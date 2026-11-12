# SPDX-License-Identifier: Apache-2.0
# OneMind SDKs: generated types + hand-written transports (docs/leap/dev/SDK.md).
# Run from the repo root as `make -C sdk <target>`. Needs uv, Go and Node (npm ci in sdk/ts).
#
#   make -C sdk gen          export the OpenAPI spec and regenerate all three SDKs
#   make -C sdk check-stale  fail when anything generated differs from what is committed (CI)
#   make -C sdk test         unit tests of the three SDKs

# Generator pins (licence: Apache-2.0 / MIT / MIT). Each was at least 14 days old when pinned.
OAPI_CODEGEN    := github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.8.1
DATAMODEL_CODEGEN := datamodel-code-generator==0.87.0

SPEC   := openapi/onemind-v1.json
GO_GEN := go/internal/gen/types.gen.go
PY_GEN := python/src/onemind_sdk/_gen/models.py
TS_GEN := ts/src/gen/schema.ts

.PHONY: openapi gen gen-go gen-py gen-ts check-stale test test-go test-py test-ts

openapi:
	cd ../core && uv run --quiet python -m onemind_core.openapi --out ../sdk/$(SPEC)

gen: openapi gen-go gen-py gen-ts

gen-go:
	cd go && go run $(OAPI_CODEGEN) -config oapi-codegen.yaml ../$(SPEC)
	python3 scripts/stamp.py $(GO_GEN) "oapi-codegen v2.8.1"

gen-py:
	uvx --quiet --python 3.12 --from $(DATAMODEL_CODEGEN) datamodel-codegen --input $(SPEC) --input-file-type openapi \
	  --output-model-type pydantic_v2.BaseModel --target-python-version 3.10 --use-annotated --field-constraints \
	  --use-standard-collections --use-union-operator --disable-timestamp --formatters builtin --output $(PY_GEN)
	python3 scripts/stamp.py $(PY_GEN) "datamodel-code-generator 0.87.0"
	python3 python/scripts/make_aio.py

gen-ts:
	cd ts && npm run --silent gen

# Regenerate into the working tree, then let git say whether anything changed.
check-stale:
	cd ../core && uv run --quiet python -m onemind_core.openapi --check ../sdk/$(SPEC)
	$(MAKE) gen-go gen-py gen-ts
	@git diff --exit-code -- $(GO_GEN) $(PY_GEN) $(TS_GEN) python/src/onemind_sdk/aio.py \
	  || { echo "generated SDK code is stale: run 'make -C sdk gen' and commit"; exit 1; }

test: test-go test-py test-ts

test-go:
	cd go && go vet ./... && go test -race -count=1 ./...

test-py:
	cd python && uv run --quiet --python 3.12 pytest -q

test-ts:
	cd ts && npm run --silent typecheck && npm test --silent
