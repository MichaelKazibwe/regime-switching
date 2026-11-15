FROM python:3.12.16-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/paper-cache

WORKDIR /app

COPY requirements-paper.hashed.lock ./requirements-paper.hashed.lock
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements-paper.hashed.lock \
    && python -m pip check

COPY . ./
ARG PAPER_CODE_REVISION
ENV PAPER_CODE_REVISION=${PAPER_CODE_REVISION}
RUN python -m paper_release verify \
    && python -c 'import json, os; assert json.load(open("release-manifest.json"))["source_commit"] == os.environ["PAPER_CODE_REVISION"], "Image revision must match manifest"'
RUN mkdir -p /app/var \
    && chown -R 10001:10001 /app

USER 10001:10001
CMD ["python", "-m", "paper_service"]
