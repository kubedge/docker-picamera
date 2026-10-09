# Proposal

## Why

kubedge-dashboard lists camera pods by the label `kubedge.device.name=camera` and has a `url` field per camera, but nothing in the fleet sets that label or publishes a URL, so its camera list is always empty. Both operators approved a minimal contract on 2026-10-09: the picamera chart makes its pod discoverable and says where the stream is, and docker-picamera stays a leaf that depends on nothing.

## What Changes

- The chart labels the camera pod `kubedge.device.name: camera` (pod template only, never the immutable Deployment selector).
- The chart annotates the pod `kubedge.io/stream-url` with the in-cluster stream URL, always, and `kubedge.io/external-url` with the browser-reachable URL, only when one is configured.
- New values `dashboard.discoverable` (default `true`; `false` removes the label and both annotations) and `dashboard.externalUrl` (default empty).
- Authentication is unchanged: the browser does the Basic-auth prompt. The dashboard never reads the Secret or proxies the stream; `/healthz` stays open for its liveness probes.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `helm-deployment`: adds dashboard-discovery requirements (label, two annotations, opt-out). The capability is introduced by `modernize-python-and-docker`, which must be archived first; this change only adds requirements.

## Impact

- **Chart**: `charts/picamera/templates/deployment.yaml` (pod-template metadata), `values.yaml` (`dashboard.*`), `_helpers.tpl` (URL helper); chart version bump.
- **Tests**: `tests/test_chart.py` cases for each requirement.
- **Docs**: README § Run (Kubernetes) and `architecture.md` § Chart mention discovery.
- **Sibling**: kubedge-dashboard ships the matching change (read the annotations into `url`); nothing here depends on it.
