ARG PYTHON_BASE_IMAGE=python:3.12-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
FROM ${PYTHON_BASE_IMAGE} AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/paper-cache

WORKDIR /app

COPY requirements-paper.hashed.lock ./requirements-paper.hashed.lock
RUN python -m pip install --no-cache-dir --require-hashes --requirement requirements-paper.hashed.lock \
    && python -m pip check

# Compilers and package managers remain in the build stage only.
COPY deploy/runtime/build_sqlite.py ./deploy/runtime/build_sqlite.py
RUN apt-get update && apt-get install --no-install-recommends -y gcc make libc6-dev zlib1g=1:1.3.dfsg+really1.3.1-1+deb13u1 && rm -rf /var/lib/apt/lists/*
ENV LD_LIBRARY_PATH=/usr/local/lib
RUN python deploy/runtime/build_sqlite.py
COPY deploy/runtime/ ./deploy/runtime/
RUN python deploy/runtime/collect_runtime.py && python -c 'import sqlite3; assert sqlite3.sqlite_version=="3.54.1"'

COPY . ./
ARG PAPER_CODE_REVISION
ENV PAPER_CODE_REVISION=${PAPER_CODE_REVISION}
RUN python -m paper_release verify \
    && python -c 'import json, os; assert json.load(open("release-manifest.json"))["source_commit"] == os.environ["PAPER_CODE_REVISION"], "Image revision must match manifest"'
RUN mkdir -p /app/var \
    && chown -R 10001:10001 /app



FROM gcr.io/distroless/cc-debian13:nonroot@sha256:532c7a94f9e96ba9db75eb9388f4227751131c7cb0a411d1a8521af4096135de
COPY --from=build /runtime/ /
COPY --from=build /app/ /app/
ENV PATH=/usr/local/bin LD_LIBRARY_PATH=/usr/local/lib PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp XDG_CACHE_HOME=/tmp/regime-cache
WORKDIR /app
ARG PAPER_CODE_REVISION
ENV PAPER_CODE_REVISION=${PAPER_CODE_REVISION}
USER 10001:10001
CMD ["python", "-m", "paper_service"]
