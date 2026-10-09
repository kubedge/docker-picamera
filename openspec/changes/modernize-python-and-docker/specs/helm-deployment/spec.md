# Spec Delta

## Purpose

Defines the `picamera` Helm chart: deploying the `kubedge/picamera` stream onto the arm64 Kubernetes nodes that carry a camera, with credentials from a Secret and health from the service itself.

## ADDED Requirements

### Requirement: Chart identity
The chart SHALL live at `charts/picamera`, be named `picamera`, target Helm 3 (`apiVersion: v2`), and deploy image `kubedge/picamera` with the tag defaulting to the chart's `appVersion`.

#### Scenario: Default image
- **WHEN** the chart is rendered with default values
- **THEN** the container image is `kubedge/picamera:<appVersion>`

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
