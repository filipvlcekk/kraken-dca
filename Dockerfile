FROM python:3.12-slim-bookworm@sha256:8a7e7cc04fd3e2bd787f7f24e22d5d119aa590d429b50c95dfe12b3abe52f48b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN set -eux; \
    apt-get update; \
    apt-get install --yes --no-install-recommends cron; \
    rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    groupadd --gid 10001 krakendca; \
    useradd --uid 10001 --gid 10001 --groups crontab --create-home --shell /usr/sbin/nologin krakendca

WORKDIR /app

COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.txt && rm -f /tmp/requirements.txt

COPY --chown=krakendca:krakendca krakendca/ /app/krakendca/
COPY --chown=krakendca:krakendca config-sample.yaml /app/config.yaml
COPY --chown=krakendca:krakendca __main__.py /app/__main__.py

RUN set -eux; \
    touch /app/orders.csv; \
    chown -R krakendca:krakendca /app; \
    mkdir -p /var/run; \
    touch /var/run/crond.pid; \
    chown krakendca:krakendca /var/run/crond.pid

COPY crontab /tmp/kraken-dca.cron
RUN set -eux; \
    chmod 0600 /tmp/kraken-dca.cron; \
    crontab -u krakendca /tmp/kraken-dca.cron; \
    rm -f /tmp/kraken-dca.cron

USER krakendca

CMD ["cron", "-f"]
