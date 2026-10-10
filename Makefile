# Developer and release targets. `make push` publishes kubedge1/picamera by hand, after
# the same test and lint gate CI runs (kubesim_blinkt's workflow); CI never pushes.
.PHONY: help sync lint typecheck test chart rust check image push image-rs push-rs

help:
	@echo "make check   lint + typecheck + test + chart"
	@echo "make image   build linux/arm64 locally (no push)"
	@echo "make push    check, then build and push kubedge1/picamera:latest and :<version>"
	@echo "make push-rs check, then build and push kubedge1/picamera-rs:latest and :<version>"

sync:
	uv sync --locked

lint: sync
	uv run ruff check .
	uv run ruff format --check .

typecheck: sync
	uv run mypy src

test: sync
	uv run pytest

chart:
	helm lint charts/picamera --set auth.existingSecret=lint
	helm lint charts/picamera-rs --set auth.existingSecret=lint

rust:
	cd rust && cargo fmt --check && cargo clippy --all-targets --locked -- -D warnings \
		&& cargo test --locked && cargo build --locked

# rust first: the conformance tests in `test` run against its debug build.
check: rust lint typecheck test chart

image:
	./build.sh

push: check
	./build.sh --push

image-rs:
	rust/build.sh

push-rs: check
	rust/build.sh --push
