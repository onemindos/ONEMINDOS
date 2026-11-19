---
pr: pending
branch: ci/sdk-gen-in-ci
---
CI-16: the SDK code generated from the OpenAPI spec (Go types, TypeScript schema, Python models and the async client) is no longer committed, so two API pull requests stop conflicting on thousands of generated lines. Only the spec `sdk/openapi/onemind-v1.json` stays committed as the reviewed contract. One script, `sdk/scripts/gen-code.sh`, makes the code from the spec, and everything that needs it calls it first: the CI jobs (through the `.github/actions/sdk-gen` step), the image build, `deploy/install.sh`, `deploy/bundle.sh` and the test harnesses. A fresh clone runs `make -C sdk gen-code` once; `make -C sdk check-stale` now checks that the spec matches core and that the code generates.
