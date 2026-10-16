# Zaheer's guide

Start with `tools/demo.py`: it launches the installed server, creates a link,
reads the redirect without following it, and checks error responses. It gives
you a real request to follow through the code. The local tool works without AWS;
cloud behavior has only offline tests.

## Follow a request

`local.py` binds a real development HTTP server to `127.0.0.1`, reads a bounded
body and passes method/path/headers/bytes to `http.Application`. The memory store
lasts for that process only. Restarting loses links; this is explicit local
behavior, not simulated DynamoDB persistence.

`http.py` recognizes POST `/links`, validates JSON/media type and calls
`Shortener.create` in `domain.py`. Only `url` and optional `ttl_seconds` are
accepted. Python booleans are int subclasses, so exact integer type checking
deliberately rejects `true` as a TTL.

URL parsing alone is not validation: parsers may accept missing hosts or strip
controls. `target_url` rejects controls first, checks scheme/host/port and emits
an ASCII URI. Hosts must already use ASCII DNS/A-labels or IP literals. Unicode
path/query text becomes UTF-8 escapes, while existing query escapes stay intact.
`+`, `%2B`, repeated parameters and nested `%25` values keep their meaning.
Nothing contacts the destination.

Normal creation uses whole Unix UTC seconds and nine cryptographically random
bytes. Tests inject the clock and code generator. The service calculates expiry
and tries up to five atomic insertions. Clients cannot choose codes. The 201
response contains code, expiry and path, not the source URL. Its relative
Location keeps an AWS stage prefix and never uses the Host header as authority.

GET `/r/<code>` checks grammar, reads storage, then compares current time with
expiry. At the exact expiry second, the result is 404, like an unknown code.
Live records return 302, an ASCII Location and no body. `no-store` discourages
cached redirects; it cannot recall a target already received by another client.

## Why conditional writes and application expiry?

A read-then-write uniqueness check races: two requests can both see absence.
DynamoDB PutItem with `attribute_not_exists(#code)` makes that decision atomic.
Conditional failure means collision. Timeouts and permissions failures mean
storage failure and must not be disguised as collisions. The local adapter uses
a lock for the same insert-if-absent contract within one process.

DynamoDB TTL is asynchronous cleanup. An expired row may still be returned, so
every read must enforce `now >= expires_at`. Existing expired rows also block
insertion while present. Once removed, random reuse is theoretically possible;
there is no permanent allocation history. Strongly consistent reads help a new
link become immediately readable but don't make an HTTP request transactional.

## What AWS adds

API Gateway supplies HTTPS routes and a `demo` stage. SAM configures IAM for
creation and public redirects. `aws.py` decodes REST proxy v1 events and lazily
creates a reusable SDK client; `dynamodb.py` translates typed links into SDK
attributes, validates retrieved records and sanitizes errors. DynamoDB persists
across Lambda invocations. CloudWatch receives fixed outcome summaries and
platform messages. The runtime role has only this table's GetItem/PutItem and
this log group's stream writes.

SDK calls have two total attempts, one-second connect/two-second read timeouts.
Lambda has ten seconds and reserved concurrency two. These are bounds, not
measured performance or hard spending guarantees. A write can succeed before
its acknowledgement is lost; retries may create extra links. POST is not
idempotent. The local store's cap of 1,000, including expired rows, requires a
restart when full; the deployed store has different capacity/cost behavior.

The checker validates SAM, translates it with the installed official translator,
checks generated authorization and validates CloudFormation. A nonexistent
artifact URI is substituted only for offline translation. No packaging upload,
AWS validation or deployment occurs. Read docs/cloud.md for retained resources,
IAM scopes, operations and rough cost arithmetic.

## Interview walkthrough

**What works?** The installed CLI serves real local HTTP. Application, socket
and actual SDK Stubber tests run offline. SAM/template checks also run. There is
no deployed endpoint, AWS integration result or verified green remote workflow.
Use the exact evidence in docs/verification.md.

**Why this structure?** `domain.py` owns URL/expiry/storage rules; `http.py` maps
them to responses. `local.py`, `aws.py` and `dynamodb.py` handle their transports
or SDK boundary. Clock/randomness/storage injection makes boundaries deterministic.
The local runtime has no third-party dependency; AWS's pinned SDK keeps its own
licenses and notices.

**What could be abused?** A valid link can direct a browser to phishing or a
private network. No server-side fetching avoids turning this into a fetch proxy,
but does not establish destination trust. IAM gates AWS writers only when
correctly deployed. Authorized writers still need quotas and moderation. Codes
are not secrets, and no takedown route exists here.

**What do tests prove?** Exact expiry, collision no-overwrite/exhaustion,
validation/encoding/bounds, safe errors/logs and real local HTTP behavior are
exercised. Stubber checks real SDK shapes/parameters without packets. It does
not prove IAM enforcement, gateway normalization, throttling, deployability,
capacity or availability. Socket guards make accidental cloud calls fail.

**What comes next?** Independent security/full-history review. Before publication
or deployment, define writer policy, quotas, moderation/takedown ownership,
privacy, alarms and budgets. An authorized sandbox should test packaging,
deployment, unsigned-denial, IAM, encoding and real expiry. Add idempotency if
clients need reliable retried creates; measure behavior before adding caches,
analytics or a UI. This build stops at local delivery.
