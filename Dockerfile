FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN npm --prefix frontend ci

COPY frontend/index.html frontend/tsconfig.json frontend/tsconfig.app.json frontend/tsconfig.node.json frontend/vite.config.ts /app/frontend/
COPY frontend/src/ /app/frontend/src/
RUN npm --prefix frontend run build

FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN set -eux; \
    apt-get update; \
    apt-get install --yes --no-install-recommends curl; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    groupadd --gid 10001 krakendca; \
    useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin krakendca

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY --chown=krakendca:krakendca krakendca/ /app/krakendca/
COPY --chown=krakendca:krakendca __main__.py /app/__main__.py
COPY --from=frontend-build --chown=krakendca:krakendca /app/frontend/dist/ /app/frontend/

RUN set -eux; \
    touch /app/orders.csv; \
    chown -R krakendca:krakendca /app

USER krakendca

EXPOSE 8080

CMD ["uvicorn", "krakendca.web.app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
