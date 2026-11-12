# OneMind Core gateway image (amd64 + arm64).
# Build from the REPO ROOT so the optional sdk/schema can be copied in:
#   docker buildx build --platform linux/amd64,linux/arm64 -f core/Dockerfile -t onemind-core:dev .
# Base images are pinned by multi-arch index digest (tag kept for humans).

ARG PYTHON_IMAGE=python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490

FROM ${UV_IMAGE} AS uv

# ---- build: resolve the locked dependencies into a venv -------------------------------------
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY core/pyproject.toml core/uv.lock core/README.md ./
RUN uv sync --frozen --no-dev --extra postgres --no-install-project
COPY core/onemind_core ./onemind_core
RUN uv sync --frozen --no-dev --extra postgres --no-editable

# ---- kubectl for the kubernetes executor (pinned version + sha256 per arch) -----------------
FROM ${PYTHON_IMAGE} AS kubectl
ARG TARGETARCH
ARG KUBECTL_VERSION=v1.37.2
ARG KUBECTL_SHA256_amd64=c04487523e7aa7d1493f7808174c899db93d7a9cf57531420cd76b9bd415f8f4
ARG KUBECTL_SHA256_arm64=fcc16f63186659d9722014b7e02d5fdd2d4e669cb8c0ab66365d7d3b8ba03509
RUN set -eu; \
    python - <<EOF
import hashlib, urllib.request, os
arch = "${TARGETARCH}"
want = {"amd64": "${KUBECTL_SHA256_amd64}", "arm64": "${KUBECTL_SHA256_arm64}"}[arch]
url = f"https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/{arch}/kubectl"
data = urllib.request.urlopen(url, timeout=120).read()
got = hashlib.sha256(data).hexdigest()
assert got == want, f"kubectl sha256 mismatch: {got} != {want}"
open("/kubectl", "wb").write(data)
os.chmod("/kubectl", 0o755)
EOF

# ---- runtime --------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.title="onemind-core" \
      org.opencontainers.image.description="OneMind OS Core gateway (contract poc-v0 section 3)" \
      org.opencontainers.image.source="https://github.com/onemindos/ONEMINDOS" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd --system --gid 10001 onemind \
 && useradd --system --uid 10001 --gid onemind --home-dir /var/lib/onemind --shell /usr/sbin/nologin onemind \
 && mkdir -p /var/lib/onemind /opt/onemind/sdk \
 && chown onemind:onemind /var/lib/onemind
COPY --from=build /opt/venv /opt/venv
COPY --from=kubectl /kubectl /usr/local/bin/kubectl
# sdk/ holds the app manifest schema when the apps stream has published it.
COPY sdk/ /opt/onemind/sdk/
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    ONEMIND_DATA_DIR=/var/lib/onemind \
    ONEMIND_APPS_DIR=/opt/onemind/apps \
    ONEMIND_HOST=0.0.0.0 \
    ONEMIND_PORT=8080
USER 10001:10001
WORKDIR /var/lib/onemind
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status == 200 else 1)"]
ENTRYPOINT ["python", "-m", "onemind_core"]
