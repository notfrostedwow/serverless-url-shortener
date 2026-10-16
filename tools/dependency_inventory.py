"""Inventory local distribution declarations and license/notice text hashes."""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    inventory = []
    runtime = {"boto3", "botocore", "jmespath", "s3transfer", "python-dateutil", "six", "urllib3"}
    for distribution in sorted(
        metadata.distributions(), key=lambda dist: dist.metadata["Name"].lower()
    ):
        name = distribution.metadata["Name"]
        if name == "serverless-url-shortener":
            continue
        notices = []
        for file in distribution.files or []:
            if not any(word in file.name.lower() for word in ("license", "notice", "copying")):
                continue
            path = Path(distribution.locate_file(file)).resolve()
            if not path.is_relative_to(root) or not path.is_file() or path.suffix == ".pyc":
                continue
            raw = path.read_bytes()
            notices.append(
                {"file": str(file).replace("\\", "/"), "sha256": hashlib.sha256(raw).hexdigest()}
            )
            if name.lower() in runtime:
                target = root / "docs" / "third-party-notices" / name / Path(file)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        declared = distribution.metadata.get("License-Expression") or distribution.metadata.get(
            "License"
        )
        classifiers = [
            value
            for value in distribution.metadata.get_all("Classifier", [])
            if value.startswith("License ::")
        ]
        inventory.append(
            {
                "name": name,
                "version": distribution.version,
                "declared_license": declared,
                "license_classifiers": classifiers,
                "notices": notices,
            }
        )
    destination = root / "docs" / "dependency-licenses.json"
    destination.write_text(
        json.dumps(inventory, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    print(f"Recorded {len(inventory)} distributions; copied runtime third-party notices unchanged.")


if __name__ == "__main__":
    main()
