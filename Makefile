.PHONY: setup api frontend build
setup:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -r requirements.lock
	npm --prefix src/frontend ci

api:
	HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false .venv/bin/python -m uvicorn backend.local:app --app-dir src --host 127.0.0.1 --port 8000

frontend:
	npm --prefix src/frontend run dev

build:
	npm --prefix src/frontend run build
