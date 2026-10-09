"""charts/picamera rendered with `helm template` and checked against the helm-deployment spec.

Skipped when helm is not installed; the chart CI job sets REQUIRE_HELM=1 so it never skips there.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

CHART = Path(__file__).resolve().parent.parent / "charts" / "picamera"
HELM = shutil.which("helm")

if HELM is None:
    if os.environ.get("REQUIRE_HELM") == "1":
        raise RuntimeError("REQUIRE_HELM=1 but helm is not on PATH")
    pytest.skip("helm not installed", allow_module_level=True)


def render(*sets: str) -> subprocess.CompletedProcess[str]:
    args = [str(HELM), "template", "cam", str(CHART)]
    for item in sets:
        args += ["--set", item]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def manifests(*sets: str) -> dict[str, dict[str, Any]]:
    result = render("auth.existingSecret=picamera-auth", *sets)
    assert result.returncode == 0, result.stderr
    docs = [d for d in yaml.safe_load_all(result.stdout) if d]
    return {d["kind"]: d for d in docs}


def container(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    containers = docs["Deployment"]["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    return containers[0]  # type: ignore[no-any-return]


def env(docs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {e["name"]: e.get("value", e.get("valueFrom")) for e in container(docs)["env"]}


def test_rendering_fails_without_the_secret_name() -> None:
    result = render()
    assert result.returncode != 0
    assert "auth.existingSecret" in result.stderr


def test_default_image_is_the_app_version() -> None:
    app_version = yaml.safe_load((CHART / "Chart.yaml").read_text())["appVersion"]
    assert container(manifests())["image"] == f"kubedge1/picamera:{app_version}"


def test_credentials_come_only_from_the_secret() -> None:
    values = env(manifests())
    for name, key in (("AUTH_USERNAME", "username"), ("AUTH_PASSWORD", "password")):
        assert values[name] == {"secretKeyRef": {"name": "picamera-auth", "key": key}}


def test_camera_settings_default_and_override() -> None:
    assert {k: v for k, v in env(manifests()).items() if not k.startswith("AUTH_")} == {
        "RESOLUTION": "800x600",
        "FRAMERATE": "24",
        "ROTATE": "0",
        "HFLIP": "false",
        "VFLIP": "false",
    }
    assert env(manifests("camera.resolution=1280x720"))["RESOLUTION"] == "1280x720"


def test_schedules_only_on_arm64_camera_nodes() -> None:
    selector = manifests()["Deployment"]["spec"]["template"]["spec"]["nodeSelector"]
    assert selector == {"kubernetes.io/arch": "arm64", "picameraInstalled": "true"}


def test_health_probes_on_8000() -> None:
    c = container(manifests())
    for probe in ("livenessProbe", "readinessProbe"):
        assert c[probe]["httpGet"] == {"path": "/healthz", "port": 8000}


def test_host_dev_and_read_only_udev_without_vchiq() -> None:
    docs = manifests()
    spec = docs["Deployment"]["spec"]["template"]["spec"]
    volumes = {v["name"]: v["hostPath"]["path"] for v in spec["volumes"]}
    mounts = {m["mountPath"]: m.get("readOnly", False) for m in container(docs)["volumeMounts"]}
    assert set(volumes.values()) == {"/dev", "/run/udev"}
    assert mounts == {"/dev": False, "/run/udev": True}
    assert "vchiq" not in yaml.safe_dump(docs)


def test_service_and_no_ingress_by_default() -> None:
    docs = manifests()
    assert "Ingress" not in docs
    service = docs["Service"]["spec"]
    assert service["type"] == "NodePort"
    assert service["ports"] == [
        {"name": "http", "port": 9090, "targetPort": "http", "nodePort": 30456}
    ]
    assert container(docs)["ports"] == [{"name": "http", "containerPort": 8000}]


def test_ingress_when_enabled() -> None:
    ingress = manifests("ingress.enabled=true")["Ingress"]
    assert ingress["apiVersion"] == "networking.k8s.io/v1"
