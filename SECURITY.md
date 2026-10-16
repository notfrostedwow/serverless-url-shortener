# Security and responsible reporting

This undeployed portfolio service is evaluated locally with synthetic links.
A URL shortener is an open-redirect service: a valid destination can be phishing,
malware, tracking or an internal address a user's browser can visit. Codes are
identifiers, not authorization. Do not store secrets in target URLs or assume
short links are private. No security certification or independent audit is claimed.

The local server has no authentication, binds only to loopback, and must not be
exposed through tunnels or proxies. AWS creation requires IAM in the template;
redirects are public. Offline translation checks configuration, not actual AWS
enforcement. Direct Lambda invocation is a separate IAM privilege operators must
restrict. There is no function URL, admin/delete route, credential or bypass.

Before deployment, independently review writer identities and narrowly scoped
`execute-api:Invoke` permissions for the intended API/stage/method/path. Test
unsigned/unauthorized denial in an authorized sandbox. IAM alone does not moderate
authorized writers. Add writer quotas, destination review, takedown ownership,
redirect abuse controls, alerts and budgets. Takedown is not implemented here;
it would require a separately authorized operational procedure. Expiry cannot
revoke an already received target. Throttles/concurrency are not hard cost caps.

Input bounds cover URL/body/header/path sizes, TTLs, local capacity and collision
attempts. Parsing uses no eval/pickle, archive extraction or target fetching.
Percent decoding occurs once for validation without rewriting existing queries.
The DynamoDB adapter revalidates stored targets before they reach headers.
Conditional inserts prevent collision overwrites; app expiry does not depend on
TTL cleanup. Exact boundaries/unsupported forms are in [docs/api.md](docs/api.md).

Application logs contain only fixed event/route labels and statuses. No targets,
paths, query strings, IPs, headers, bodies, codes or exception details are logged.
Default local access/error tracebacks are suppressed. API Gateway execution data
tracing/access logging are disabled. Lambda platform records still include
operational metadata. Do not enable SDK debug logs with real input. Targets
remain stored in DynamoDB and appear in redirect responses; recipients must
handle them appropriately.

The function has GetItem/PutItem only on its exact table and log stream writes
only under its exact group. Encryption and fourteen-day log retention are
configured. TTL cleanup is delayed; retained resources outlive stack deletion.
There are no backups, WAF, recovery/abuse procedures or availability objectives.
[docs/cloud.md](docs/cloud.md) covers those deployment limits.

Report suspected vulnerabilities privately through an already established owner/
parent channel. No reporting email or advisory contact has been configured;
do not invent one or disclose sensitive details in public issues. Include the
version, minimal synthetic reproducer, expected/actual behavior and boundary.
Never send credentials or real logs. No response-time or bounty promise is made.
Local checks in CONTRIBUTING.md reduce mistakes but do not replace review.
