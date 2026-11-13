"""Local development Cognito credentials; never put passwords in frontend files."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
USER_FILE = ROOT / ".local/dev-user.json"


def access_token(cognito, outputs):
    user = json.loads(USER_FILE.read_text())
    if user["pool_id"] != outputs["UserPoolId"]:
        raise RuntimeError("Run security setup to create the local demo user")
    result = cognito.initiate_auth(
        ClientId=outputs["CognitoClientId"],
        AuthFlow="USER_PASSWORD_AUTH",
        AuthParameters={"USERNAME": user["username"], "PASSWORD": user["password"]},
    )
    return result["AuthenticationResult"]["AccessToken"]
