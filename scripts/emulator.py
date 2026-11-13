"""Only connects to the loopback AWS Emulator with its generated credentials."""
import argparse
import configparser
import json
import hashlib
from pathlib import Path
import time

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local/emulator/9297"
REGION = "ap-northeast-1"
PREFIX = "wrime-local"


def session():
    credentials = configparser.ConfigParser()
    credentials.read(STATE / "emulator_credentials")
    if "default" not in credentials:
        raise RuntimeError("Start docker compose first; emulator credentials are missing")
    key = credentials["default"]["aws_access_key_id"]
    if not key.startswith("EMULATOR"):
        raise RuntimeError("Refusing credentials that do not belong to AWS Emulator")
    return boto3.Session(aws_access_key_id=key,
                         aws_secret_access_key=credentials["default"]["aws_secret_access_key"],
                         aws_session_token=credentials["default"].get("aws_session_token"), region_name=REGION)


def client(service):
    # Explicit credentials, CA, and endpoint; do not use the user's AWS profile.
    return session().client(service, endpoint_url="https://127.0.0.1:9297",
                            verify=str(STATE / "ca.pem"),
                            config=Config(inject_host_prefix=False, connect_timeout=5, read_timeout=30,
                                          retries={"max_attempts": 0}))


def create_stack(name, file, parameters=None):
    cfn = client("cloudformation")
    cfn.create_stack(StackName=name, TemplateBody=(ROOT / file).read_text(),
                     Parameters=[{"ParameterKey": key, "ParameterValue": value} for key, value in (parameters or {}).items()],
                     Capabilities=["CAPABILITY_IAM"])
    for _ in range(60):
        stack = cfn.describe_stacks(StackName=name)["Stacks"][0]
        status = stack["StackStatus"]
        if status == "CREATE_COMPLETE":
            return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}
        if "FAILED" in status or "ROLLBACK" in status:
            events = cfn.describe_stack_events(StackName=name)["StackEvents"]
            raise RuntimeError(json.dumps({"status": status, "events": [
                {k: e.get(k) for k in ("LogicalResourceId", "ResourceStatus", "ResourceStatusReason")}
                for e in events[:10]]}, ensure_ascii=False))
        time.sleep(1)
    raise RuntimeError("Local stack creation timed out")


def seed_control_plane_images(images):
    # Metadata-only empty images: enough to exercise Lambda creation, NOT runnable
    # model images. Never presented as inference verification or pushed to real AWS.
    ecr = client("ecr")
    for uri in images.values():
        name = uri.rsplit("/", 1)[1]
        config = json.dumps({"architecture": "arm64", "os": "linux", "config": {},
                             "rootfs": {"type": "layers", "diff_ids": []}, "history": []}).encode()
        digest = "sha256:" + hashlib.sha256(config).hexdigest()
        upload = ecr.initiate_layer_upload(repositoryName=name)
        ecr.upload_layer_part(repositoryName=name, uploadId=upload["uploadId"],
                              partFirstByte=0, partLastByte=len(config) - 1, layerPartBlob=config)
        ecr.complete_layer_upload(repositoryName=name, uploadId=upload["uploadId"], layerDigests=[digest])
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                    "config": {"mediaType": "application/vnd.docker.container.image.v1+json",
                               "size": len(config), "digest": digest}, "layers": []}
        ecr.put_image(repositoryName=name, imageTag="local", imageManifest=json.dumps(manifest))


def check(outputs):
    report = {"endpoint": "https://127.0.0.1:9297", "account": "000000000000", "checks": {}}
    checks = report["checks"]
    probes = {
        "lambda_lora": lambda: client("lambda").get_function(FunctionName=outputs["LoRAFunctionName"]),
        "lambda_full": lambda: client("lambda").get_function(FunctionName=outputs["FullFunctionName"]),
        "api_routes": lambda: client("apigatewayv2").get_routes(ApiId=outputs["HttpApiId"]),
        "cloudformation_amplify_app": lambda: client("amplify").get_app(appId=outputs["AmplifyAppId"]),
        "ecr_repositories": lambda: client("ecr").describe_repositories(),
    }
    for name, probe in probes.items():
        try:
            result = probe()
            checks[name] = {"status": "available"}
            if name == "api_routes":
                routes = sorted(item["RouteKey"] for item in result["Items"])
                if routes != ["POST /predict/full", "POST /predict/lora"]:
                    raise RuntimeError(f"Unexpected routes: {routes}")
                checks[name]["routes"] = routes
            if name == "ecr_repositories":
                if len(result["repositories"]) != 2:
                    raise RuntimeError("Expected two image repositories")
        except ClientError as error:
            checks[name] = {"status": "unsupported-or-missing", "code": error.response["Error"]["Code"]}
    # Amplify's direct API works even when CloudFormation only declares its app.
    amplify = client("amplify")
    direct_app = None
    try:
        direct_app = amplify.create_app(name="wrime-local-api-probe", platform="WEB")["app"]["appId"]
        amplify.get_app(appId=direct_app)
        checks["direct_amplify_api"] = {"status": "available"}
    except ClientError as error:
        checks["direct_amplify_api"] = {"status": "unsupported", "code": error.response["Error"]["Code"]}
    finally:
        if direct_app:
            amplify.delete_app(appId=direct_app)
    try:
        result = client("lambda").invoke(FunctionName=outputs["LoRAFunctionName"],
                                          Payload=json.dumps({"body": '{"text":"テスト"}'}).encode())
        payload = result["Payload"].read().decode()
        checks["container_invoke"] = {"status": "function-error" if "FunctionError" in result else "returned",
                                       "payload": payload[:500]}
    except ClientError as error:
        checks["container_invoke"] = {"status": "unsupported", "code": error.response["Error"]["Code"],
                                       "message": error.response["Error"].get("Message", "")[:500]}
    report["note"] = "This report covers control-plane APIs. Real inference uses backend.local, not Emulator Lambda execution."
    (ROOT / ".local/emulator-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    for name in ("lambda_lora", "lambda_full", "api_routes", "ecr_repositories"):
        if checks[name]["status"] != "available":
            raise RuntimeError(f"Required control-plane check failed: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["up", "check", "down"])
    args = parser.parse_args()
    identity = client("sts").get_caller_identity()
    if identity["Account"] != "000000000000":
        raise RuntimeError("Refusing a non-emulator account")
    state_file = ROOT / ".local/stack-outputs.json"
    if args.action == "up":
        images = create_stack(PREFIX + "-registry", "infra/registry.yaml")
        seed_control_plane_images(images)
        outputs = create_stack(PREFIX + "-app", "infra/app.yaml", {
            "LoRAImageUri": images["LoRAImageRepository"] + ":local",
            "FullImageUri": images["FullImageRepository"] + ":local",
        })
        state_file.write_text(json.dumps(outputs, indent=2) + "\n")
        check(outputs)
    elif args.action == "check":
        check(json.loads(state_file.read_text()))
    else:
        cfn = client("cloudformation")
        for name in (PREFIX + "-app", PREFIX + "-registry"):
            try:
                cfn.delete_stack(StackName=name)
                cfn.get_waiter("stack_delete_complete").wait(StackName=name, WaiterConfig={"Delay": 1, "MaxAttempts": 60})
            except ClientError as error:
                if "does not exist" not in str(error):
                    raise
        state_file.unlink(missing_ok=True)
        print("Local emulator stacks deleted")


if __name__ == "__main__":
    main()
