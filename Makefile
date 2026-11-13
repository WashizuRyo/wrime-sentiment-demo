.PHONY: setup api frontend test smoke
setup:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -r requirements.lock
	npm --prefix frontend ci

api:
	HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false .venv/bin/python -m uvicorn backend.local:app --host 127.0.0.1 --port 8000

frontend:
	npm --prefix frontend run dev

test:
	.venv/bin/python -m pytest -q
	npm --prefix frontend run build

smoke:
	.venv/bin/python scripts/smoke.py
