# AWS design: undeployed

The local HTTP service works. The AWS adapter/template are implemented and checked
offline, with no AWS connection, account inspection, deployment or integration
test. Local validation cannot establish IAM enforcement, quotas or deployability.

## Services and permissions

| Component | Why it exists | Configuration in this repository |
| --- | --- | --- |
| API Gateway REST API | HTTPS routing and IAM authorization | Regional endpoint, explicit `demo` stage; IAM on `/links`, public `/r/{code}` |
| Lambda | Run the shared typed Python application | Python 3.12, arm64, 256 MiB, 10 seconds, concurrency 2 |
| DynamoDB | Persist one record per code independently of Lambda | On-demand table, string partition key `code`, numeric TTL `expires_at`, encryption enabled |
| CloudWatch Logs | Fixed application outcomes and runtime diagnostics | Precreated exact function group, 14-day retention |
| IAM | Limit runtime and caller privileges | Function GetItem/PutItem on this exact table; stream creation/events in this exact group |
| SAM / CloudFormation | Describe and transform the resources | Versioned template, standard Python build input under `src/` |

There is no VPC, NAT gateway, S3 application storage, CDN, custom domain, function
URL, API key, authorizer Lambda or database scan. A future SAM deployment may
use a separately controlled S3 **build-artifact** bucket; none exists from this
work and no artifact was uploaded. Runtime credentials/administration permissions
are never included in source or supplied by local tools.

The role has no DeleteItem, UpdateItem, Scan, Query or wildcard table access.
`logs:CreateLogStream` and `logs:PutLogEvents` cover only
`/aws/lambda/<FunctionName>:log-stream:*`; this wildcard is for dynamic runtime
stream names in that one group. It cannot create groups. SAM generates API
invocation permissions scoped to this API/account and its two route shapes;
its generated ARN permits any stage/method for those shapes. Inspect and consider
narrowing that generated scope during deployment review. These resource-policy
permissions are separate from the function's table/log role and client policies.

SSE is explicitly enabled using DynamoDB's default AWS managed key selection,
without a customer-managed key. No KMS wildcard permission is added. The table
and log group have Retain on deletion/replacement. TTL cleanup is delayed and
retention is not synchronous erasure. Removing a stack leaves retained resources
and possible costs; a separately authorized cleanup/retention review is required.
Point-in-time recovery is explicitly off; backups/recovery are not implemented.

## Authentication and abuse boundary

The creation event explicitly uses `Authorizer: AWS_IAM`. Public redirects have
no authorizer. Generated OpenAPI is checked offline for that exact distinction.
This is configuration evidence, not an AWS enforcement test. Future clients
must sign requests with an authorized identity; there is no local token or
unauthenticated production fallback. Client IAM policies should allow only
`execute-api:Invoke` on the chosen API, `demo` stage, POST and `/links`. Broader
direct Lambda invocation rights can bypass the API gate and must be restricted
to reviewed operators. Deployment roles are separate from the runtime role.

Local HTTP has no auth and must remain on loopback. Before public use, define
writer quotas, moderation, takedown/escalation ownership, privacy and alerting.
IAM does not prevent an authorized writer from making a malicious link. Public
redirect traffic can enumerate codes, attack browsers or consume capacity. There
is no allow-list, threat intelligence, WAF or automated takedown in this build.

The API stage sets 5 requests/second and burst 10 across methods; Lambda reserves
two concurrent executions. API Gateway throttles are best effort, not hard usage
or spending limits. SDK attempts, body caps and short timeouts bound some work
but do not provide a production abuse strategy. Add reviewed per-writer quotas,
operational alarms and budgets before allowing traffic. No auto-deployment exists.

Application logs contain only event, fixed route label and HTTP status; no URL,
query, IP, body, headers, code or exception. Gateway data tracing, execution
logging and access logging are off to avoid accidental request disclosure and
additional account-level logging setup. Lambda platform logs still have request
metadata. A future privacy-reviewed access log could use only approved fields;
do not turn on request/response data tracing or SDK debug logging with real data.

## Consistency, failure and limits

GetItem is strongly consistent. PutItem is conditional on code absence. Reads
enforce expiry even while TTL removal is pending; expired keys still present
cannot be overwritten. The 72-bit random code space reduces accidental collisions
but is not access control, permanent non-reuse or an availability guarantee.

Two total SDK attempts use standard backoff, with one-second connect and
two-second read timeouts and pool size two. Up to five candidate IDs may be tried
on conditional failures only. Lambda's ten-second timeout is an outer limit;
combined network waits/retries can exhaust it. Store errors become bounded 503s,
unexpected application errors 500s. Cold-start/setup failure is sanitized to 503.
No SDK error text reaches clients or application logs. A platform timeout can
produce a gateway 5xx rather than the application JSON response.

HTTP invocation is synchronous, not an async event/replay queue. There is no
exactly-once or POST idempotency guarantee. A PutItem can succeed before an
acknowledgement is lost; a retry can allocate an extra code. Retried callers can
also create duplicates. GET is read-only, but reads still cost money, including
absent/expired lookups. There are no partial-batch semantics, streams or DLQs.

The application accepts at most 2,048 URL bytes after normalization, 4,096 decoded
body bytes and 8,192 raw Lambda body bytes. Headers/path limits are in api.md.
No target fetching, previews or analytics writes occur. A created item's size
depends on its target; write/read request-unit rounding affects costs. There
are no load tests, alarms, backup/restore drills or availability objectives.
Operators need an incident playbook, replay/idempotency decisions and cleanup
procedures before real deployment.

## Offline validation actually executed

```powershell
.venv/Scripts/python tools/validate_iac.py
```

The script disables socket connections and DNS, overrides AWS config/credentials
with workspace dummy values, and supplies `infra/cfnlintrc.json` explicitly to
avoid user-level lint config search. It runs cfn-lint on `infra/template.yaml`,
uses the installed official SAM translator, verifies generated route auth, then
runs cfn-lint on `.tmp/transformed-template.json`. A nonexistent
`s3://offline-placeholder-build/shortener.zip` replaces CodeUri **only in memory**
because translation expects a packaged URI. No S3 lookup, managed policy lookup,
upload or AWS validation occurs. The source still builds from `../src/`.

The installed cfn-lint validates SAM schemas directly, so explicit translation
adds a separate check. The translator emits a `normalized_open_api_version`
feature-toggle warning; translation/assertions and both lint runs exit 0. See
[validation/checks.txt](validation/checks.txt). This is not `sam validate` via
SAM CLI, a provider-backed plan or a deployment test. SAM CLI is not installed.

The offline packaging check separately assembles a Lambda layout with the pinned
pure-Python SDK wheels and imports its own handler/SDK under a socket guard.
It does not establish SAM CLI/runtime packaging, arm64 execution or AWS operation.

## Intended HOWTO: not executed

Only a separately authorized parent-controlled sandbox should perform these steps:

1. Finish independent security/full-history review and choose region, unique
   function name, writer IAM policy, moderation/takedown and cost/alert ownership.
   The explicit function/log names conflict if reused by another stack.
2. Review/install SAM CLI and provide a matching Python 3.12 build environment.
   A future `sam build --template-file infra/template.yaml` uses `src/requirements.txt`
   plus the package under `src/shortener`. All pinned SDK distributions are pure
   Python; recheck compatibility/licenses after upgrades. No Docker workflow is
   provided or required by local checks. SAM build itself was not run here.
3. Prepare a deployment/change set with separate deployment/artifact permissions.
   Review generated IAM, API integration, invoke scopes, retained resources and
   costs before approving execution. No deployment command is authorized by this
   local build. Do not put credentials into this repository or reuse a personal
   authentication session through these tools.
4. In that authorized environment, test signed success, unsigned/unauthorized
   denial, public GET, exact expiry despite retained TTL rows, malformed/base64
   requests, gateway path normalization, throttling, SDK failures and privacy of
   logs. Confirm retained-resource cleanup and recovery before enabling traffic.

## Rough monthly illustration: October 2026

Arithmetic dated **2026-10-15**, US East (N. Virginia), USD. Not a live bill, quote,
regional guarantee or free-tier promise. Assume 1,000 creates and 10,000 redirects
per month, one invocation/database operation each, zero collisions/retries,
items at most 1 KiB (one write unit or strong read unit), 100 ms at 256 MiB per
invocation (275 GB-seconds), average 1 MB table storage and 1 KiB of all log
messages per invocation (about 0.0113 GB ingested). Fourteen-day log retention.

| Component | Illustrative unit assumption | Approximate monthly amount |
| --- | --- | --- |
| REST API | $3.50 per million requests | $0.0385 |
| Lambda requests | $0.20 per million | $0.0022 |
| Lambda arm64 compute | Assumed $0.0000133334 / GB-second | $0.0037 |
| DynamoDB writes / strong reads | $0.625 / $0.125 per million units | $0.0019 |
| DynamoDB storage | Assumed $0.25 / GB-month | $0.0003 |
| CloudWatch ingestion / storage | Assumed $0.50 / GB ingested, $0.03 / GB-month stored | About $0.0058 |

The modeled components total roughly **$0.06/month**, before tax, transfer,
artifact storage, logging variance, extra IAM-denied traffic or any optional
monitoring/security services. A 2 KiB item doubles write units. Sustained abuse
and retries invalidate this tiny-traffic example; throttling is not a billing
cap. No free tier or discount is subtracted.

Public official pricing pages were consulted on 2026-10-15:
[API Gateway](https://aws.amazon.com/api-gateway/pricing/),
[Lambda](https://aws.amazon.com/lambda/pricing/),
[DynamoDB](https://aws.amazon.com/dynamodb/pricing/),
[CloudWatch](https://aws.amazon.com/cloudwatch/pricing/).
Some regional/architecture prices are dynamically rendered, so explicitly
assumed units above must be reconfirmed in the selected region before approval.
