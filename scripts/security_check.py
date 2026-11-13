"""TLS, cache, JWT, CORS and real IAM allow/deny checks against local services."""

import base64
import json
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from floci import client
from local_auth import USER_FILE

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "https://localhost:8443"
API = "https://localhost:9443"


def tls_context():
    return ssl.create_default_context(cafile=str(ROOT / ".local/security/certs/ca.crt"))


def http(url, *, method="GET", headers=None, data=None, context=None):
    request = urllib.request.Request(
        url, method=method, headers=headers or {}, data=data
    )
    try:
        response = urllib.request.urlopen(
            request, context=context or tls_context(), timeout=90
        )
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, dict(response.headers), response.read()


def post(token=None, origin=ORIGIN):
    return http(
        API + "/predict/lora",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Origin": origin,
            **({"Authorization": "Bearer " + token} if token else {}),
        },
        data=json.dumps({"text": "今日はとても楽しかった！"}).encode(),
    )


def issued_tokens(outputs, user, client_id=None):
    return client("cognito-idp").initiate_auth(
        ClientId=client_id or outputs["CognitoClientId"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": user["username"], "PASSWORD": user["password"]},
    )["AuthenticationResult"]


def iam_checks():
    iam = client("iam")
    name = "wrime-policy-probe-" + secrets.token_hex(4)
    iam.create_user(UserName=name)
    key = None
    policy_name = "ReadRepositories"
    result = {}
    try:
        key = iam.create_access_key(UserName=name)["AccessKey"]

        def principal(secret=None):
            return boto3.Session(
                aws_access_key_id=key["AccessKeyId"],
                aws_secret_access_key=secret or key["SecretAccessKey"],
                region_name="ap-northeast-1",
            ).client(
                "ecr",
                endpoint_url="http://127.0.0.1:4566",
                config=Config(inject_host_prefix=False, retries={"max_attempts": 0}),
            )

        def denied(call):
            try:
                call()
            except ClientError as error:
                code = error.response["Error"]["Code"]
                assert code in {"AccessDenied", "AccessDeniedException"}, code
                return code
            raise AssertionError("IAM request unexpectedly allowed")

        user = principal()
        result["no_policy"] = denied(user.describe_repositories)
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "ecr:DescribeRepositories",
                    "Resource": "*",
                }
            ],
        }
        iam.put_user_policy(
            UserName=name, PolicyName=policy_name, PolicyDocument=json.dumps(policy)
        )
        result["allowed_read"] = user.describe_repositories()["ResponseMetadata"][
            "HTTPStatusCode"
        ]
        assert result["allowed_read"] == 200
        repo = client("ecr").describe_repositories()["repositories"][0][
            "repositoryName"
        ]
        result["other_read_denied"] = denied(
            lambda: user.list_images(repositoryName=repo)
        )
        try:
            principal("incorrect-local-secret").describe_repositories()
        except ClientError as error:
            code = error.response["Error"]["Code"]
            assert code in {"SignatureDoesNotMatch", "InvalidSignatureException"}, code
            result["wrong_signature"] = code
        else:
            raise AssertionError("Incorrect SigV4 signature was accepted")
        policy["Statement"].append(
            {"Effect": "Deny", "Action": "ecr:DescribeRepositories", "Resource": "*"}
        )
        iam.put_user_policy(
            UserName=name, PolicyName=policy_name, PolicyDocument=json.dumps(policy)
        )
        result["explicit_deny_over_allow"] = denied(user.describe_repositories)
    finally:
        if key:
            iam.delete_access_key(UserName=name, AccessKeyId=key["AccessKeyId"])
        try:
            iam.delete_user_policy(UserName=name, PolicyName=policy_name)
        except iam.exceptions.NoSuchEntityException:
            pass
        iam.delete_user(UserName=name)
    return result


def main():
    outputs = json.loads((ROOT / ".local/floci-outputs.json").read_text())
    user = json.loads(USER_FILE.read_text())
    report = {"origins": {"frontend": ORIGIN, "api": API}, "checks": {}}
    checks = report["checks"]
    for _ in range(30):
        try:
            status, headers, index = http(ORIGIN)
            break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError("HTTPS static server did not start")
    assert status == 200
    checks["trusted_https"] = status
    try:
        http(ORIGIN, context=ssl.create_default_context())
    except urllib.error.URLError as error:
        assert isinstance(error.reason, ssl.SSLCertVerificationError)
        checks["untrusted_ca_rejected"] = True
    else:
        raise AssertionError("Local CA was unexpectedly trusted globally")
    with (
        socket.create_connection(("127.0.0.1", 8443)) as sock,
        tls_context().wrap_socket(sock, server_hostname="app.wrime.test"),
    ):
        checks["local_domain_san"] = True
    try:
        with socket.create_connection(("127.0.0.1", 8443)) as sock:
            tls_context().wrap_socket(sock, server_hostname="wrong.wrime.test")
    except ssl.SSLCertVerificationError:
        checks["wrong_hostname_rejected"] = True
    else:
        raise AssertionError("Wrong TLS hostname was accepted")
    lower = {k.lower(): v for k, v in headers.items()}
    assert lower["cache-control"] == "no-cache"
    etag = lower["etag"]
    assert http(ORIGIN, headers={"If-None-Match": etag})[0] == 304
    checks["html_cache"] = "no-cache and ETag 304"
    import re

    asset = re.search(rb'/assets/[^" ]+\.js', index).group().decode()
    status, asset_headers, _ = http(ORIGIN + asset)
    assert status == 200 and "immutable" in asset_headers.get("Cache-Control", "")
    checks["hashed_asset_cache"] = asset_headers["Cache-Control"]
    assert http(ORIGIN + "/config.json")[1]["Cache-Control"] == "no-store"
    checks["runtime_config_cache"] = "no-store"
    tokens = issued_tokens(outputs, user)
    token = tokens["AccessToken"]
    checks["missing_token"] = post()[0]
    assert checks["missing_token"] == 401
    parts = token.split(".")
    parts[2] = ("A" if parts[2][0] != "A" else "B") + parts[2][1:]
    checks["invalid_signature"] = post(".".join(parts))[0]
    assert checks["invalid_signature"] == 401
    checks["id_token_missing_scope"] = post(tokens["IdToken"])[0]
    assert checks["id_token_missing_scope"] == 403
    status, headers, body = post(token)
    assert status == 200 and json.loads(body)["sentiment"] == 2
    assert headers["Access-Control-Allow-Origin"] == ORIGIN
    checks["valid_access_token"] = status
    for origin, allowed in ((ORIGIN, True), ("https://localhost:8445", False)):
        status, headers, _ = http(
            API + "/predict/lora",
            method="OPTIONS",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert status in (200, 204)
        exposed = headers.get("Access-Control-Allow-Origin") == origin
        assert exposed == allowed, headers
        checks["allowed_preflight" if allowed else "disallowed_preflight"] = {
            "status": status,
            "origin_allowed": exposed,
        }
    cognito = client("cognito-idp")
    other_client = cognito.create_user_pool_client(
        UserPoolId=outputs["UserPoolId"],
        ClientName="wrime-wrong-audience",
        ExplicitAuthFlows=["ALLOW_USER_PASSWORD_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    )["UserPoolClient"]["ClientId"]
    try:
        checks["wrong_audience"] = post(
            issued_tokens(outputs, user, other_client)["AccessToken"]
        )[0]
        assert checks["wrong_audience"] == 401
    finally:
        cognito.delete_user_pool_client(
            UserPoolId=outputs["UserPoolId"], ClientId=other_client
        )
    original = cognito.describe_user_pool_client(
        UserPoolId=outputs["UserPoolId"], ClientId=outputs["CognitoClientId"]
    )["UserPoolClient"]
    shape = cognito.meta.service_model.operation_model(
        "UpdateUserPoolClient"
    ).input_shape.members
    restore = {k: v for k, v in original.items() if k in shape}
    restore["UserPoolId"] = outputs["UserPoolId"]
    short = {
        **restore,
        "AccessTokenValidity": 1,
        "TokenValidityUnits": {
            **original.get("TokenValidityUnits", {}),
            "AccessToken": "seconds",
        },
    }
    try:
        cognito.update_user_pool_client(**short)
        expiring = issued_tokens(outputs, user)["AccessToken"]
    finally:
        cognito.update_user_pool_client(**restore)
    claims = json.loads(base64.urlsafe_b64decode(expiring.split(".")[1] + "==="))
    wait = max(0, claims["exp"] + 1 - time.time())
    if wait > 5:
        raise RuntimeError("Short-lived expiry fixture did not take effect")
    time.sleep(wait)
    checks["expired_token"] = post(expiring)[0]
    assert checks["expired_token"] == 401
    checks["iam"] = iam_checks()
    report["scope"] = (
        "Local TLS and JWT/CORS/IAM checks; not a guarantee of AWS-wide policy or CDN fidelity. No credentials or JWTs are included."
    )
    (ROOT / ".local/security-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
