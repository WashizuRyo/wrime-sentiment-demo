import base64
import json

import pytest
from fastapi.testclient import TestClient

from backend.handler import handle
from backend.inference import ModelUnavailable
from backend.local import app


class RecordingPredictor:
    def __init__(self):
        self.calls = []

    def predict(self, text, method):
        self.calls.append((text, method))
        return {"sentiment": 2, "model": method}


@pytest.mark.parametrize(
    "body",
    [
        "",
        "{",
        "[]",
        "null",
        '{"text":null}',
        '{"text":42}',
        '{"text":"   "}',
        json.dumps({"text": "あ" * 10001}),
    ],
)
def test_invalid_requests_never_reach_inference(body):
    engine = RecordingPredictor()
    assert handle({"body": body}, "lora", engine)["statusCode"] == 400
    assert engine.calls == []


def test_gateway_base64_body_and_classification_method():
    engine = RecordingPredictor()
    event = {
        "body": base64.b64encode('{"text":"楽しかった"}'.encode()).decode(),
        "isBase64Encoded": True,
    }
    result = handle(event, "full", engine)
    assert result["statusCode"] == 200
    assert engine.calls == [("楽しかった", "full")]
    assert json.loads(result["body"]) == {"sentiment": 2, "model": "full"}


def test_unknown_model_does_not_load_weights():
    engine = RecordingPredictor()
    assert handle({"body": '{"text":"テスト"}'}, "other", engine)["statusCode"] == 404
    assert engine.calls == []


def test_missing_model_is_actionable_without_leaking_filesystem():
    class Missing:
        def predict(self, *args):
            raise ModelUnavailable("private/path")

    result = handle({"body": '{"text":"テスト"}'}, "lora", Missing())
    assert result["statusCode"] == 503
    assert "private/path" not in result["body"]


def test_http_adapter_rejects_oversize_stream_before_inference():
    with TestClient(app) as client:
        result = client.post("/predict/lora", content=b"x" * 65537)
    assert result.status_code == 413
