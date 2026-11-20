# SPDX-License-Identifier: Apache-2.0
# OneMind SDKs: generated types + hand-written transports (docs/leap/dev/SDK.md).
# Run from the repo root as `make -C sdk <target>`. Needs uv, Go and Node.
#
#   make -C sdk gen          export the OpenAPI spec from core/, then generate the code of all three SDKs
#   make -C sdk gen-code     generate the SDK code from the committed spec only (no core/; what CI runs)
#   make -C sdk check-stale  the committed spec matches core/ and the code generates from it (CI)
#   make -C sdk test         generate, then the unit tests of the three SDKs
#
# Only the spec (openapi/onemind-v1.json) is committed: it is the reviewed API contract. The code
# generated from it is not (CI-16; .gitignore), so two API pull requests never conflict on it.
# A fresh clone runs `make -C sdk gen-code` (or `make -C sdk gen`) once before building.
# The generator pins live in scripts/gen-code.sh and ts/package.json.

SPEC   := openapi/onemind-v1.json
OPENAPI_STATE_DIR ?=
OPENAPI_STATE_ARGS = $(if $(OPENAPI_STATE_DIR),--state-dir "$(OPENAPI_STATE_DIR)",)

.PHONY: openapi gen gen-code gen-go gen-py gen-ts check-stale test test-go test-py test-ts

openapi:
	cd ../core && uv run --quiet python -m onemind_core.openapi --out ../sdk/$(SPEC) $(OPENAPI_STATE_ARGS)

gen: openapi
	$(MAKE) gen-code

gen-code:
	scripts/gen-code.sh go ts py

gen-go:
	scripts/gen-code.sh go

gen-py:
	scripts/gen-code.sh py

gen-ts:
	scripts/gen-code.sh ts

# The committed spec must match core/ (the reviewed contract), and every SDK must generate from it.
# The generated code is untracked, so there is no git diff to check; ci-sdk's test job then runs
# the SDK tests and the live conformance suite on that freshly generated code.
check-stale:
	cd ../core && uv run --quiet python -m onemind_core.openapi --check ../sdk/$(SPEC) $(OPENAPI_STATE_ARGS)
	$(MAKE) gen-code

test: test-go test-py test-ts

test-go: gen-go
	cd go && go vet ./... && go test -race -count=1 ./...

test-py: gen-py
	cd python && uv run --quiet --python 3.12 pytest -q

test-ts: gen-ts
	cd ts && npm run --silent typecheck && npm test --silent
