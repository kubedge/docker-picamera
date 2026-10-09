# Design

## Context

`charts/picamera` (from `modernize-python-and-docker`) already renders one Deployment with `Recreate`, a Service (`<fullname>`, port 9090 → 8000) and selector labels `app.kubernetes.io/{name,instance}`. kubedge-dashboard (main@6b69bef) lists pods in all namespaces labelled `kubedge.device.name=camera` and has an unfilled `url` field. The contract was negotiated session-to-session and approved by both operators on 2026-10-09.

## Goals / Non-Goals

**Goals:** discovery metadata on the pod only; zero effect on scheduling, the selector, or auth.
**Non-Goals:** dashboard proxying, instantiate/terminate, any runtime change to the service, an Ingress-derived external URL.

## Decisions

- **Pod template, not selector.** A Deployment's selector is immutable; adding to `selectorLabels` would break `helm upgrade` of existing releases. The label goes into `spec.template.metadata.labels` beside the selector labels. Flipping `dashboard.discoverable` changes the pod template, so `Recreate` restarts the single pod — acceptable.
- **Label key kept as the dashboard's existing `kubedge.device.name`.** Renaming it to the namespaced `kubedge.io/device` would need both repos to change in one step; deferred.
- **Two annotations.** `kubedge.io/stream-url` is the in-cluster URL (for the dashboard's `/healthz` probes and pod-to-pod use); a browser cannot open it. `kubedge.io/external-url` is what the dashboard links to, and only an operator knows it (NodePort host, ingress), so it is a value and is omitted when empty. Deriving it from `ingress.hosts` was rejected: ingress paths and TLS make a guess wrong more often than right.
- **URL built in a helper** `picamera.streamUrl`: `printf "http://%s.%s:%v/stream.mjpg" (include "picamera.fullname" .) .Release.Namespace .Values.service.port`.
- **Values** under one key: `dashboard.discoverable: true`, `dashboard.externalUrl: ""`.

## Risks / Trade-offs

- [Dashboard reads a different key later] → keys are pinned in this spec and in the dashboard's matching change; a rename is a coordinated change.
- [Label leaks discovery to anyone listing pods] → it carries no credentials; the stream is still behind Basic auth.

## Migration Plan

Chart version bump to 0.3.0; `helm upgrade` restarts the pod once with the new metadata. No action needed for releases that set `dashboard.discoverable=false`.
