"""API Gateway HTTP API v2 Lambda proxy handler. No AWS SDK calls here."""

import base64
import binascii
import json
import logging
import os

from backend.inference import METHODS, ModelUnavailable, Predictor

predictor = Predictor()
logger = logging.getLogger(__name__)


def response(status, payload):
    return {
        "statusCode": status,
        "headers": {
            "content-type": "application/json; charset=utf-8",
            "cache-control": "no-store",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }


def handle(event, method, engine=None):
    if method not in METHODS:
        return response(404, {"error": "Unknown model"})
    try:
        body = event.get("body") or ""
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body, validate=True).decode("utf-8")
        if len(body.encode("utf-8")) > 64 * 1024:
            return response(413, {"error": "Request body is too large"})
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError("Expected a JSON object")
        text = payload.get("text")
        # Validate even when the engine is replaced in tests.
        if not isinstance(text, str) or not text.strip() or len(text) > 10_000:
            raise ValueError(
                "text must be a non-empty string of at most 10000 characters"
            )
    except (ValueError, TypeError, UnicodeError, binascii.Error):
        return response(
            400,
            {
                "error": "Provide a JSON object with non-empty text (max 10000 characters)"
            },
        )
    try:
        return response(200, (engine or predictor).predict(text, method))
    except ModelUnavailable:
        return response(
            503, {"error": "Model is not prepared. Run the model preparation step."}
        )
    except Exception:  # noqa: BLE001 - sanitize errors at the API boundary
        # Do not log the request text, exception message, or model filesystem paths.
        logger.error("Inference failed")
        return response(500, {"error": "Inference failed"})


def lambda_handler(event, context):
    return handle(event, os.environ.get("MODEL_METHOD", ""))
