"""FastAPI endpoints for local sentiment analysis."""

import json
import logging

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from backend.inference import MAX_CHARS, METHODS, ModelUnavailable, Predictor

app = FastAPI(title="WRIME sentiment API")
predictor = Predictor()
logger = logging.getLogger(__name__)


def response(status, payload):
    return JSONResponse(
        payload, status_code=status, headers={"Cache-Control": "no-store"}
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict/{method}")
async def predict(method: str, request: Request):
    if method not in METHODS:
        return response(404, {"error": "Unknown model"})
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64 * 1024:
            return response(413, {"error": "Request body is too large"})
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict):
            raise TypeError("Expected a JSON object")
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError("Invalid text")
    except (ValueError, TypeError):
        return response(400, {"error": "Provide non-empty text (max 10000 characters)"})
    try:
        result = await run_in_threadpool(predictor.predict, text, method)
    except ModelUnavailable:
        return response(
            503, {"error": "Model is not prepared. Run the model preparation step."}
        )
    except Exception:  # noqa: BLE001 - sanitize errors at the API boundary
        logger.error("Inference failed")
        return response(500, {"error": "Inference failed"})
    return response(200, result)
