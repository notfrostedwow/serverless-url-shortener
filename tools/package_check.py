"""Verify a fresh wheel install and a real Lambda-layout artifact, wholly offline."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="package-", dir=temporary))
    environment = dict(
        os.environ,
        PIP_CONFIG_FILE=os.devnull,
        PIP_NO_INDEX="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PIP_CACHE_DIR=str(root / ".cache/pip"),
        TEMP=str(work),
        TMP=str(work),
        TMPDIR=str(work),
    )
    transcript = ["Actual offline packaging checks; fresh directories per invocation.\n"]

    def run(command: list[str]) -> str:
        result = subprocess.run(  # noqa: S603 -- explicitly constructed local commands
            command, cwd=root, env=environment, capture_output=True, text=True, check=False
        )
        transcript.append(
            f"\n$ {' '.join(command)}\n{result.stdout}{result.stderr}"
            f"exit_code={result.returncode}\n"
        )
        if result.returncode:
            raise RuntimeError("offline packaging check failed")
        return result.stdout

    destination = root / "docs/validation/package.txt"
    try:
        wheels = work / "wheels"
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "-w",
                str(wheels),
                ".",
            ]
        )
        wheel = wheels / "serverless_url_shortener-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel) as archive:
            prefix = "serverless_url_shortener-0.1.0.dist-info/"
            if archive.read(prefix + "licenses/LICENSE") != (root / "LICENSE").read_bytes():
                raise RuntimeError("wheel license differs from approved MIT LICENSE")
            if (
                "License-Expression: MIT"
                not in archive.read(prefix + "METADATA").decode().splitlines()
            ):
                raise RuntimeError("wheel MIT metadata missing")
        clean = work / "clean-venv"
        venv.EnvBuilder(with_pip=True).create(clean)
        scripts = clean / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        entry = scripts / ("url-shortener.exe" if os.name == "nt" else "url-shortener")
        run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)])
        run([str(entry), "--version"])
        run(
            [
                str(python),
                "-I",
                "-c",
                "from shortener.domain import MemoryStore, Shortener; "
                "s=Shortener(MemoryStore()); "
                "link=s.create('https://example.com/docs?ref=demo'); "
                "assert s.resolve(link.code)==link; "
                "print('wheel-only stdlib create/resolve passed')",
            ]
        )
        artifact = work / "lambda-artifact"
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--find-links",
                str(root / ".cache/wheels"),
                "--target",
                str(artifact),
                "-r",
                "src/requirements.txt",
            ]
        )
        shutil.copytree(
            root / "src/shortener",
            artifact / "shortener",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        smoke = work / "artifact_smoke.py"
        smoke.write_text(
            "import socket, sys\nfrom pathlib import Path\n"
            "def blocked(*args, **kwargs): raise RuntimeError('network forbidden')\n"
            "socket.socket.connect=blocked\nsocket.getaddrinfo=blocked\n"
            f"artifact=Path({str(artifact)!r})\nsys.path.insert(0,str(artifact))\n"
            "import boto3, botocore, shortener.aws, shortener.dynamodb\n"
            "for module in (boto3, botocore, shortener.aws, shortener.dynamodb):\n"
            "    assert Path(module.__file__).is_relative_to(artifact)\n"
            "assert shortener.aws._application is None\n"
            "print('Lambda artifact imports its packaged SDK and handler with sockets blocked')\n",
            encoding="utf-8",
        )
        run([str(python), "-I", str(smoke)])
        transcript.append("Approved MIT wheel license/metadata and both artifact checks passed.\n")
    finally:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("".join(transcript), encoding="utf-8")
    print("Offline clean wheel install and SDK-packaged Lambda artifact checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
