FROM public.ecr.aws/lambda/python:3.12

# Use the CPU index explicitly to exclude large CUDA dependencies.
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers==5.14.1
COPY backend/__init__.py backend/inference.py ${LAMBDA_TASK_ROOT}/backend/
COPY backend/lambda/handler.py ${LAMBDA_TASK_ROOT}/handler.py
COPY --chmod=755 models/lora/ ${LAMBDA_TASK_ROOT}/models/lora/
COPY --chmod=755 models/full/ ${LAMBDA_TASK_ROOT}/models/full/
ENV HF_HOME=/tmp/huggingface OMP_NUM_THREADS=2
CMD ["handler.handler"]
