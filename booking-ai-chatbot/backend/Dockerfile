FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install -e .

ARG EMBED_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ARG EMBED_MODEL_VERSION=multilingual-minilm-l12-v2-1
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL_NAME}').save('/opt/models/embedding')"

ENV EMBED_MODEL_NAME=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV EMBED_MODEL_PATH=/opt/models/embedding
ENV EMBED_MODEL_VERSION=${EMBED_MODEL_VERSION}

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
