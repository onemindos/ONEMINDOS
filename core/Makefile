# OneMind Core gateway. Run from the repo root as `make -C core <target>`.
# Needs uv (https://docs.astral.sh/uv/); uv fetches Python 3.12 by itself.

PY        ?= 3.12
IMAGE     ?= onemind-core:dev
PLATFORMS ?= linux/amd64,linux/arm64
REPO_ROOT := $(abspath $(CURDIR)/..)
# Use the real Market seed (apps/) when the apps stream has landed it, else the test fixtures.
APPS_DIR  ?= $(if $(wildcard $(REPO_ROOT)/apps/*/onemind.app.yaml),$(REPO_ROOT)/apps,$(CURDIR)/tests/fixtures/apps)
DIST_DIR  ?= $(if $(wildcard $(REPO_ROOT)/dashboard/dist/index.html),$(REPO_ROOT)/dashboard/dist,$(CURDIR)/tests/fixtures/dist)

.PHONY: help sync test test-integration run audit-verify image image-multiarch clean

help:
	@echo "make -C core test              unit + contract tests (SQLite, no NATS)"
	@echo "make -C core test-integration  same suite on PostgreSQL + a real NATS (needs Docker)"
	@echo "make -C core run               gateway on 127.0.0.1:8080 (noop executor, dev tokens)"
	@echo "make -C core audit-verify      check the hash chain of ./data/audit.jsonl"
	@echo "make -C core image             docker image for this machine's arch"
	@echo "make -C core image-multiarch   buildx amd64+arm64 (no push)"

sync:
	uv sync --python $(PY)

test: sync
	uv run pytest -q

test-integration: sync
	docker run -d --rm -p 14222:4222 --name onemind-core-it-nats nats:2.10-alpine
	docker run -d --rm -p 15432:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_DB=onemind --name onemind-core-it-pg postgres:17-alpine
	sleep 5
	ONEMIND_TEST_DB_URL=postgresql://postgres:test@127.0.0.1:15432/onemind \
	ONEMIND_TEST_NATS_URL=nats://127.0.0.1:14222 uv run pytest -q; rc=$$?; \
	docker rm -f onemind-core-it-nats onemind-core-it-pg >/dev/null; exit $$rc

run: sync
	ONEMIND_TOKENS_FILE=$${ONEMIND_TOKENS_FILE:-$(CURDIR)/examples/tokens.example.yaml} \
	ONEMIND_APPS_DIR=$${ONEMIND_APPS_DIR:-$(APPS_DIR)} \
	ONEMIND_DASHBOARD_DIST=$${ONEMIND_DASHBOARD_DIST:-$(DIST_DIR)} \
	ONEMIND_EXECUTOR=$${ONEMIND_EXECUTOR:-noop} \
	ONEMIND_HOST=$${ONEMIND_HOST:-127.0.0.1} \
	uv run python -m onemind_core

audit-verify: sync
	uv run onemind-audit-verify $${ONEMIND_AUDIT_PATH:-data/audit.jsonl}

image:
	docker build -f Dockerfile -t $(IMAGE) $(REPO_ROOT)

image-multiarch:
	docker buildx build --platform $(PLATFORMS) -f Dockerfile -t $(IMAGE) $(REPO_ROOT)

clean:
	rm -rf .venv data .pytest_cache
