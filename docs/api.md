# HTTP, URL and storage contracts

## Requests and responses

Routes are exactly `POST /links` and `GET /r/<code>`. No admin/delete route exists.
Codes match `[A-Za-z0-9_-]{12}` case-sensitively. Trailing slashes, extra segments
and percent-encoded code text are not aliases. The Lambda adapter supports API
Gateway REST proxy v1 only; HTTP API v2 envelopes fail validation.

POST requires `application/json` with optional `charset=utf-8`, a UTF-8 object
with required string `url` and optional integer `ttl_seconds`. Default TTL is
86,400 seconds; range 1–604,800. Floats, booleans, null, missing URLs, unknown or
duplicate keys, BOMs, invalid UTF-8, non-finite numbers and malformed JSON fail.
Query parameters, content encodings and transfer encodings are unsupported.

Creation returns 201 with `code`, `expires_at` (whole Unix UTC seconds) and
`short_path`. Append the path to the service base. `Location: r/<code>` is
relative to the POST URL, so `/demo/links` resolves to `/demo/r/<code>`. No header
is trusted to determine the public host. Actual output is in `validation/local-demo.txt`.

GET returns 302, empty body and a validated ASCII target Location. At the exact
boundary `now >= expires_at`, it returns the same 404 as an absent link. A previous
redirect cannot be recalled from a client that already has it. Application
responses set `Cache-Control: no-store`, `Referrer-Policy: no-referrer` and
`X-Content-Type-Options: nosniff`. No CORS policy or UI is provided.

Errors contain only fixed bounded text, for example:

```json
{"error":{"code":"not_found","message":"Link not found or expired."}}
```

| Status | Meaning |
| --- | --- |
| 400 | Bad event, JSON/schema/TTL/path or URL |
| 404 | Unknown path, invalid/missing/expired code |
| 405 | Unsupported standard method; `Allow: POST` or `GET` |
| 413 | Raw/decoded body exceeds its cap |
| 414 | Path exceeds 256 ASCII bytes |
| 415 | Unsupported/missing creation media type or encoding |
| 500 | Unexpected internal failure; no details exposed |
| 503 | Store/initialization failure, local capacity or five collisions; `Retry-After: 1` |

CLI exits 0 for help/version or normal Ctrl+C, 2 for invalid arguments or local
server startup/I/O failure. HTTP errors do not stop the process.

## Transport bounds

Raw Lambda body string/UTF-8 bytes: 8,192; decoded bytes: 4,096. Base64 uses strict
alphabet/padding validation. `isBase64Encoded` must be a boolean; body is a string
or None (empty). POST still rejects an empty JSON body. At most 32 headers, 8,192
combined name/value ASCII bytes, 64 token characters per name, 2,048 bytes per
value. Duplicate names, controls (including tabs/DEL) and incorrect types fail.
Multi-value REST headers must have exactly one value; overlapping maps must agree.
Content-Length, if present, must match decoded bytes. Query maps must be null,
absent or empty objects. Routing fields must have correct types.

Local HTTP reads only bounded Content-Length, closes each connection and refuses
duplicate headers, chunking and `Expect` (417). Stalled bodies time out after
three seconds (408). Python's parser has its own request/header line and count
ceilings before these tighter checks. Parser-level unsupported verbs can return
501 and malformed framing can yield other 4xx/505 statuses; errors still use
safe JSON. HEAD omits the response body. The sequential loopback server is for
development, not a hardened public edge.

API Gateway authorizes, decodes and matches routes before Lambda. Its errors can
differ, such as unsigned creation/unmatched resources returning 403 or throttles
returning 429. REST v1 does not preserve every wire encoding: the app validates
the path supplied by the gateway. Gateway normalization requires separate AWS
testing. Local HTTP and SDK mocks are not cloud integration tests.

## Target policy

Both original UTF-8 and resulting ASCII are capped at 2,048 bytes. Only absolute
HTTP(S) URLs are accepted. Scheme/host become lowercase, ports normalize to
integers 1–65,535. No credentials, raw whitespace, backslashes or Unicode category
`C` characters (controls, format, surrogates, private-use, unassigned). Validate
percent escapes by decoding exactly once to UTF-8; decoded controls/backslashes
and invalid UTF-8 fail. Never double-decode.

Hosts are canonical dotted IPv4, bracketed IPv6 without zone IDs, or ASCII DNS
names with at least two labels. DNS labels are 1–63 letters/digits/interior
hyphens, total length at most 253, final label starting with a letter. No trailing
dot, underscores or numeric browser shorthand. `xn--` labels must round-trip via
Python's IDNA codec (IDNA 2003, not a complete IDNA 2008/UTS 46 implementation).
Unicode hosts must be supplied as ASCII A-labels; lookalike names remain possible.

Unicode paths/queries/fragments become UTF-8 escapes. Existing escape spelling,
`+`, repeated parameters/order and empty `?`/`#` delimiters survive. Decoding is
only a validation pass, so `%250D` remains `%250D`, never a literal CR. No DNS,
preview, reputation lookup, allow-list or fetch occurs. Valid targets can include
private IPs; a browser could follow them. This is not moderation or a safety
guarantee for another system that chooses to fetch these URLs.

## Storage and retries

`secrets.token_urlsafe(9)` produces twelve characters from nine cryptographically
random bytes (72 bits). Callers cannot select codes, creation times or absolute
expiry. Five insert attempts are permitted. Clock and randomness injection are
trusted application dependencies used for tests.

DynamoDB items have exactly string `code`/canonical `url` and integer numeric
`created_at`/`expires_at`. Retrieved records are checked again before redirecting;
invalid records yield 503. Atomic PutItem uses `attribute_not_exists(#code)`.
Only ConditionalCheckFailedException is a collision; other SDK errors are
sanitized failures. There is no read-before-write uniqueness check.

Expired items still block insertion until removed; application code never
overwrites them. After TTL deletion, random reuse is theoretically possible:
there is no permanent allocation history. The local locked store has a cap of
1,000, keeps expired rows and loses everything on restart. DynamoDB persists
across Lambda invocations; its delayed TTL cleanup does not enforce read expiry.

SDK calls use standard retries, two total attempts, one-second connect and
two-second read timeouts, pool size two. Collision retries are separate. A write
can succeed before its acknowledgement is lost, so SDK/client retries can create
additional codes. POST is not idempotent. GET uses strong consistency, which does
not make the entire HTTP operation transactional. No latency/availability or
permanent no-reuse guarantee is claimed.
