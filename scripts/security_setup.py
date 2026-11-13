"""Configure local JWT auth and build an HTTPS static deployment. No real AWS calls."""

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from botocore.exceptions import ClientError
from floci import client
from local_auth import USER_FILE

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / ".local/security"


def configure_auth():
    cfn = client("cloudformation")
    images = {
        method: client("lambda").get_function(FunctionName=f"wrime-floci-app-{method}")[
            "Code"
        ]["ImageUri"]
        for method in ("lora", "full")
    }
    try:
        cfn.update_stack(
            StackName="wrime-floci-app",
            TemplateBody=(ROOT / "infra/app.yaml").read_text(),
            Parameters=[
                {"ParameterKey": k, "ParameterValue": v}
                for k, v in {
                    "LoRAImageUri": images["lora"],
                    "FullImageUri": images["full"],
                    "EnableHosting": "false",
                    "EnableApiAuth": "true",
                    "AuthIssuerBaseUrl": "http://127.0.0.1:4566",
                    "FrontendOrigin": "https://localhost:8443",
                }.items()
            ],
            Capabilities=["CAPABILITY_IAM"],
        )
    except ClientError as error:
        if "No updates are to be performed" not in str(error):
            raise
    for _ in range(60):
        stack = cfn.describe_stacks(StackName="wrime-floci-app")["Stacks"][0]
        if stack["StackStatus"] == "UPDATE_COMPLETE":
            break
        if "ROLLBACK" in stack["StackStatus"] or "FAILED" in stack["StackStatus"]:
            raise RuntimeError(f"Auth stack update failed: {stack['StackStatus']}")
        time.sleep(1)
    else:
        raise RuntimeError("Auth stack update timed out")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    if not outputs.get("CognitoClientId"):
        raise RuntimeError("Cognito client was not created")
    (ROOT / ".local/floci-outputs.json").write_text(
        json.dumps(outputs, indent=2) + "\n"
    )
    return outputs


def provision_user(outputs):
    cognito = client("cognito-idp")
    user = json.loads(USER_FILE.read_text()) if USER_FILE.exists() else {}
    if user.get("pool_id") != outputs["UserPoolId"]:
        user = {
            "pool_id": outputs["UserPoolId"],
            "username": "demo",
            "password": "Wrime!" + secrets.token_urlsafe(24) + "9",
        }
        try:
            cognito.admin_create_user(
                UserPoolId=user["pool_id"],
                Username=user["username"],
                MessageAction="SUPPRESS",
            )
        except cognito.exceptions.UsernameExistsException:
            pass
        cognito.admin_set_user_password(
            UserPoolId=user["pool_id"],
            Username=user["username"],
            Password=user["password"],
            Permanent=True,
        )
        fd = os.open(USER_FILE, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as stream:
            json.dump(user, stream)
    print("Local login credentials saved in .local/dev-user.json (not published)")


def certificates():
    certs = DIRECTORY / "certs"
    certs.mkdir(parents=True, exist_ok=True)
    if not (certs / "server.crt").exists():

        def openssl(*args):
            subprocess.run(
                ["openssl", *args], cwd=certs, check=True, capture_output=True
            )

        previous = os.umask(0o077)
        try:
            openssl(
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "7",
                "-subj",
                "/CN=WRIME Local CA",
                "-keyout",
                "ca.key",
                "-out",
                "ca.crt",
            )
            openssl(
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                "/CN=localhost",
                "-keyout",
                "server.key",
                "-out",
                "server.csr",
            )
            (certs / "extensions.cnf").write_text(
                "subjectAltName=DNS:localhost,DNS:app.wrime.test,DNS:api.wrime.test,IP:127.0.0.1\nextendedKeyUsage=serverAuth\n"
            )
            openssl(
                "x509",
                "-req",
                "-in",
                "server.csr",
                "-CA",
                "ca.crt",
                "-CAkey",
                "ca.key",
                "-CAcreateserial",
                "-days",
                "7",
                "-extfile",
                "extensions.cnf",
                "-out",
                "server.crt",
            )
        finally:
            os.umask(previous)
    public = subprocess.check_output(
        ["openssl", "x509", "-in", str(certs / "server.crt"), "-pubkey", "-noout"]
    )
    der = subprocess.run(
        ["openssl", "pkey", "-pubin", "-outform", "DER"],
        input=public,
        capture_output=True,
        check=True,
    ).stdout
    (DIRECTORY / "cert-spki.txt").write_text(
        base64.b64encode(hashlib.sha256(der).digest()).decode()
    )
    # Only save a local CA file. Do not install it in the OS trust store.


def deploy(outputs, artifact=None):
    if not artifact:
        subprocess.run(
            ["npm", "--prefix", "frontend", "run", "build"], cwd=ROOT, check=True
        )
    source = Path(artifact) if artifact else ROOT / "frontend/dist"
    if not (source / "index.html").is_file():
        raise RuntimeError("Static build has no index.html")
    site = DIRECTORY / "site"
    site.mkdir(parents=True, exist_ok=True)
    # Preserve the bind-mounted directory and old hashed assets for open tabs.
    shutil.copytree(
        source,
        site,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("index.html", "config.json"),
    )
    config = {
        "apiBaseUrl": "https://localhost:9443",
        "cognitoClientId": outputs["CognitoClientId"],
        "cognitoEndpoint": "/auth",
    }
    (site / ".config.new").write_text(json.dumps(config) + "\n")
    (site / ".config.new").replace(site / "config.json")
    shutil.copy2(source / "index.html", site / ".index.new")
    (site / ".index.new").replace(site / "index.html")
    api_id = outputs["HttpApiId"]
    if not re.fullmatch(r"[A-Za-z0-9]+", api_id):
        raise RuntimeError("Invalid local API id")
    (DIRECTORY / "Caddyfile").write_text(
        (ROOT / "security/Caddyfile.template").read_text().replace("__API_ID__", api_id)
    )
    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "compose.floci.yaml",
            "--profile",
            "security",
            "up",
            "-d",
            "--force-recreate",
            "web",
        ],
        cwd=ROOT,
        check=True,
    )
    print(
        "Static frontend: https://localhost:8443; cross-origin API: https://localhost:9443"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        help="Use a downloaded CI artifact instead of rebuilding",
    )
    args = parser.parse_args()
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    outputs = configure_auth()
    provision_user(outputs)
    certificates()
    deploy(outputs, args.artifact_dir)


if __name__ == "__main__":
    main()
