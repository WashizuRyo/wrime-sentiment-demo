"""Floci comparison: actual container Lambda inference through a local HTTP API."""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from ecr_images import publish_images, verify_lambda_pulls
from local_auth import access_token

from emulator import create_stack

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local/floci-outputs.json"
STACK = "wrime-floci-app"
REGISTRY_STACK = "wrime-floci-registry"
ENDPOINT = "http://127.0.0.1:4566"


def client(service):
    return boto3.Session(
        aws_access_key_id="floci",
        aws_secret_access_key="floci",
        region_name="ap-northeast-1",
    ).client(
        service,
        endpoint_url=ENDPOINT,
        config=Config(
            inject_host_prefix=False,
            connect_timeout=5,
            read_timeout=120,
            retries={"max_attempts": 0},
        ),
    )


def delete_stack(name):
    cfn = client("cloudformation")
    cfn.delete_stack(StackName=name)
    cfn.get_waiter("stack_delete_complete").wait(
        StackName=name, WaiterConfig={"Delay": 1, "MaxAttempts": 60}
    )


def gateway_base(outputs):
    # Never use CloudFormation's AWS-shaped ApiEndpoint URL: local calls only.
    return f"{ENDPOINT}/execute-api/{outputs['HttpApiId']}/$default"


def request(base, method, text, token=None):
    req = urllib.request.Request(
        f"{base}/predict/{method}",
        data=json.dumps({"text": text}).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def check(outputs):
    token = (
        access_token(client("cognito-idp"), outputs)
        if outputs.get("CognitoClientId")
        else None
    )
    checks = {}
    for method in ("lora", "full"):
        fn = client("lambda").get_function(FunctionName=f"{STACK}-{method}")[
            "Configuration"
        ]
        assert fn["PackageType"] == "Image"
        response = client("lambda").invoke(
            FunctionName=fn["FunctionName"],
            Payload=json.dumps(
                {"body": json.dumps({"text": "今日はとても楽しかった！"})}
            ).encode(),
        )
        assert "FunctionError" not in response
        proxy = json.loads(response["Payload"].read())
        assert proxy["statusCode"] == 200
        prediction = json.loads(proxy["body"])
        assert prediction["model"] == method
        checks[f"lambda_{method}"] = {
            "package_type": fn["PackageType"],
            "function": fn["FunctionName"],
            "direct_invoke": proxy["statusCode"],
            "sentiment": prediction["sentiment"],
        }
    routes = client("apigatewayv2").get_routes(ApiId=outputs["HttpApiId"])["Items"]
    assert sorted(r["RouteKey"] for r in routes) == [
        "POST /predict/full",
        "POST /predict/lora",
    ]
    records = []
    for method in ("lora", "full"):
        for text, truncated in (
            ("今日はとても楽しかった！", False),
            ("最悪な一日だった。", False),
            ("明日は月曜日です。", False),
            ("今日は楽しかった。" * 600, True),
        ):
            status, result = request(gateway_base(outputs), method, text, token)
            assert status == 200, (status, result)
            assert result["model"] == method
            assert set(result["probabilities"]) == {"-2", "-1", "0", "1", "2"}
            assert abs(sum(result["probabilities"].values()) - 1) < 1e-5
            assert str(result["sentiment"]) == max(
                result["probabilities"], key=result["probabilities"].get
            )
            assert result["truncated"] == truncated
            records.append({"model": method, "input_chars": len(text), **result})
    status, _ = request(gateway_base(outputs), "lora", "", token)
    assert status == 400
    checks["empty_input"] = status
    repositories = client("ecr").describe_repositories()["repositories"]
    assert len(repositories) == 2
    checks["ecr_repositories"] = len(repositories)
    try:
        client("amplify").list_apps()
        checks["amplify_api"] = {"status": "available"}
    except ClientError as error:
        checks["amplify_api"] = {
            "status": "unsupported",
            "code": error.response["Error"]["Code"],
        }
    report = {
        "emulator": "floci/floci:2.4.0",
        "endpoint": ENDPOINT,
        "gateway_base": gateway_base(outputs),
        "checks": checks,
        "requests": records,
        "scope": "HTTP API -> container Lambda -> real model. Frontend delivery is tested separately. Real images are pushed to and pulled from Floci ECR before Lambda execution.",
    }
    (ROOT / ".local/floci-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("up", "check", "down", "frontend"))
    args = parser.parse_args()
    if args.action == "frontend":
        outputs = json.loads(STATE.read_text())
        env = dict(
            os.environ,
            WRIME_LOCAL_API_TARGET=gateway_base(outputs),
            VITE_COGNITO_CLIENT_ID=outputs.get("CognitoClientId", ""),
            VITE_COGNITO_ENDPOINT="/auth",
        )
        print(f"Vite proxy -> {env['WRIME_LOCAL_API_TARGET']}", flush=True)
        subprocess.run(
            ["npm", "--prefix", "frontend", "run", "dev"], cwd=ROOT, env=env, check=True
        )
        return
    for attempt in range(30):
        try:
            identity = client("sts").get_caller_identity()
            if identity["Account"] != "000000000000":
                raise RuntimeError("Refusing a non-local account")
            break
        except (ClientError, EndpointConnectionError, OSError):
            if attempt == 29:
                raise
            time.sleep(1)
    cfn = client("cloudformation")
    if args.action == "up":
        images = create_stack(REGISTRY_STACK, "infra/registry.yaml", cfn_client=cfn)
        uris = publish_images(client("ecr"), images)
        outputs = create_stack(
            STACK,
            "infra/app.yaml",
            {
                "LoRAImageUri": uris["LoRAImageRepository"],
                "FullImageUri": uris["FullImageRepository"],
                "EnableHosting": "false",
                "EnableApiAuth": "false",
            },
            cfn_client=cfn,
        )
        STATE.write_text(json.dumps(outputs, indent=2) + "\n")
        check(outputs)
        verify_lambda_pulls()
    elif args.action == "check":
        check(json.loads(STATE.read_text()))
    else:
        for name in (STACK, REGISTRY_STACK):
            delete_stack(name)
        STATE.unlink(missing_ok=True)
        print("Floci stacks deleted")


if __name__ == "__main__":
    main()
