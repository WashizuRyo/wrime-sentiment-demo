.PHONY: security-up security-check security-down security-browser security-ci-deploy security-ci-watch setup emulator-up emulator-check emulator-down api frontend test smoke floci-images floci-up floci-check floci-down frontend-floci
setup:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -r requirements.lock
	npm --prefix frontend ci

emulator-up:
	mkdir -p .local/emulator
	docker compose up -d --build
	.venv/bin/python scripts/wait_emulator.py
	.venv/bin/python scripts/emulator.py up

emulator-check:
	.venv/bin/python scripts/emulator.py check

emulator-down:
	.venv/bin/python scripts/emulator.py down
	docker compose down

api:
	HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false .venv/bin/python -m uvicorn backend.local:app --host 127.0.0.1 --port 8000

frontend:
	npm --prefix frontend run dev

test:
	.venv/bin/python -m pytest -q
	.venv/bin/cfn-lint infra/registry.yaml infra/app.yaml
	npm --prefix frontend run build

smoke:
	.venv/bin/python scripts/smoke.py

floci-images:
	docker build --platform linux/arm64 --provenance=false --build-arg MODEL_METHOD=lora -f backend/Dockerfile -t wrime-lora:local .
	docker build --platform linux/arm64 --provenance=false --build-arg MODEL_METHOD=full -f backend/Dockerfile -t wrime-full:local .

floci-up:
	docker compose -f compose.floci.yaml up -d
	.venv/bin/python scripts/floci.py up

floci-check:
	.venv/bin/python scripts/floci.py check

frontend-floci:
	.venv/bin/python scripts/floci.py frontend

floci-down:
	.venv/bin/python scripts/floci.py down
	docker compose -f compose.floci.yaml --profile security down

security-up:
	.venv/bin/python scripts/security_setup.py

security-check:
	.venv/bin/python scripts/security_check.py
	npm --prefix frontend run test:secure

security-down:
	docker compose -f compose.floci.yaml --profile security stop web

security-browser:
	cd frontend && node security-browser.mjs

security-ci-deploy:
	.venv/bin/python scripts/deploy_ci.py

security-ci-watch:
	.venv/bin/python scripts/deploy_ci.py --watch
