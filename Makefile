export PATH := $(HOME)/.local/bin:$(PATH)
export AWS_DEFAULT_REGION := $(or $(AWS_REGION),$(AWS_DEFAULT_REGION),ap-northeast-1)
export AWS_REGION := $(AWS_DEFAULT_REGION)

.PHONY: setup api frontend build infra-check bootstrap deploy invoke destroy
setup:
	uv venv --python 3.12 .venv
	uv pip install --python .venv/bin/python -r requirements.lock
	npm --prefix src/frontend ci
	npm --prefix src/infra ci

api:
	HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false .venv/bin/python -m uvicorn backend.local:app --app-dir src --host 127.0.0.1 --port 8000

frontend:
	npm --prefix src/frontend run dev

build:
	npm --prefix src/frontend run build

infra-check:
	npm --prefix src/infra run check
	npm --prefix src/infra run synth

bootstrap:
	npm --prefix src/infra run cdk -- bootstrap

deploy:
	npm --prefix src/infra run cdk -- deploy

invoke:
	bash scripts/invoke-lambda.sh

destroy:
	npm --prefix src/infra run cdk -- destroy --all
	node scripts/delete-images.mjs
