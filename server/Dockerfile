# syntax=docker.io/docker/dockerfile:1.19.0@sha256:b6afd42430b15f2d2a4c5a02b919e98a525b785b1aaff16747d2f623364e39b6

FROM ghcr.io/astral-sh/uv:0.11.28@sha256:0f36cb9361a3346885ca3677e3767016687b5a170c1a6b88465ec14aefec90aa AS uv

FROM python:3.13.14-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS builder

ENV PYTHONUNBUFFERED=1
WORKDIR /rpc-gateway-api/

COPY --from=uv /uv /uvx /bin/
ENV PATH="/rpc-gateway-api/.venv/bin:$PATH"
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential python3-dev \
    && rm -rf /var/lib/apt/lists/ \
    && apt-get autoremove -y && apt-get autoclean -y

COPY pyproject.toml uv.lock README.md /rpc-gateway-api/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY ./app /rpc-gateway-api/app
COPY ./jobs /rpc-gateway-api/jobs
COPY ./migrations /rpc-gateway-api/migrations
COPY ./scripts/taskiq_stream_cleanup.py /rpc-gateway-api/scripts/taskiq_stream_cleanup.py

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.13.14-slim-bookworm@sha256:fcbd8dfc2605ba7c2eca646846c5e892b2931e41f6227985154a596f26ab8ed7 AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=18173
ENV HOME=/home/app
ENV UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /rpc-gateway-api/

COPY --from=uv /uv /uvx /bin/
ENV PATH="/rpc-gateway-api/.venv/bin:$PATH"
ENV PYTHONPATH=/rpc-gateway-api

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/app --shell /usr/sbin/nologin --no-log-init app

COPY --from=builder --chown=10001:10001 /rpc-gateway-api /rpc-gateway-api

USER 10001:10001

EXPOSE 18173

CMD ["uv", "run", "--no-sync", "app"]
