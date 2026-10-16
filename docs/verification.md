# Local verification

Windows / Python 3.11.9, 2026-10-15. All examples and test data are synthetic.
No AWS call, account connection, credential discovery, remote creation, push,
publication, Docker or deployment has been performed. No remote CI or Python
3.12 execution is claimed. Public AWS API/pricing docs were checked; package
downloads used a package index. Source was written in this workspace only.

**Final result: 232 tests passed with no skips**, both in the main working tree
and a fresh detached checkout. Ruff lint/format, strict mypy (six source modules),
`pip check`, source SAM cfn-lint, offline SAM translation/auth assertions and
generated CloudFormation cfn-lint all returned 0. Genuine native screenshot
capture is the outstanding artifact blocker; the actual text session is saved.

## Executed commands

Using `.venv/Scripts/python.exe`, from the repository root:

```text
python -m venv .venv
python -m pip install --log docs/validation/install.log -e ".[aws]" pytest ruff mypy cfn-lint setuptools
python -m pip install --log docs/validation/sam-tools-install.log aws-sam-translator "setuptools>=77,<83"
python -m ruff check . --fix
python -m ruff format .
python tools/verify.py
python tools/demo.py
python tools/dependency_inventory.py
python -m pip download --dest .cache/wheels -r requirements-aws.txt --log docs/validation/wheels-download.log
python tools/package_check.py
python tools/capture_terminal.py
git diff --check
```

Install commands disabled pip user configuration/version checks and used
workspace-local cache/temp paths. `--log` captured installer debugging locally
under ignored `docs/validation/*.log`; installed versions/licenses are committed
in dependency-licenses.json. Build backend and final requirements are pinned.
The shell quoted the setuptools version constraint; it was not a redirection.

The complete latest verifier commands/stdout/stderr/exits are in
[validation/checks.txt](validation/checks.txt), including actual source/transformed
cfn-lint and offline SAM translation. Development checkpoints: first 207
application/SDK tests passed, then 223 with live HTTP/infrastructure tests, then
229 after gateway header/body boundaries. Later results supersede these counts.

## Real local behavior and packaging

[validation/local-demo.txt](validation/local-demo.txt) is actual installed CLI and
curl output: 201 create, 302 redirect, 404 absent, 405 method and 400 invalid
scheme. Curl never follows targets; the child service is stopped afterward.
Runtime logs contain only fixed labels/statuses. Ports, random codes and actual
clock/date fields vary between runs. Test fixtures inject deterministic values.
The README's actual PowerShell curl pipeline was also executed against the real
server on port 8000; see [validation/powershell-example.txt](validation/powershell-example.txt).
The first Invoke-RestMethod example failed because Windows PowerShell sent
`Expect: 100-continue`, which the deliberately simple local transport rejects
with 417. The final example uses curl's stdin pipeline and was verified directly.

[validation/package.txt](validation/package.txt) records actual offline wheel
build/install and artifact commands. Each invocation creates a new local temp
directory/venv. MIT metadata/license is verified, wheel-only stdlib create/resolve
works, and a separately assembled Lambda artifact imports its packaged SDK and
handler under blocked sockets. No Lambda invocation or SAM CLI build is implied.

`tools/capture_terminal.py` attempted a dedicated hidden console and then rendering
only that console offscreen without activation. The native capture was blank.
[validation/screenshot-attempt.txt](validation/screenshot-attempt.txt) records the
failure (exit 1); no image, desktop screenshot or illustrated substitute is
claimed. The first capture attempt also exposed a 64-bit WinAPI handle signature
error, corrected before the blank-rendering result. No user app was inspected.

## Development findings

Initial lint/format findings were fixed. One test collection failed because
`request` is reserved by pytest; the parameter was renamed. Mypy required an
explicit annotation for BaseHTTPRequestHandler's runtime `raw_requestline`.
SAM cfn-lint caught the regional endpoint shape; it now uses `{Type: REGIONAL}`.
Explicit translation exposed an unwanted `NONE` marker in the initial default-
auth override, so the final template applies IAM directly to creation instead.
Generated OpenAPI authorization is asserted. Both final lint passes exit 0.

The current SAM translator emits a `normalized_open_api_version` feature-toggle
warning; it is preserved in the transcript, not presented as a test failure or
suppressed. Source SAM validation alone is not transformation in this cfn-lint
version, which is why both translation and generated-template validation run.
Review caught the API stage-prefix risk in the creation Location; the final
relative Location preserves it. No live URL or AWS target was queried to test it.

## Not executed / limitations

AWS integration, actual IAM denial/allow, API Gateway wire normalization,
throttling, TTL cleanup, SAM CLI build/deploy, arm64 execution, load tests,
backup/recovery and remote CI are untested. Python 3.12 is a CI matrix target;
only 3.11.9 is available locally. SDK Stubber is an offline unit boundary, not
cloud integration. Native terminal screenshot capture remains unavailable.

## Fresh checkout and local commit provenance

Source and all check tools were committed at
`1877f13779f6839aa0377d7e3d6679199f9fa31e`, following the license/notices commit
`25e8eb7`. Immediately before each commit, repository root and local author were
verified as this workspace and
`notfrostedwow <105129603+notfrostedwow@users.noreply.github.com>`.
Hooks/signing were disabled for these local commit invocations, with no global
Git changes or authentication commands.

The executed fresh-checkout command was:

```text
git -c core.hooksPath=NUL worktree add --detach .cache/clean-review-1877f13 1877f13779f6839aa0377d7e3d6679199f9fa31e
```

Before checks, `.tmp`, `.cache`, `.venv` and `build` were asserted absent in that
checkout. No ignored directories or untracked source were copied. It reused
only the existing **same-workspace** virtual environment's installed tools.
`PYTHONPATH` selected the fresh checkout's `src`; imported `shortener.__file__`
was printed and asserted to be inside it. The existing interpreter ran
`tools/verify.py` with the fresh checkout as cwd. Explicit temp creation therefore
ran from genuinely absent parents. The full fresh suite passed **232 tests**;
every other check exited 0. Commands, source provenance, stdout/stderr and exits
are in [validation/clean-checkout.txt](validation/clean-checkout.txt).

The fresh verifier output was copied verbatim to validation/checks.txt. Captured
stdlib HTTP `Server: LocalShortener ` headers contain a trailing space; the
validation-text-only Git whitespace attribute preserves that actual output
instead of editing it to satisfy a source whitespace rule. The final evidence
commit adds these saved records/verification prose and that attribute; it does not
change the validated source, workflow, infrastructure or tools. The detached
review tree remains ignored under `.cache/` for parent inspection. No worktree
outside the permitted project directory was created.
