# Contributing locally

Use Python 3.11/3.12 and synthetic data. Keep original code under MIT and preserve
third-party notices. Parent controls publication/deployment. No AWS credentials,
account connection, Docker or LocalStack are needed.

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e . -r requirements-dev.txt
.venv/Scripts/python tools/verify.py
.venv/Scripts/python tools/demo.py
git diff --check
```

Use `.venv/bin/python` on Linux/macOS. The verifier saves stdout/stderr, commands
and exits in `docs/validation/checks.txt`. It runs pytest, Ruff lint/format,
strict mypy for all source modules, pip consistency and source/translated SAM
validation with sockets disabled. Pytest creates explicit temp parents; normal
`python -m pytest` temp defaults work too.

Tests block cloud/DNS access. Only the `loopback` marker permits numeric
`127.0.0.1` sockets. AWS tests use workspace dummy config, explicit noncredentials
and Stubber; never remove the guard to make a test pass. Do not follow external
target redirects. New behavior needs useful positive/negative/boundary tests.

Optional packaging/license checks:

```powershell
.venv/Scripts/python -m pip download --dest .cache/wheels -r requirements-aws.txt
.venv/Scripts/python tools/package_check.py
.venv/Scripts/python tools/dependency_inventory.py
```

The packaging script builds offline, installs the wheel into a newly created
venv, checks MIT metadata/license and stdlib create/resolve, then assembles a
fresh SDK-packaged Lambda layout and checks imports with sockets blocked. It
is not a SAM build or cloud test. Windows console capture may be unavailable;
record failure without fabricating an image.

Before committing, verify `git rev-parse --show-toplevel`, `git status --short`,
`git diff --check`, `git config --local --get user.name` and
`git config --local --get user.email`. The local author must be `notfrostedwow
<105129603+notfrostedwow@users.noreply.github.com>`. Do not access other private
projects, global Git/gh settings, authentication or secrets. Do not create remotes,
push, publish or deploy. Add no CI badge without a verified remote run.
