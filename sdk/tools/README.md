<!-- SPDX-License-Identifier: Apache-2.0 -->
# sdk/tools

Tools for packaging OneMind apps. The binding contract is [`sdk/contracts/poc-v0.md`](../contracts/poc-v0.md): §4 defines the app manifest and §9.4 the app CI gate.

## validate-apps

`validate-apps` checks every app directory `apps/<id>/` against the contract. It skips directories whose names start with `_` (such as `apps/_intake`) or `.`. It is the local version of the checks that `.github/workflows/ci-apps.yml` runs on every pull request that touches `apps/` or `sdk/`.

| # | Check | Why |
|---|---|---|
| 1 | `onemind.app.yaml` is valid against [`sdk/schema/onemind.app.schema.json`](../schema/onemind.app.schema.json) | The gateway builds the Market catalog from this file (contract §3, `GET /v1/apps`). |
| 2 | `metadata.id` equals the directory name, and no two apps share an id | The id names the install namespace `app-<id>`. |
| 3 | The `metadata.icon` file exists inside the app directory | The Market shows it. |
| 4 | `kustomize build apps/<id>/<spec.manifests>` passes `kubeconform -strict -summary` | The gateway installs with `kubectl apply -k` (contract §3), so the rendered output must be valid Kubernetes. |
| 5 | Every container image is `name:tag@sha256:<64 hex>` | The tag tells a person which version it is. The digest makes the bytes fixed, so a scan stays true for what actually runs (§9.4 check 3). |
| 6 | Every container (including init containers) sets `cpu` and `memory` in both `resources.requests` and `resources.limits` | Small boxes (Pi 5, 8 GB) need predictable memory use. |
| 7 | A Service exposes `spec.web.port`, when `spec.web` is set, its selector matches a workload's pod labels, and its `targetPort` is a port (by name or number) that one of those containers declares | The dashboard links to the app's web UI on that port, so the port must reach the app. |
| 8 | `renovate.json` automerges exactly the apps whose manifest has `metadata.tier: verified` and `spec.updates.automerge: patch` (only when every app is validated) | Renovate cannot read the manifests, so this keeps contract §10.2's automerge policy and the list in `renovate.json` in step. |

The manifest schema leaves `spec.web` optional because some seed apps have no web UI (Mosquitto is an MQTT broker). It includes the contract §9.3 fields (`metadata.links`, `metadata.upstream`, `metadata.tier`, `spec.updates`) and the optional §11.2 `spec.agent`. Every object rejects unknown keys: a new field is a contract change first. A link or release date may be the string `UNVERIFIED` when no primary source confirmed it; that caps the app's tier at `community`.

### Run it

You need Python 3.11 or later, plus `kustomize` and `kubeconform` on `PATH`. CI pins kustomize v5.8.3 and kubeconform v0.8.0. kubeconform downloads Kubernetes JSON schemas, so the check needs network access.

```sh
python3 -m venv .venv
.venv/bin/python3 -m pip install -r sdk/tools/requirements.txt
.venv/bin/python3 -I sdk/tools/validate-apps              # every app
.venv/bin/python3 -I sdk/tools/validate-apps uptime-kuma  # only some apps
.venv/bin/python3 -I sdk/tools/validate-apps --apps-dir path/to/apps
```

`-I` runs Python in isolated mode, which ignores `PYTHON*` environment variables and the current directory, so a stray file cannot change what the tool imports.

Exit codes:
- `0`: all apps pass, or there are no apps
- `1`: at least one check failed (each failure is printed under `FAIL apps/<id>/`)
- `2`: a usage or environment problem, such as a missing tool, a missing dependency or an unreadable schema

### Find an image's digest

```sh
crane digest docker.io/louislam/uptime-kuma:2.0.2      # the multi-arch index digest to pin
crane manifest docker.io/louislam/uptime-kuma:2.0.2    # lists the per-arch images, to confirm spec.archs
```

Pin the index digest, not a single-arch one, so the same reference works on amd64 and arm64.

## Not checked yet

These parts of the §9.4 gate come in later waves: the licence gate against `research-output/evidence/license-matrix.csv`, a check that the images support the declared `spec.archs`, Trivy (CVE scan, SBOM, secrets), ClamAV, cosign and Scorecard, the non-root check and the k3d smoke test. CI already runs gitleaks over the pull request's commits.
