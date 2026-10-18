FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        default-libmysqlclient-dev \
        pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .
COPY deploy/docker-entrypoint.sh /usr/local/bin/gofinance-entrypoint

RUN chmod 755 /usr/local/bin/gofinance-entrypoint \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R www-data:www-data /app

EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/gofinance-entrypoint"]
