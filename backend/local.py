"""Local HTTP adapter; runs the SAME handler, not an emulated Lambda invocation."""
import json

from fastapi import FastAPI, Request
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from backend.handler import handle

app = FastAPI(title="WRIME local inference")


@app.get("/health")
def health():
    return {"status": "ok", "execution": "local-python", "inference": "real-model"}


@app.post("/predict/{method}")
async def predict(method: str, request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64 * 1024:
            return JSONResponse({"error": "Request body is too large"}, status_code=413)
    event = {
        "version": "2.0", "rawPath": f"/predict/{method}",
        "requestContext": {"http": {"method": "POST"}},
        "body": body.decode("utf-8", errors="replace"), "isBase64Encoded": False,
    }
    result = await run_in_threadpool(handle, event, method)
    return JSONResponse(json.loads(result["body"]), status_code=result["statusCode"], headers=result["headers"])
