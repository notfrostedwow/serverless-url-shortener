# Serverless URL shortener

A working Python HTTP service that creates random short links and redirects them
until expiry. It runs without AWS and includes a real DynamoDB adapter and an
**undeployed** SAM template for API Gateway, Lambda, DynamoDB and CloudWatch Logs.
An original portfolio project for **notfrostedwow**, using synthetic examples.

## Run locally

Python 3.11+ is required. From this repository in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e .
.venv/Scripts/url-shortener --port 8000
```

Keep that process running. It binds only to `127.0.0.1`, has **no authentication**,
and retains at most 1,000 links **only until the process stops**. Expired records
still occupy capacity; restart to clear them. This is a sequential development
HTTP server with a three-second connection timeout. Never expose or tunnel it.
The local path uses only the standard library, without SDK imports or credentials.

In a second PowerShell terminal:

```powershell
$payload = '{"url":"https://example.com/docs?ref=demo","ttl_seconds":60}'
$created = $payload | curl.exe --noproxy "*" --max-time 3 -sS http://127.0.0.1:8000/links -H "Content-Type: application/json" --data-binary "@-" | ConvertFrom-Json
$created
curl.exe --noproxy "*" --max-time 3 -i "http://127.0.0.1:8000$($created.short_path)"
```

POST returns 201 with `code`, `short_path` and integer UTC `expires_at`. GET returns
302 with the target in `Location` and `Cache-Control: no-store`; after 60 seconds
it returns 404. Curl does **not** use `--location`, so it never visits the target.
Codes/timestamps vary because the live local process uses its real clock and
cryptographic randomness. Stop it with Ctrl+C.

This one-command demo starts the **installed CLI**, executes actual curl requests,
checks 201/302/404/405/400 and stops its child server:

```powershell
.venv/Scripts/python tools/demo.py
```

Read the [actual session](docs/validation/local-demo.txt). Windows console capture
produced blank pixels; no screenshot or illustrated substitute is claimed. The
[attempt record](docs/validation/screenshot-attempt.txt) is retained. On Linux/macOS
use `.venv/bin/` instead of `.venv/Scripts/`, and `curl` instead of `curl.exe`.

## Contract

| Request | Success | Other application responses |
| --- | --- | --- |
| `POST /links` | 201 JSON; relative `Location: r/<code>` | 400 invalid input, 413 body size, 415 media type, 503 storage/collision exhaustion |
| `GET /r/<code>` | 302, ASCII Location, empty body | 404 missing/expired/invalid code, 503 store failure |
| Other standard method on a recognized route | 405 with `Allow` | AWS creation is gated by IAM first |
| Unknown application path | 404 JSON | API Gateway can reject before Lambda |

JSON accepts exactly `url` plus optional integer `ttl_seconds` (default 86,400;
range 1–604,800). Boolean TTLs, duplicate/extra keys and malformed UTF-8/JSON fail.
Decoded bodies are capped at 4,096 bytes; Lambda's raw body cap is 8,192 bytes.
Codes are twelve characters matching `[A-Za-z0-9_-]{12}`. Append `short_path` to
your known API base, including `/demo` in AWS. The relative creation Location
preserves that stage prefix and never trusts the Host header to build a URL.

Targets must be HTTP(S), at most 2,048 original UTF-8 and resulting ASCII bytes.
Controls (also percent-escaped CR/LF), credentials, raw whitespace, backslashes,
bad escapes and malformed hosts fail. Unicode hosts must already use valid ASCII
IDNA A-labels. Unicode path/query/fragment text becomes UTF-8 escapes. Existing
query escapes, `+`, parameter order and empty `?`/`#` delimiters are preserved.
No DNS lookup or target fetching occurs. The exact policy and transport differences
are in [docs/api.md](docs/api.md).

## Architecture

```mermaid
flowchart LR
    subgraph Local[Working local service: no AWS]
      Curl[Curl client] --> Dev[Loopback Python HTTP server]
      Dev --> Rules[Typed HTTP and URL rules]
      Rules --> Memory[Bounded memory: process lifetime]
    end
    subgraph AWS[Undeployed AWS implementation]
      Client[HTTPS client] --> Gateway[API Gateway REST: demo stage]
      Gateway -->|IAM creation; public redirects| Lambda[Python Lambda]
      Lambda --> Shared[Same typed application rules]
      Shared --> Dynamo[DynamoDB conditional writes / consistent reads]
      Lambda --> Logs[CloudWatch Logs: fixed outcome summaries]
    end
```

Nine random bytes produce a 72-bit code. Creation attempts at most five atomic
inserts and cannot overwrite a collision. Reads check `now >= expires_at`, even
while DynamoDB TTL deletion is pending. Storage, clock and code generation are
injected for deterministic tests. The SDK has bounded attempts/timeouts.

A shortener is inherently an **open-redirect service**: valid destinations can
still be harmful. Codes are not authorization. The SAM template explicitly
requires IAM for creation; redirects remain public. Offline translation checks
that configuration, not AWS enforcement. Public deployment still needs reviewed
writer policies, quotas, moderation/takedown, abuse monitoring, budgets and
operational ownership. Throttles are best effort, not spending caps. Read
[SECURITY.md](SECURITY.md) and [docs/cloud.md](docs/cloud.md).

## Checks and review

```powershell
.venv/Scripts/python -m pip install -e . -r requirements-dev.txt
.venv/Scripts/python tools/verify.py
```

The verifier runs pytest, real loopback HTTP, SDK Stubber tests, Ruff lint/format,
strict mypy, `pip check`, source SAM cfn-lint, offline SAM translation/security
checks and cfn-lint on generated CloudFormation. Socket/DNS guards prohibit cloud
networking. Temp parents are created explicitly in fresh checkouts.

[docs/verification.md](docs/verification.md) records actual results and limitations.
Python 3.11/3.12 CI has only `contents: read`, pinned actions and no deployment or
credential steps. No remote run, badge or AWS integration success is claimed.

[ZAHEER-GUIDE.md](ZAHEER-GUIDE.md) explains the code and interview tradeoffs;
[CONTRIBUTING.md](CONTRIBUTING.md) covers local checks. Original code is
[MIT licensed](LICENSE), Copyright (c) 2026 Zaheer Miah, with explicit approval.
Dependencies retain [their own licenses/notices](docs/dependencies.md). Parent
review controls all future publication and deployment.
