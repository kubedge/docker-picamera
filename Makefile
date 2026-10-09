# Developer and release targets. `make push` publishes kubedge1/picamera by hand, after
# the same test and lint gate CI runs (kubesim_blinkt's workflow); CI never pushes.
.PHONY: help sync lint typecheck test chart check image push

help:
	@echo "make check   lint + typecheck + test + chart"
	@echo "make image   build linux/arm64 locally (no push)"
	@echo "make push    check, then build and push kubedge1/picamera:latest and :<version>"

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

check: lint typecheck test chart

image:
	./build.sh

push: check
	./build.sh --push
