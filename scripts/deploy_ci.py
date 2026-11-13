"""Deploy this repository's successful GitHub build to local HTTPS hosting."""

import argparse
import hashlib
import json
import shutil
import ssl
import subprocess
import tempfile
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "WashizuRyo/wrime-sentiment-demo"
STATE = ROOT / ".local/security/deployment.json"


def gh(*args):
    return subprocess.check_output(
        ["gh", *args, "--repo", REPOSITORY], text=True, cwd=ROOT
    )


def deploy(run_id):
    run = json.loads(
        gh(
            "run",
            "view",
            str(run_id),
            "--json",
            "databaseId,headSha,headBranch,conclusion,workflowName",
        )
    )
    if run["conclusion"] != "success" or run["workflowName"] != "Checks":
        raise RuntimeError("Only successful Checks workflow artifacts can be deployed")
    staging = Path(tempfile.mkdtemp(prefix="ci-artifact-", dir=ROOT / ".local"))
    try:
        subprocess.run(
            [
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                REPOSITORY,
                "--name",
                "frontend-dist",
                "--dir",
                str(staging),
            ],
            cwd=ROOT,
            check=True,
        )
        # No npm hooks or artifact executables are run. Only static files are deployed.
        subprocess.run(
            [
                str(ROOT / ".venv/bin/python"),
                "scripts/security_setup.py",
                "--artifact-dir",
                str(staging),
            ],
            cwd=ROOT,
            check=True,
        )
        source = (staging / "index.html").read_bytes()
        published = (ROOT / ".local/security/site/index.html").read_bytes()
        if source != published:
            raise RuntimeError("Deployed HTML differs from the GitHub artifact")
        context = ssl.create_default_context(
            cafile=str(ROOT / ".local/security/certs/ca.crt")
        )
        for attempt in range(30):
            try:
                with urllib.request.urlopen(
                    "https://localhost:8443", context=context, timeout=2
                ) as response:
                    served = response.read()
                break
            except OSError:
                if attempt == 29:
                    raise
                time.sleep(1)
        if served != source:
            raise RuntimeError("HTTPS response differs from the GitHub artifact")
        metadata = {
            "repository": REPOSITORY,
            "run_id": run_id,
            "commit": run["headSha"],
            "branch": run["headBranch"],
            "index_sha256": hashlib.sha256(source).hexdigest(),
            "deployed_at": datetime.now(UTC).isoformat(),
            "source": "github-actions-artifact",
        }
        STATE.write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2), flush=True)
    finally:
        shutil.rmtree(staging)


def latest(branch):
    runs = json.loads(
        gh(
            "run",
            "list",
            "--workflow",
            "checks.yaml",
            "--branch",
            branch,
            "--status",
            "success",
            "--limit",
            "1",
            "--json",
            "databaseId",
        )
    )
    return runs[0]["databaseId"] if runs else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=int)
    parser.add_argument("--branch", default="feat/local-aws-emulator")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll this branch every 30 seconds and deploy new successful builds",
    )
    args = parser.parse_args()
    if args.run_id and args.watch:
        parser.error("Choose --run-id or --watch")
    if not args.watch:
        run = args.run_id or latest(args.branch)
        if not run:
            raise RuntimeError("No successful build found")
        deploy(run)
        return
    print(f"Watching {REPOSITORY}:{args.branch}; local deployment only", flush=True)
    while True:
        try:
            run = latest(args.branch)
            previous = (
                json.loads(STATE.read_text()).get("run_id") if STATE.exists() else None
            )
            if run and run != previous:
                deploy(run)
        except (RuntimeError, subprocess.CalledProcessError):
            print("Build lookup/deployment failed; retrying in 30 seconds", flush=True)
        time.sleep(30)


if __name__ == "__main__":
    main()
