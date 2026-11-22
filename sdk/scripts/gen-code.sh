#!/bin/sh
# SPDX-License-Identifier: Apache-2.0
# Generate the SDK code that is not committed (CI-16) from the committed spec sdk/openapi/onemind-v1.json.
# It needs neither core/ nor a gateway, only each language's own toolchain, so CI jobs, the image
# build (os/rootfs/Containerfile), deploy/install.sh and deploy/bundle.sh all call this one script.
#
#   sdk/scripts/gen-code.sh [go] [ts] [py]      (no argument: all three)
#
#   go  needs Go           -> sdk/go/internal/gen/types.gen.go
#   ts  needs Node and npm -> sdk/ts/src/gen/schema.ts (runs npm ci in sdk/ts once if needed)
#   py  needs uv           -> sdk/python/src/onemind_sdk/_gen/models.py and aio.py
#
# The generator pins live here (Go, Python) and in sdk/ts/package.json (TypeScript). Licences:
# oapi-codegen Apache-2.0, datamodel-code-generator MIT, openapi-typescript MIT.
set -eu

OAPI_CODEGEN=github.com/oapi-codegen/oapi-codegen/v2/cmd/oapi-codegen@v2.8.1
DATAMODEL_CODEGEN=datamodel-code-generator==0.87.0

SDK=$(cd "$(dirname "$0")/.." && pwd)
SPEC=$SDK/openapi/onemind-v1.json
[ -f "$SPEC" ] || { echo "gen-code: $SPEC is missing" >&2; exit 1; }
[ "$#" -gt 0 ] || set -- go ts py

# The "generated" header with the spec's sha256 (SDK.md §3.4). Cosmetic, so it is skipped where the
# build has no python3 (the image's Go stage); the code itself is the same.
stamp() { if command -v python3 >/dev/null 2>&1; then python3 "$SDK/scripts/stamp.py" "$1" "$2"; fi; }

for lang in "$@"; do
  case $lang in
    go)
      mkdir -p "$SDK/go/internal/gen"
      (cd "$SDK/go" && go run "$OAPI_CODEGEN" -config oapi-codegen.yaml ../openapi/onemind-v1.json)
      stamp "$SDK/go/internal/gen/types.gen.go" "oapi-codegen v2.8.1" ;;
    ts)
      mkdir -p "$SDK/ts/src/gen"
      [ -x "$SDK/ts/node_modules/.bin/openapi-typescript" ] \
        || (cd "$SDK/ts" && npm ci --ignore-scripts --no-audit --no-fund --loglevel=error)
      (cd "$SDK/ts" && npm run --silent gen) ;;
    py)
      out=python/src/onemind_sdk/_gen/models.py   # relative: the generator writes the input name into the header
      (cd "$SDK" && uvx --quiet --python 3.12 --from "$DATAMODEL_CODEGEN" datamodel-codegen --input openapi/onemind-v1.json \
        --input-file-type openapi --output-model-type pydantic_v2.BaseModel --target-python-version 3.10 --use-annotated \
        --field-constraints --use-standard-collections --use-union-operator --disable-timestamp --formatters builtin --output "$out")
      stamp "$SDK/$out" "datamodel-code-generator 0.87.0"
      python3 "$SDK/python/scripts/make_aio.py" ;;
    *) echo "gen-code: unknown language '$lang' (go, ts or py)" >&2; exit 2 ;;
  esac
done
