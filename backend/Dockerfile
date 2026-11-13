FROM public.ecr.aws/lambda/python:3.12
ARG MODEL_METHOD
ENV MODEL_METHOD=${MODEL_METHOD} WRIME_MODEL_ROOT=/opt/models HF_HUB_OFFLINE=1 TOKENIZERS_PARALLELISM=false TORCH_NUM_THREADS=2
RUN pip install --no-cache-dir torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir transformers==5.14.1
COPY backend ${LAMBDA_TASK_ROOT}/backend
COPY models/${MODEL_METHOD}/ /opt/models/${MODEL_METHOD}/
CMD ["backend.handler.lambda_handler"]
