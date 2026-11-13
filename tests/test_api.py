import json

import pytest
from fastapi.testclient import TestClient

import backend.local as api_module
from backend.inference import ModelUnavailable
from backend.local import app


class RecordingPredictor:
    def __init__(self):
        self.calls = []

    def predict(self, text, method):
        self.calls.append((text, method))
        return {"sentiment": 2, "model": method}


@pytest.fixture
def api(monkeypatch):
    engine = RecordingPredictor()
    monkeypatch.setattr(api_module, "predictor", engine)
    with TestClient(app) as client:
        yield client, engine


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
def test_invalid_requests_never_reach_inference(api, body):
    client, engine = api
    result = client.post("/predict/lora", content=body)
    assert result.status_code == 400
    assert engine.calls == []


def test_utf8_text_and_model_selection(api):
    client, engine = api
    result = client.post("/predict/full", json={"text": "楽しかった"})
    assert result.status_code == 200
    assert engine.calls == [("楽しかった", "full")]
    assert result.json() == {"sentiment": 2, "model": "full"}
    assert result.headers["cache-control"] == "no-store"


def test_unknown_model_does_not_load_weights(api):
    client, engine = api
    assert client.post("/predict/other", json={"text": "テスト"}).status_code == 404
    assert engine.calls == []


def test_missing_model_does_not_leak_filesystem(api, monkeypatch):
    client, _ = api

    class Missing:
        def predict(self, *args):
            raise ModelUnavailable("private/path")

    monkeypatch.setattr(api_module, "predictor", Missing())
    result = client.post("/predict/lora", json={"text": "テスト"})
    assert result.status_code == 503
    assert "private/path" not in result.text


def test_oversize_request_does_not_reach_inference(api):
    client, engine = api
    assert client.post("/predict/lora", content=b"x" * 65537).status_code == 413
    assert engine.calls == []
