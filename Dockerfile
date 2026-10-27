# OAK — one image with the FastAPI backend and the built React frontend.
#
#   docker compose up -d --build
#
# The base images are pinned to a patch version and a digest, so a changed image under the same
# tag never slips in. Dependabot keeps both up to date. Behind a registry mirror, set
# registry-mirrors in the Docker daemon instead of changing these lines.

# --- frontend -----------------------------------------------------------------------------------
# The built files are the same on every platform, so this stage always runs natively, also when
# the image is built for arm64 on an amd64 machine.
FROM --platform=$BUILDPLATFORM node:22.23.4-bookworm-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS frontend
WORKDIR /src/frontend
ENV npm_config_fund=false npm_config_audit=false npm_config_update_notifier=false
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- backend dependencies -----------------------------------------------------------------------
FROM python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5 AS backend-deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /src
COPY backend/build-requirements.txt backend/pyproject.toml backend/uv.lock ./
# Only the runtime dependencies, also the indirect ones, exactly as locked in uv.lock and checked
# against their hashes (audit F08). uv itself is pinned by hash and stays in this stage. The
# application code is copied into the final stage, so a code change does not reinstall anything.
RUN python -m pip install --require-hashes -r build-requirements.txt \
    && uv export --locked --no-dev --no-emit-project --format requirements-txt -o requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install --require-virtualenv --require-hashes --no-deps -r requirements.txt

# --- runtime ------------------------------------------------------------------------------------
FROM python:3.13.18-slim-bookworm@sha256:93498f36dc7e24ef233bfdf6cc17d4b8bd32d94ee737143e906460d5f5a914c5 AS runtime

ARG OAK_VERSION=dev
ARG OAK_BUILD_SHA=unknown
ARG OAK_BUILD_DATE=unknown
ARG OAK_BUILD_REF=local

LABEL org.opencontainers.image.title="OAK" \
      org.opencontainers.image.description="Self-hosted Pokémon GO Manager met PGSharp-koppeling" \
      org.opencontainers.image.source="https://github.com/arjancool/oak-pogo" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${OAK_VERSION}" \
      org.opencontainers.image.revision="${OAK_BUILD_SHA}" \
      org.opencontainers.image.created="${OAK_BUILD_DATE}"

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Amsterdam \
    OAK_DATA_DIR=/data \
    OAK_PORT=8080 \
    OAK_FRONTEND_DIR=/app/frontend \
    OAK_BUILD_SHA=${OAK_BUILD_SHA} \
    OAK_BUILD_DATE=${OAK_BUILD_DATE} \
    OAK_BUILD_REF=${OAK_BUILD_REF}

WORKDIR /app
COPY --from=backend-deps /opt/venv /opt/venv
COPY backend/app ./app
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
COPY --from=frontend /src/frontend/dist ./frontend
COPY docker/entrypoint.sh /usr/local/bin/oak-entrypoint
RUN chmod 0755 /usr/local/bin/oak-entrypoint \
    && python -m compileall -q /app/app \
    && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import os, sys, urllib.request; port = os.environ.get('OAK_PORT', '8080'); r = urllib.request.urlopen(f'http://127.0.0.1:{port}/health/ready', timeout=4); sys.exit(0 if r.status == 200 else 1)"]

ENTRYPOINT ["oak-entrypoint"]
CMD ["python", "-m", "app"]
