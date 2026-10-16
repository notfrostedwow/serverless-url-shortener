# Dependencies and notices

The local installed service has **zero third-party runtime dependencies**. AWS
uses boto3 1.43.114. Its complete runtime set is pinned in `src/requirements.txt`;
the root `requirements-aws.txt` includes that one source of version truth. SAM's
standard Python build reads the requirements beside its `src/` CodeUri.

Unchanged runtime license/notice files are preserved under
[third-party-notices](third-party-notices). The [local inventory](dependency-licenses.json)
records 40 installed distributions, declared licenses, source notice paths and
SHA-256 hashes. This inventory is not a vulnerability audit or legal opinion.
Original code is MIT with explicit Zaheer approval; that does not relicense any
third-party code. No dependency source/wheels are committed as original work.

| Runtime distribution | License checked from installed declarations/text |
| --- | --- |
| boto3, botocore, s3transfer | Apache-2.0, including bundled notices |
| jmespath, six, urllib3 | MIT |
| python-dateutil | Apache-2.0 plus historical BSD-3-Clause portions; see bundled LICENSE |

Development tools are pinned directly in `requirements-dev.txt`; their transitive
environment is recorded in the inventory and can change on a later install.

| Development tools/packages | License declarations / text |
| --- | --- |
| pytest, Ruff, mypy, mypy_extensions, setuptools, pip | MIT; bundled vendor notices retained in distributions |
| cfn-lint | MIT-0 |
| aws-sam-translator | Apache-2.0 |
| annotated-types, attrs, iniconfig, pluggy, librt, ast_serialize | MIT |
| PyYAML, jsonschema, jsonschema-specifications, referencing, rpds-py | MIT |
| pydantic, pydantic_core, typing-inspection | MIT |
| colorama, jsonpatch, jsonpointer, networkx, mpmath, sympy | BSD-3-Clause (some declare the broader BSD label; text inspected) |
| Pygments | BSD-2-Clause |
| packaging | Apache-2.0 OR BSD-2-Clause |
| pathspec | MPL-2.0 |
| regex | Apache-2.0 AND CNRI-Python |
| typing_extensions | PSF-2.0 |

MPL-licensed pathspec is an unmodified development dependency of mypy; it is not
part of the deployed/local runtime artifacts. Do not remove its notices or claim
it is MIT. Recheck all licenses when changing packages. Regenerate the inventory
with `python tools/dependency_inventory.py` from the project virtual environment.

Build backend setuptools is pinned to 82.0.1. Offline packaging verifies the
original MIT LICENSE and `License-Expression: MIT` in the built wheel. SDK wheels
and generated environments/artifacts remain ignored workspace files.
