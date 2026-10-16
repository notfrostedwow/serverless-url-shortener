"""Validate SAM and transformed CloudFormation with no network or account config."""

from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, NoReturn


def blocked(*args: Any, **kwargs: Any) -> NoReturn:
    raise RuntimeError("network is disabled during offline template validation")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    config = temporary / "iac-aws-config"
    config.write_text("[default]\nregion = us-east-1\n", encoding="utf-8")
    os.environ.update(
        AWS_CONFIG_FILE=str(config),
        AWS_SHARED_CREDENTIALS_FILE=str(config),
        AWS_PROFILE="default",
        AWS_DEFAULT_PROFILE="default",
        AWS_ACCESS_KEY_ID="offline-placeholder",
        AWS_SECRET_ACCESS_KEY="offline-placeholder",  # noqa: S106 -- disables credential discovery
        AWS_SESSION_TOKEN="offline-placeholder",  # noqa: S106 -- noncredential, sockets are blocked
        AWS_EC2_METADATA_DISABLED="true",
        AWS_DEFAULT_REGION="us-east-1",
    )
    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked
    socket.getaddrinfo = blocked
    os.chdir(root)
    from cfnlint.runner import main as lint_main

    def lint(template: str) -> None:
        sys.argv = [
            "cfn-lint",
            "--config-file",
            "infra/cfnlintrc.json",
            "--template",
            template,
            "--regions",
            "us-east-1",
        ]
        print(
            " ".join(sys.argv) + " (sockets/DNS disabled; workspace dummy AWS config)", flush=True
        )
        try:
            lint_main()
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise

    lint("infra/template.yaml")
    import boto3
    from samtranslator.parser.parser import Parser
    from samtranslator.translator.translator import Translator
    from samtranslator.yaml_helper import yaml_parse

    template = yaml_parse((root / "infra/template.yaml").read_text(encoding="utf-8"))
    # Translation consumes packaged S3 URIs. Substitute a NONEXISTENT artifact,
    # not a real bucket, without packaging, uploading or touching S3.
    template["Resources"]["Shortener"]["Properties"]["CodeUri"] = (
        "s3://offline-placeholder-build/shortener.zip"
    )
    session = boto3.Session(region_name="us-east-1")
    transformed = Translator({}, Parser(), boto_session=session).translate(template, {})
    generated = transformed["Resources"]
    paths = generated["RestApi"]["Properties"]["Body"]["paths"]
    create = paths["/links"]["x-amazon-apigateway-any-method"]
    redirect = paths["/r/{code}"]["x-amazon-apigateway-any-method"]
    output = temporary / "transformed-template.json"
    output.write_text(json.dumps(transformed, indent=2), encoding="utf-8")
    if create.get("security") != [{"AWS_IAM": []}]:
        raise RuntimeError("transformed create route must require AWS_IAM")
    if redirect.get("security") not in (None, []):
        raise RuntimeError(f"transformed redirect route must be public: {redirect.get('security')}")
    if any(resource["Type"].startswith("AWS::Serverless::") for resource in generated.values()):
        raise RuntimeError("SAM resources remain after transformation")
    print(
        f"Offline SAM translation: {len(generated)} resources; "
        "IAM create/public redirect verified; "
        "no managed policy lookup, packaging or AWS calls.",
        flush=True,
    )
    lint(".tmp/transformed-template.json")


if __name__ == "__main__":
    main()
