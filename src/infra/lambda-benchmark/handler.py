"""Direct Lambda invocation, with explicit first-request loading measurements."""

import time
import uuid

from backend.inference import Predictor

predictor = Predictor()
environment_id = str(uuid.uuid4())
first_request = True


def handler(event, context):
    global first_request
    start = time.perf_counter()
    cold = first_request
    import_ms = load_ms = 0.0
    if cold:
        import_start = time.perf_counter()
        import torch  # noqa: F401
        import transformers  # noqa: F401

        import_ms = (time.perf_counter() - import_start) * 1000
        load_start = time.perf_counter()
        predictor._load("lora")
        load_ms = (time.perf_counter() - load_start) * 1000
        first_request = False
    result = predictor.predict(event["text"], "lora")
    result["benchmark"] = {
        "first_request_in_environment": cold,
        "environment_id": environment_id,
        "import_ms": round(import_ms, 2),
        "model_load_ms": round(load_ms, 2),
        "handler_ms": round((time.perf_counter() - start) * 1000, 2),
        "aws_request_id": context.aws_request_id,
    }
    return result
