# syntax=docker/dockerfile:1.7

# Cross-compile on the build host's own platform: xx supplies the target's linker and libc,
# so the Rust build never runs under emulation. Build context is the repository root.
FROM --platform=$BUILDPLATFORM tonistiigi/xx:1.9.0 AS xx

FROM --platform=$BUILDPLATFORM rust:1.99-slim-trixie AS builder
COPY --from=xx / /
# hadolint ignore=DL3008
RUN apt-get update \
    && apt-get install -y --no-install-recommends clang lld \
    && rm -rf /var/lib/apt/lists/*
ARG TARGETPLATFORM
# hadolint ignore=DL3008
RUN xx-apt-get update \
    && xx-apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY rust/ ./
RUN xx-cargo build --release --locked \
    && xx-verify "target/$(xx-cargo --print-target-triple)/release/picamera-rs" \
    && cp "target/$(xx-cargo --print-target-triple)/release/picamera-rs" /picamera-rs

FROM debian:trixie-slim

# rpicam-vid ships only in the Raspberry Pi archive; same vendored key as ../Dockerfile.
COPY docker/raspberrypi-archive-keyring.pgp /usr/share/keyrings/raspberrypi-archive-keyring.pgp

# hadolint ignore=DL3008
RUN echo "deb [signed-by=/usr/share/keyrings/raspberrypi-archive-keyring.pgp] http://archive.raspberrypi.com/debian trixie main" \
        > /etc/apt/sources.list.d/raspberrypi.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends rpicam-apps-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --user-group --groups video \
        --no-create-home --shell /usr/sbin/nologin picamera

COPY --from=builder /picamera-rs /usr/local/bin/picamera-rs

# Non-secret defaults only. AUTH_PASSWORD has no default and must be supplied at run time.
ENV RESOLUTION=800x600 \
    FRAMERATE=24

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["picamera-rs", "--healthcheck"]

USER 10001
ENTRYPOINT ["picamera-rs"]
