# rust-helm-deployment Specification

## Purpose

Defines the `picamera-rs` Helm chart, which deploys the Rust streamer to Kubernetes camera nodes with the same contract as the Python chart and a memory limit sized for it.

## Requirements

### Requirement: Chart identity
The chart SHALL live at `charts/picamera-rs`, be named `picamera-rs`, target Helm 3 (`apiVersion: v2`), and deploy image `kubedge1/picamera-rs` with the tag defaulting to the chart's `appVersion`.

#### Scenario: Default image
- **WHEN** the chart is rendered with default values
- **THEN** the container image is `kubedge1/picamera-rs:<appVersion>`

### Requirement: Same deployment contract as the Python chart
The chart SHALL schedule only on `kubernetes.io/arch=arm64` nodes labelled `picameraInstalled=true`, take credentials from the Secret named by `auth.existingSecret` (failing to render without it), set camera variables from `camera.*` values, give the container host `/dev` and read-only `/run/udev`, probe `GET /healthz` on 8000 for liveness and readiness, and expose a `NodePort` Service — with the same value names and defaults as `charts/picamera`.

#### Scenario: Secret not configured
- **WHEN** the chart is rendered without `auth.existingSecret`
- **THEN** rendering fails with a message naming `auth.existingSecret`

#### Scenario: Values are interchangeable
- **WHEN** a values file written for `charts/picamera` is rendered with `charts/picamera-rs`
- **THEN** it renders without error and differs only in names, image and resources

### Requirement: Memory limit by default
The chart SHALL set a container memory request and limit by default, sized from the on-device measurement of the Rust image, and SHALL let both be overridden.

#### Scenario: Default resources
- **WHEN** the chart is rendered with default values
- **THEN** the container has a memory request and a memory limit

#### Scenario: Override
- **WHEN** the chart is rendered with `resources.limits.memory=128Mi`
- **THEN** the container's memory limit is `128Mi`

### Requirement: Coexists with the Python chart
Both charts SHALL be installable in the same namespace at the same time without resource-name collisions, provided their Services use different node ports.

#### Scenario: Side by side
- **WHEN** `picamera` and `picamera-rs` are installed in one namespace with distinct `service.nodePort` values
- **THEN** both install successfully
