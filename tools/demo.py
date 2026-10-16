"""Run the installed CLI and actual curl requests; never follow target redirects."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    destination = root / "docs" / "validation"
    destination.mkdir(parents=True, exist_ok=True)
    curl = shutil.which("curl.exe" if os.name == "nt" else "curl")
    if curl is None:
        raise RuntimeError("curl is required for the genuine HTTP demo")
    temporary = root / ".tmp"
    temporary.mkdir(exist_ok=True)
    payload = temporary / "demo-request.json"
    payload.write_text(
        json.dumps({"url": "https://example.com/docs?ref=demo", "ttl_seconds": 60}),
        encoding="utf-8",
    )
    # Select an ephemeral loopback port, then launch the actual installed entry point.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    entry = Path(sys.executable).parent / (
        "url-shortener.exe" if os.name == "nt" else "url-shortener"
    )
    command = [str(entry), "--port", str(port)]
    transcript = ["Actual synthetic local HTTP session; curl never uses --location.\n"]
    log_path = temporary / "demo-server.log"
    result_path = temporary / "demo-created.json"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(  # noqa: S603 -- fixed installed local CLI
            command,
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
        )
        try:
            transcript.append(f"\n$ url-shortener --port {port}\n")
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("local CLI exited before readiness")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError("local CLI readiness timeout")

            def run(args: list[str], expected: int) -> str:
                result = subprocess.run(  # noqa: S603 -- fixed curl executable, bounded localhost URL
                    [curl, "--noproxy", "*", "--max-time", "3", "--silent", "--show-error", *args],
                    cwd=root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                transcript.append(
                    "\n$ curl --noproxy '*' --max-time 3 --silent --show-error "
                    + " ".join(args)
                    + f"\n{result.stdout}{result.stderr}\nexit_code={result.returncode}\n"
                )
                if result.returncode != 0:
                    raise RuntimeError("local curl command failed")
                if int(result.stdout.rsplit("\n", 1)[-1]) != expected:
                    raise RuntimeError("unexpected actual HTTP status")
                return result.stdout

            base = f"http://127.0.0.1:{port}"
            run(
                [
                    "-X",
                    "POST",
                    f"{base}/links",
                    "-H",
                    "Content-Type:application/json",
                    "--data-binary",
                    "@.tmp/demo-request.json",
                    "-o",
                    ".tmp/demo-created.json",
                    "-w",
                    "\\n%{http_code}",
                ],
                201,
            )
            created = json.loads(result_path.read_text(encoding="utf-8"))
            transcript.append(
                "Actual response body:\n" + json.dumps(created, sort_keys=True) + "\n"
            )
            path = created["short_path"]
            run(["-i", base + path, "-w", "\\n%{http_code}"], 302)
            run(["-i", f"{base}/r/AAAAAAAAAAAA", "-w", "\\n%{http_code}"], 404)
            run(["-i", f"{base}/links", "-w", "\\n%{http_code}"], 405)
            run(
                [
                    "-i",
                    "-X",
                    "POST",
                    f"{base}/links",
                    "-H",
                    "Content-Type:application/json",
                    "--data-binary",
                    '{"url":"javascript:synthetic"}',
                    "-w",
                    "\\n%{http_code}",
                ],
                400,
            )
        finally:
            process.terminate()
            process.wait(timeout=5)
    transcript.append("\nActual server stdout/stderr:\n" + log_path.read_text(encoding="utf-8"))
    (destination / "local-demo.txt").write_text("".join(transcript), encoding="utf-8")
    print("".join(transcript), end="")
    print("Local demo verified 201, 302, 404, 405 and 400; child server stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
