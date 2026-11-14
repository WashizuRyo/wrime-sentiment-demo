"""Run a small AWS CLI benchmark and always remove this run's AWS resources.

Build wrime-lambda-benchmark:local first. Results stay under .local/lambda-benchmark.
No public endpoint, provisioned concurrency, EC2, or scheduled invocations.
"""

import base64
import json
import math
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".local/lambda-benchmark"
REGION = os.environ.get("AWS_REGION", "ap-northeast-1")
AWS = shutil.which("aws") or str(Path.home() / ".local/bin/aws")
NAME = "wrime-bench-" + uuid.uuid4().hex[:10]
GROUP = "/aws/lambda/" + NAME
DOCKER_CONFIG = OUT / (NAME + "-docker")


def aws(*args, allow_missing=False):
    p = subprocess.run(
        [AWS, "--region", REGION, "--output", "json", *args],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "AWS_PAGER": "", "AWS_MAX_ATTEMPTS": "3"},
    )
    if p.returncode:
        if allow_missing and any(
            s in p.stderr
            for s in (
                "ResourceNotFoundException",
                "RepositoryNotFoundException",
                "NoSuchEntity",
            )
        ):
            return None
        raise RuntimeError(p.stderr.strip())
    return json.loads(p.stdout) if p.stdout.strip() else {}


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def invoke(cycle, index, text, expected):
    path = OUT / f"cycle-{cycle}-invoke-{index}.json"
    start = time.perf_counter()
    meta = aws(
        "lambda",
        "invoke",
        "--function-name",
        NAME,
        "--invocation-type",
        "RequestResponse",
        "--log-type",
        "Tail",
        "--cli-read-timeout",
        "180",
        "--cli-connect-timeout",
        "15",
        "--payload",
        json.dumps({"text": text}, ensure_ascii=False),
        str(path),
    )
    wall_ms = (time.perf_counter() - start) * 1000
    log = base64.b64decode(meta.get("LogResult", "")).decode()
    (OUT / f"cycle-{cycle}-invoke-{index}.log").write_text(log)
    result = json.loads(path.read_text())
    record = {
        "cycle": cycle,
        "index": index,
        "client_ms": round(wall_ms, 2),
        "result": result,
        "log": log,
        "status": meta.get("StatusCode"),
    }
    # Persist errors too, before validating the response.
    save(f"cycle-{cycle}-invoke-{index}-record.json", record)
    if meta.get("FunctionError"):
        raise RuntimeError(f"Lambda error: {result}")
    probs = result["probabilities"]
    assert result["sentiment"] == expected, result
    assert math.isclose(sum(probs.values()), 1.0, abs_tol=1e-5)
    assert int(max(probs, key=probs.get)) == result["sentiment"]
    assert result["benchmark"]["first_request_in_environment"] == (index == 0)
    for label, pattern in {
        "duration_ms": r"(?<![\w ])Duration: ([\d.]+) ms",
        "billed_ms": r"Billed Duration: ([\d.]+) ms",
        "init_ms": r"Init Duration: ([\d.]+) ms",
        "max_memory_mb": r"Max Memory Used: (\d+) MB",
    }.items():
        match = re.search(pattern, log)
        record[label] = float(match.group(1)) if match else None
    print(
        json.dumps({k: v for k, v in record.items() if k not in ("log", "result")}),
        flush=True,
    )
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return record


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    identity = aws("sts", "get-caller-identity")
    account = identity["Account"]
    registry = f"{account}.dkr.ecr.{REGION}.amazonaws.com"
    image = f"{registry}/{NAME}:benchmark"
    role_arn = f"arn:aws:iam::{account}:role/{NAME}"
    resources = {
        "name": NAME,
        "region": REGION,
        "image": image,
        "role": role_arn,
        "log_group": GROUP,
        "started_at": time.time(),
    }
    save("resources.json", resources)
    records = []
    created = set()
    try:
        print(f"Creating temporary resources: {NAME} ({REGION})", flush=True)
        aws(
            "iam",
            "create-role",
            "--role-name",
            NAME,
            "--assume-role-policy-document",
            json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "lambda.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                }
            ),
        )
        created.add("role")
        aws("logs", "create-log-group", "--log-group-name", GROUP)
        created.add("logs")
        aws(
            "logs",
            "put-retention-policy",
            "--log-group-name",
            GROUP,
            "--retention-in-days",
            "1",
        )
        aws(
            "iam",
            "put-role-policy",
            "--role-name",
            NAME,
            "--policy-name",
            "benchmark-logs",
            "--policy-document",
            json.dumps(
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
                            "Resource": f"arn:aws:logs:{REGION}:{account}:log-group:{GROUP}:*",
                        }
                    ],
                }
            ),
        )
        aws(
            "ecr",
            "create-repository",
            "--repository-name",
            NAME,
            "--image-scanning-configuration",
            "scanOnPush=false",
        )
        created.add("repo")
        auth = aws("ecr", "get-authorization-token")["authorizationData"][0]
        password = (
            base64.b64decode(auth["authorizationToken"]).decode().split(":", 1)[1]
        )
        DOCKER_CONFIG.mkdir(mode=0o700)
        subprocess.run(
            [
                "docker",
                "--config",
                str(DOCKER_CONFIG),
                "login",
                "--username",
                "AWS",
                "--password-stdin",
                registry,
            ],
            input=password,
            text=True,
            check=True,
            capture_output=True,
        )
        del password, auth
        subprocess.run(
            ["docker", "tag", "wrime-lambda-benchmark:local", image], check=True
        )
        docker_host = (
            os.environ.get("DOCKER_HOST")
            or subprocess.check_output(
                [
                    "docker",
                    "context",
                    "inspect",
                    "--format",
                    "{{.Endpoints.docker.Host}}",
                ],
                text=True,
            ).strip()
        )
        with (OUT / "push.log").open("w") as log:
            subprocess.run(
                [
                    "docker",
                    "--config",
                    str(DOCKER_CONFIG),
                    "--host",
                    docker_host,
                    "push",
                    image,
                ],
                check=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        save("image.json", aws("ecr", "describe-images", "--repository-name", NAME))
        print(
            "Image uploaded; creating ARM64 Lambda (3008 MB, timeout 120s).", flush=True
        )
        for attempt in range(6):
            try:
                aws(
                    "lambda",
                    "create-function",
                    "--function-name",
                    NAME,
                    "--package-type",
                    "Image",
                    "--code",
                    json.dumps({"ImageUri": image}),
                    "--role",
                    role_arn,
                    "--architectures",
                    "arm64",
                    "--memory-size",
                    "3008",
                    "--timeout",
                    "120",
                    "--description",
                    "Temporary WRIME Gemma 270M cold-start benchmark; delete after run",
                )
                created.add("function")
                break
            except RuntimeError as e:
                if "cannot be assumed by Lambda" not in str(e) or attempt == 5:
                    raise
                time.sleep(5)
        aws("lambda", "wait", "function-active-v2", "--function-name", NAME)
        save(
            "configuration.json",
            aws("lambda", "get-function-configuration", "--function-name", NAME),
        )
        for cycle in range(3):
            if cycle:
                # A fresh configuration replaces execution environments; no paid warm capacity.
                aws(
                    "lambda",
                    "update-function-configuration",
                    "--function-name",
                    NAME,
                    "--environment",
                    json.dumps({"Variables": {"BENCHMARK_CYCLE": str(cycle)}}),
                )
                aws("lambda", "wait", "function-updated-v2", "--function-name", NAME)
            cycle_records = []
            for index, (text, expected) in enumerate(
                [
                    ("今日はとても楽しかった！", 2),
                    ("最悪な一日だった", -2),
                    ("明日は月曜日です", 0),
                ]
            ):
                record = invoke(cycle, index, text, expected)
                records.append(record)
                cycle_records.append(record)
                save("results.json", records)
            ids = {r["result"]["benchmark"]["environment_id"] for r in cycle_records}
            assert len(ids) == 1, "Warm requests did not reuse the same environment"
        assert len({r["result"]["benchmark"]["environment_id"] for r in records}) == 3
        print(
            "All 9 inferences validated across 3 fresh execution environments.",
            flush=True,
        )
    finally:
        print("Deleting this run's AWS resources...", flush=True)
        errors = []
        cleanup = [
            ("function", ("lambda", "delete-function", "--function-name", NAME)),
            (
                "repo",
                ("ecr", "delete-repository", "--repository-name", NAME, "--force"),
            ),
            ("logs", ("logs", "delete-log-group", "--log-group-name", GROUP)),
            (
                "role",
                (
                    "iam",
                    "delete-role-policy",
                    "--role-name",
                    NAME,
                    "--policy-name",
                    "benchmark-logs",
                ),
            ),
            ("role", ("iam", "delete-role", "--role-name", NAME)),
        ]
        for kind, args in cleanup:
            if kind in created:
                try:
                    aws(*args, allow_missing=True)
                except (RuntimeError, OSError) as e:
                    errors.append(str(e))
        shutil.rmtree(DOCKER_CONFIG, ignore_errors=True)
        resources.update({"cleanup_errors": errors, "finished_at": time.time()})
        save("resources.json", resources)
        if errors:
            raise RuntimeError(f"Cleanup requires attention: {errors}")
        print("Temporary AWS resources deleted.", flush=True)


if __name__ == "__main__":
    main()
