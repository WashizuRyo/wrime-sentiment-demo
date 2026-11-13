"""CPU inference for the sentiment analysis API."""

import json
import os
import threading
import time
from pathlib import Path

METHODS = {"lora", "full"}
MAX_CHARS = 10_000
MAX_TOKENS = 512


class ModelUnavailable(RuntimeError):
    pass


class Predictor:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("WRIME_MODEL_ROOT", "models"))
        self._models = {}
        # Bound memory/CPU use and avoid duplicate model loading on concurrent requests.
        self._lock = threading.Lock()

    def _load(self, method):
        if method not in self._models:
            import torch
            from transformers import AutoTokenizer, Gemma3TextForSequenceClassification

            path = self.root / method
            if not (path / "model.safetensors").is_file():
                raise ModelUnavailable("Model files are not prepared")
            torch.set_num_threads(int(os.environ.get("TORCH_NUM_THREADS", "2")))
            tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
            model = Gemma3TextForSequenceClassification.from_pretrained(
                path,
                dtype=torch.float32,
                local_files_only=True,
            ).eval()
            if model.config.num_labels != 5:
                raise ModelUnavailable("Expected a five-class classifier")
            if model.config.id2label != {i: str(i - 2) for i in range(5)}:
                raise ModelUnavailable("Unexpected class mapping")
            model.config.use_cache = False
            manifest = json.loads((path / "manifest.json").read_text())
            self._models[method] = (tokenizer, model, manifest["model_version"])
        return self._models[method]

    def predict(self, text, method):
        if method not in METHODS:
            raise ValueError("Unknown model")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
            raise ValueError(
                "text must be a non-empty string of at most 10000 characters"
            )
        start = time.perf_counter()
        with self._lock:
            import torch

            tokenizer, model, version = self._load(method)
            token_count = len(tokenizer(text, truncation=False)["input_ids"])
            inputs = tokenizer(
                text, truncation=True, max_length=MAX_TOKENS, return_tensors="pt"
            )
            with torch.inference_mode():
                logits = model(**inputs).logits[0]
                probabilities = logits.softmax(dim=-1).tolist()
            return {
                "model": method,
                "model_version": version,
                "sentiment": int(logits.argmax().item()) - 2,
                "probabilities": {str(i - 2): p for i, p in enumerate(probabilities)},
                "truncated": token_count > MAX_TOKENS,
                "elapsed_ms": round((time.perf_counter() - start) * 1000, 1),
            }
