# Spec Delta

## ADDED Requirements

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
