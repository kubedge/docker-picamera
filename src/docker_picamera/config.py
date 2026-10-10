"""Service configuration, read once from the environment at startup."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

SUPPORTED_ROTATIONS = (0, 180)

_RESOLUTION = re.compile(r"^(\d+)x(\d+)$")
_DIGITS = re.compile(r"^\d+$")


class ConfigError(ValueError):
    """A setting is missing or malformed. The message starts with the variable's name."""


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    width: int
    height: int
    framerate: int
    rotation: int
    hflip: bool
    vflip: bool


# docker-picamera-example: the upstream picamera recipe's fixed settings, no credentials.
EXAMPLE_CONFIG = Config(
    username="",
    password="",
    width=640,
    height=480,
    framerate=24,
    rotation=0,
    hflip=False,
    vflip=False,
)


def load_config(environ: Mapping[str, str]) -> Config:
    """Build a Config from environment variables; raise ConfigError on the first bad one."""
    username = environ.get("AUTH_USERNAME", "pi")
    if not username:
        raise ConfigError("AUTH_USERNAME: must not be empty")
    password = environ.get("AUTH_PASSWORD", "")
    if not password:
        raise ConfigError("AUTH_PASSWORD: must be set to a non-empty value")

    raw_resolution = environ.get("RESOLUTION", "800x600")
    match = _RESOLUTION.match(raw_resolution)
    if not match or int(match[1]) == 0 or int(match[2]) == 0:
        raise ConfigError(
            f"RESOLUTION: expected <width>x<height> with positive integers, got {raw_resolution!r}"
        )

    framerate = _positive_int(environ, "FRAMERATE", "24")

    raw_rotation = environ.get("ROTATE", "0")
    if not _DIGITS.match(raw_rotation) or int(raw_rotation) not in SUPPORTED_ROTATIONS:
        raise ConfigError(f"ROTATE: only 0 and 180 are supported, got {raw_rotation!r}")

    return Config(
        username=username,
        password=password,
        width=int(match[1]),
        height=int(match[2]),
        framerate=framerate,
        rotation=int(raw_rotation),
        hflip=_flag(environ, "HFLIP"),
        vflip=_flag(environ, "VFLIP"),
    )


DEFAULT_PORT = 8000


def load_port(environ: Mapping[str, str]) -> int:
    """`PORT`, default 8000: the TCP port the service listens on."""
    raw = environ.get("PORT", str(DEFAULT_PORT))
    if not _DIGITS.match(raw) or not 1 <= int(raw) <= 65535:
        raise ConfigError(f"PORT: expected a port number 1-65535, got {raw!r}")
    return int(raw)


def _positive_int(environ: Mapping[str, str], name: str, default: str) -> int:
    raw = environ.get(name, default)
    if not _DIGITS.match(raw) or int(raw) == 0:
        raise ConfigError(f"{name}: expected a positive integer, got {raw!r}")
    return int(raw)


def _flag(environ: Mapping[str, str], name: str) -> bool:
    raw = environ.get(name, "false")
    if raw.lower() not in ("true", "false"):
        raise ConfigError(f"{name}: expected true or false, got {raw!r}")
    return raw.lower() == "true"
