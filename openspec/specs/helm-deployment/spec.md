# helm-deployment Specification

## Purpose

Defines the `picamera` Helm chart: deploying the `kubedge1/picamera` stream onto the arm64 Kubernetes nodes that carry a camera, with credentials from a Secret, health from the service itself, and pod metadata that lets kubedge-dashboard discover and link it.

## Requirements

### Requirement: Chart identity
The chart SHALL live at `charts/picamera`, be named `picamera`, target Helm 3 (`apiVersion: v2`), and deploy image `kubedge1/picamera` with the tag defaulting to the chart's `appVersion`.

#### Scenario: Default image
- **WHEN** the chart is rendered with default values
- **THEN** the container image is `kubedge1/picamera:<appVersion>`

### Requirement: Scheduling on camera nodes
Pods SHALL schedule only onto nodes labelled `kubernetes.io/arch=arm64` and `picameraInstalled=true`.

#### Scenario: Node selector
- **WHEN** the chart is rendered with default values
- **THEN** the pod spec's node selector contains both labels

### Requirement: Credentials from a Secret
The chart SHALL take `AUTH_USERNAME` and `AUTH_PASSWORD` from an existing Secret named by `auth.existingSecret` (keys `username` and `password`), and rendering SHALL fail with a clear message when `auth.existingSecret` is not set. No credential value SHALL appear in chart values or rendered manifests.

#### Scenario: Secret not configured
- **WHEN** the chart is rendered without `auth.existingSecret`
- **THEN** rendering fails with a message that names `auth.existingSecret`

#### Scenario: Secret configured
- **WHEN** the chart is rendered with `auth.existingSecret=picamera-auth`
- **THEN** both variables come from `secretKeyRef` entries on `picamera-auth`

### Requirement: Camera settings from values
`RESOLUTION`, `FRAMERATE`, `ROTATE`, `HFLIP` and `VFLIP` SHALL be set from chart values, defaulting to the service defaults.

#### Scenario: Override resolution
- **WHEN** the chart is rendered with `camera.resolution=1280x720`
- **THEN** the container has `RESOLUTION=1280x720`

### Requirement: Camera device access
The container SHALL be given the host's `/dev` and read-only `/run/udev`, with the privilege Kubernetes requires for host device access, and SHALL NOT mount `/dev/vchiq` on its own.

#### Scenario: Rendered volumes
- **WHEN** the chart is rendered with default values
- **THEN** the pod mounts host `/dev` and `/run/udev` (read-only) and no `/dev/vchiq` volume

### Requirement: Health probes
The chart SHALL configure liveness and readiness probes as `GET /healthz` on port 8000 and SHALL deploy a single container.

#### Scenario: Probes
- **WHEN** the chart is rendered with default values
- **THEN** the one container has HTTP liveness and readiness probes on `/healthz` port 8000

### Requirement: Service exposure
The chart SHALL create a `NodePort` Service on node port `30456`, port `9090`, targeting container port `8000`, with an optional Ingress disabled by default.

#### Scenario: Default service
- **WHEN** the chart is rendered with default values
- **THEN** the Service is `NodePort` `30456` → `9090` → `8000` and no Ingress is rendered

### Requirement: Discoverable by kubedge-dashboard
When `dashboard.discoverable` is true (the default), the pod template SHALL carry the label `kubedge.device.name: camera`. The label SHALL NOT be added to the Deployment's selector.

#### Scenario: Default render
- **WHEN** the chart is rendered with default values
- **THEN** the pod template's labels include `kubedge.device.name: camera` and the Deployment's `matchLabels` do not

### Requirement: In-cluster stream URL annotation
When discoverable, the pod template SHALL carry the annotation `kubedge.io/stream-url` set to `http://<service-name>.<namespace>:<service.port>/stream.mjpg`, derived from the rendered Service.

#### Scenario: Release in a namespace
- **WHEN** release `cam` is rendered into namespace `home` with default values
- **THEN** `kubedge.io/stream-url` is `http://cam-picamera.home:9090/stream.mjpg`

### Requirement: External stream URL annotation
When discoverable and `dashboard.externalUrl` is non-empty, the pod template SHALL carry `kubedge.io/external-url` with that value verbatim; otherwise the annotation SHALL be absent.

#### Scenario: Not configured
- **WHEN** the chart is rendered with default values
- **THEN** there is no `kubedge.io/external-url` annotation

#### Scenario: Configured
- **WHEN** the chart is rendered with `dashboard.externalUrl=http://kube-node02:30456/stream.mjpg`
- **THEN** `kubedge.io/external-url` equals that URL

### Requirement: Opt-out
With `dashboard.discoverable=false` the pod SHALL carry neither the label nor either annotation, and nothing else in the rendered manifests SHALL change.

#### Scenario: Discovery off
- **WHEN** the chart is rendered with `dashboard.discoverable=false`
- **THEN** the pod has no `kubedge.device.name` label and no `kubedge.io/*` annotation

### Requirement: Credentials stay with the service
Discovery metadata SHALL NOT contain credentials or reference the auth Secret; the stream stays behind the service's Basic auth and `/healthz` stays unauthenticated.

#### Scenario: No secret in metadata
- **WHEN** the chart is rendered with `auth.existingSecret=picamera-auth`
- **THEN** no pod label or annotation contains `picamera-auth`, a username or a password
