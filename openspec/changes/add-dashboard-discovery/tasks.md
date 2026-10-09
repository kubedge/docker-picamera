# Tasks

## 1. Prerequisite

- [x] 1.1 Confirm `modernize-python-and-docker` is archived (`openspec list --specs` shows `helm-deployment`); verify `openspec validate add-dashboard-discovery --strict` passes against it

## 2. Chart

- [x] 2.1 Add `dashboard.discoverable` / `dashboard.externalUrl` to `values.yaml` with comments, the `picamera.streamUrl` helper to `_helpers.tpl`, and pod-template label + annotations to `deployment.yaml` (selector untouched); bump `Chart.yaml` version to 0.3.0; verify `helm lint charts/picamera --set auth.existingSecret=x` passes
- [x] 2.2 Add `tests/test_chart.py` cases, one per requirement: default label on pod template and absent from `matchLabels`; `stream-url` for release `cam` in namespace `home` equals `http://cam-picamera.home:9090/stream.mjpg`; `external-url` absent by default and verbatim when set; `discoverable=false` removes label and both annotations and leaves every other rendered field identical; no label/annotation contains the Secret name; verify `make check` passes

## 3. Docs

- [x] 3.1 README § Run (Kubernetes): one paragraph on dashboard discovery and `dashboard.externalUrl`; `architecture.md` § Chart: the label/annotation contract and why it is not in the selector; verify `python3 bin/check-doc-set.py` passes

## 4. Integration

- [x] 4.1 Open the PR; verify CI green (`chart` job runs the new tests)
- [ ] 4.2 Tell kubedge-dashboard (cross-session) the keys are live on `main`, with the chart version; verify its reply
