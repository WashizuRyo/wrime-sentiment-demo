"""Sentiment inference for HTTP and direct Lambda invocation."""

import base64
import binascii
import json

from backend.inference import MAX_CHARS, ModelUnavailable, Predictor

predictor = Predictor()


def response(status, payload):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"},
        "body": json.dumps(payload, ensure_ascii=False),
    }


def handler(event, context):
    # Direct invocation returns the prediction without an HTTP response wrapper.
    if "requestContext" not in event:
        return predictor.predict(event["text"], "lora")
    http = event["requestContext"].get("http", {})
    if http.get("path") != "/predict/lora":
        return response(404, {"error": "Unknown model or path"})
    if http.get("method") != "POST":
        return response(405, {"error": "Use POST"})
    try:
        body = event.get("body") or ""
        body = (
            base64.b64decode(body, validate=True)
            if event.get("isBase64Encoded") else body.encode("utf-8")
        )
        if len(body) > 64 * 1024:
            return response(413, {"error": "Request body is too large"})
        payload = json.loads(body)
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError("Invalid text")
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return response(400, {"error": "Provide non-empty text (max 10000 characters)"})
    try:
        return response(200, predictor.predict(text, "lora"))
    except ModelUnavailable:
        return response(503, {"error": "Model is not prepared"})
    except Exception:
        # Do not expose input text, internal paths or exception details.
        return response(500, {"error": "Inference failed"})
