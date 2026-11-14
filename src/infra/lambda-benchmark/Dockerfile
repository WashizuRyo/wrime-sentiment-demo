FROM public.ecr.aws/lambda/python:3.12

# Use the CPU index explicitly to exclude large CUDA dependencies.
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers==5.14.1
COPY backend/__init__.py backend/inference.py ${LAMBDA_TASK_ROOT}/backend/
COPY infra/lambda-benchmark/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY --chmod=755 models/lora/ ${LAMBDA_TASK_ROOT}/models/lora/
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HOME=/tmp/huggingface \
    TOKENIZERS_PARALLELISM=false TORCH_NUM_THREADS=2 OMP_NUM_THREADS=2
CMD ["handler.handler"]
