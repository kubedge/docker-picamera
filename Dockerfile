# syntax=docker/dockerfile:1.7

# Build the wheel on the build host's own platform: it is pure Python, so this stage
# never runs under emulation.
FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:0.12.23-python3.13-trixie-slim AS builder
WORKDIR /src
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv build --wheel --out-dir /dist

FROM debian:trixie-slim

# picamera2 and its libcamera bindings ship only as Raspberry Pi apt packages.
# Key: "Raspberry Pi Archive Signing Key", CF8A 1AF5 02A2 AA2D 763B AE7E 82B1 2992 7FA3 303E.
ADD --checksum=sha256:76603890d82a492175caf17aba68dc73acb1189c9fd58ec0c19145dfa3866d56 \
    https://archive.raspberrypi.com/debian/raspberrypi.gpg.key \
    /usr/share/keyrings/raspberrypi-archive-keyring.asc

# Versions come from the trixie suites; pinning each would break on every archive update.
# --no-install-recommends keeps out the Qt/OpenCV preview stack python3-picamera2 recommends.
# hadolint ignore=DL3008
RUN chmod 0644 /usr/share/keyrings/raspberrypi-archive-keyring.asc \
    && echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.asc] http://archive.raspberrypi.com/debian trixie main" \
        > /etc/apt/sources.list.d/raspberrypi.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3-picamera2 python3-venv \
    && rm -rf /var/lib/apt/lists/*

# The venv sees apt's picamera2 through system site packages; the app itself has no
# PyPI dependencies, so --no-deps installs exactly one wheel.
COPY --from=builder /dist/ /tmp/dist/
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --no-deps /tmp/dist/*.whl \
    && rm -rf /tmp/dist \
    && useradd --system --uid 10001 --user-group --groups video \
        --no-create-home --shell /usr/sbin/nologin picamera

# Non-secret defaults only. AUTH_PASSWORD has no default and must be supplied at run time.
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    RESOLUTION=800x600 \
    FRAMERATE=24

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"]

USER picamera
ENTRYPOINT ["docker-picamera"]
