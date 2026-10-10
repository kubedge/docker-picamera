"""charts/picamera-rs against the rust-helm-deployment spec, and against charts/picamera.

Skipped when helm is not installed; the chart CI job sets REQUIRE_HELM=1.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

CHARTS = Path(__file__).resolve().parent.parent / "charts"
HELM = shutil.which("helm")

if HELM is None:
    if os.environ.get("REQUIRE_HELM") == "1":
        raise RuntimeError("REQUIRE_HELM=1 but helm is not on PATH")
    pytest.skip("helm not installed", allow_module_level=True)

VALUES = {
    "auth": {"existingSecret": "picamera-auth"},
    "camera": {"resolution": "1280x720", "framerate": 15, "rotate": 180, "hflip": True},
    "service": {"nodePort": 30457},
    "dashboard": {"externalUrl": "http://kube-node02:30457/stream.mjpg"},
    "ingress": {"enabled": True},
}


def render(chart: str, *sets: str, values: Path | None = None) -> subprocess.CompletedProcess[str]:
    args = [str(HELM), "template", "cam", str(CHARTS / chart)]
    if values:
        args += ["-f", str(values)]
    for item in sets:
        args += ["--set", item]
    return subprocess.run(args, capture_output=True, text=True, check=False)


def docs(chart: str, *sets: str, values: Path | None = None) -> dict[str, dict[str, Any]]:
    if values is None:
        sets = ("auth.existingSecret=picamera-auth", *sets)
    result = render(chart, *sets, values=values)
    assert result.returncode == 0, result.stderr
    return {d["kind"]: d for d in yaml.safe_load_all(result.stdout) if d}


def container(d: dict[str, dict[str, Any]]) -> dict[str, Any]:
    (c,) = d["Deployment"]["spec"]["template"]["spec"]["containers"]
    return c  # type: ignore[no-any-return]


def test_default_image_is_the_app_version() -> None:
    app_version = yaml.safe_load((CHARTS / "picamera-rs" / "Chart.yaml").read_text())["appVersion"]
    assert container(docs("picamera-rs"))["image"] == f"kubedge1/picamera-rs:{app_version}"


def test_rendering_fails_without_the_secret_name() -> None:
    result = render("picamera-rs")
    assert result.returncode != 0
    assert "auth.existingSecret" in result.stderr


def test_memory_request_and_limit_by_default_and_overridable() -> None:
    resources = container(docs("picamera-rs"))["resources"]
    assert resources["requests"]["memory"] and resources["limits"]["memory"]
    overridden = container(docs("picamera-rs", "resources.limits.memory=128Mi"))["resources"]
    assert overridden["limits"]["memory"] == "128Mi"


def normalise(d: dict[str, dict[str, Any]]) -> str:
    text = yaml.safe_dump(d, sort_keys=True)
    text = text.replace("picamera-rs", "picamera")
    for chart in ("picamera-rs", "picamera"):
        meta = yaml.safe_load((CHARTS / chart / "Chart.yaml").read_text())
        text = text.replace(f"picamera-{meta['version']}", "picamera-CHART")
        text = text.replace(f"'{meta['appVersion']}'", "'APP'")
        text = text.replace(f":{meta['appVersion']}", ":APP")
        text = text.replace(f"version: {meta['appVersion']}", "version: APP")
    return text


def test_values_are_interchangeable_and_only_resources_differ(tmp_path: Path) -> None:
    values = tmp_path / "values.yaml"
    values.write_text(yaml.safe_dump(VALUES))
    python, rust = docs("picamera", values=values), docs("picamera-rs", values=values)
    container(python).pop("resources")
    container(rust).pop("resources")
    assert normalise(python) == normalise(rust)


def test_both_charts_coexist_without_name_collisions() -> None:
    python, rust = docs("picamera"), docs("picamera-rs", "service.nodePort=30457")
    for kind in ("Deployment", "Service"):
        assert python[kind]["metadata"]["name"] != rust[kind]["metadata"]["name"]
    python_selector = python["Deployment"]["spec"]["selector"]["matchLabels"]
    rust_selector = rust["Deployment"]["spec"]["selector"]["matchLabels"]
    assert python_selector != rust_selector
    assert (
        python["Service"]["spec"]["ports"][0]["nodePort"]
        != (rust["Service"]["spec"]["ports"][0]["nodePort"])
    )
