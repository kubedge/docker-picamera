# Spec Delta

## MODIFIED Requirements

### Requirement: Listening address
The service SHALL accept HTTP connections on all interfaces on the TCP port named by `PORT` (default `8000`) and serve concurrent clients. A `PORT` that is not an integer from 1 to 65535 SHALL be a startup error naming `PORT`.

#### Scenario: Two clients at once
- **WHEN** two authenticated clients open `/stream.mjpg` at the same time
- **THEN** both receive frames

#### Scenario: Port override
- **WHEN** the service starts with `PORT=9000`
- **THEN** it serves on port 9000

#### Scenario: Bad port
- **WHEN** the service starts with `PORT=0`
- **THEN** it exits non-zero with an error naming `PORT`
