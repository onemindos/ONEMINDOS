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

## app-scaffold

`app-scaffold owner/repo` writes `apps/<id>/` (manifest, `manifests/` with a Deployment, Service, PVCs and kustomization, a neutral initials icon and the generated README) from primary sources only (contract §9.2):

- **GitHub API:** description, homepage, topics, SPDX licence, latest release and its date, archived flag, stars, last commit.
- **Upstream files at the release tag:** the shallowest compose file (test, dev and e2e files are skipped), else a Helm chart's `values.yaml`, else a `docker run` line in `README.md`: image, container ports and volumes. Host paths (`/etc`, `/run`, device files) and extra services (databases) are not packaged and are listed as open questions.
- **Registry (crane):** the image tag that equals the release (`2.5.10` or `v2.5.10`) is preferred over a floating tag such as `:2` or `:latest`; then the index digest, architectures and the image's `USER`.

Whatever it cannot confirm is written as `UNVERIFIED` (in values, or in comments for defaults such as resources and category) and listed in the README's open questions, which caps the app at tier `community`. It never guesses an image name: without one in an upstream file or `--image`, the Deployment's image is `UNVERIFIED` and `validate-apps` fails. If the repo is in `apps/_intake/queue.yaml`, it takes the entry's name and docs and sets its status to `in-pr`.

```sh
python3 -I sdk/tools/app-scaffold dani-garcia/vaultwarden
python3 -I sdk/tools/app-scaffold home-assistant/core --id home-assistant --image ghcr.io/home-assistant/home-assistant
```

Unauthenticated GitHub API calls are limited to 60 an hour; set `GITHUB_TOKEN` to raise that. Exit codes: 0 written with nothing unverified, 1 written with `UNVERIFIED` left, 2 error.

## Tests

```sh
python3 -I -m unittest discover -s sdk/tools/tests -v
```

The tests use GitHub and registry answers recorded in `sdk/tools/tests/fixtures/` and need no network.

## app-gate

`app-gate` runs the contract §9.4 gate for one or more apps and writes `apps/<id>/scan.json` in exactly the §11.1 format, then regenerates the app's README. `.github/workflows/ci-apps.yml` runs it on every pull request that changes an app, and `.github/workflows/apps-rescan.yml` runs it every day for every app (§10.2).

| §9.4 | Check | Fails (`result: fail`) when |
|---|---|---|
| 1, 8 | `validate-apps` for the app (schema, id, kubeconform, limits, pins) | any validate-apps check fails |
| 2 | Licence: the manifest's SPDX expression must be confirmed by GitHub's detected licence or by the row for that repo in `research-output/evidence/license-matrix.csv`, then classed L1 (permissive), L2 (copyleft) or `blocked` | the class is `blocked`: unknown, unconfirmed, source-available (BUSL, Elastic, FSL), non-commercial (PolyForm-NC) or any `LicenseRef-` term. `OR` takes the best term, `AND` the worst. Confirmed by GitHub alone (no matrix row), the class is never better than GitHub's detected term, so `MIT OR <GitHub's licence>` cannot lift a licence |
| 3 | Pinning: `name:tag@sha256:…`, the digest exists, and its index has every arch in `spec.archs` (crane) | a declared arch is missing. A tag that has since moved is only noted |
| 4, 6 | Trivy over each image, once per declared arch (`--image-src remote`, no Docker needed): CVEs and secrets | a CRITICAL has a fixed version, or Trivy reports a secret in the image |
| 5 | ClamAV: `crane export` streams each arch's filesystem, regular files are unpacked to a temp dir, `clamscan -r` | any hit |
| 7 | cosign: if the registry has a `sha256-<digest>.sig` for the index or an arch image, `cosign verify` with the upstream's GitHub Actions identity; else `unsigned`. OpenSSF Scorecard from api.securityscorecards.dev (informational) | a published signature does not verify |
| 8 | Non-root: every container runs non-root (`runAsNonRoot`, a non-zero `runAsUser`, or the image's own non-root `USER`). An image whose `USER` is root is accepted only with `allowPrivilegeEscalation: false` and all capabilities dropped | a container forces UID 0 over a non-root image, or runs as root without those two settings |
| 9 | `--smoke`: `kubectl apply -k` into `app-<id>` on the current context, `rollout status` for every workload, then `GET /` through a port-forward to `spec.web.port` must answer 200–399. Skipped (and not a failure) when the app has no `spec.web` | the rollout or the HTTP check fails, or `--smoke` was not given for an app with a web port |

**Tier** (`metadata.tier`, contract §9.3): `blocked` when the licence class is blocked, ClamAV hits, or a CRITICAL has a fix; `verified` when the result is `pass`, the upstream is not archived, its latest release is under 18 months old and no file under `apps/<id>/` (except `scan.json`) says `UNVERIFIED`; `community` otherwise. `--tier check` (the default, used on pull requests) fails when the manifest claims a higher tier than the gate computes. `--tier write` (the daily rescan) writes the computed tier, but never lifts `blocked`: unblocking is a human pull request. With `--tier check` a committed `scan.json` that says `pass` must also be reproduced by the gate. `--fail-on claim` (used by `ci-apps.yml`) exits 1 only for such an over-claim, so an app that honestly fails (tier `blocked` or `community`, scan not `pass`) can merge and stays uninstallable (§10.3).

```sh
python3 -I sdk/tools/app-gate ntfy --smoke --clamav-db /var/lib/clamav --report /tmp/report.json
```

It needs `crane`, `trivy` (v0.76.2), `clamscan` with a fresh database (`freshclam`), `cosign` (only when an upstream signs), `kustomize`, `kubeconform` and, with `--smoke`, `kubectl` pointed at a **throwaway** cluster (CI uses k3d). `--report` writes every finding as JSON (CVE ids, notes, Scorecard), and `--sbom-dir` writes a CycloneDX SBOM per image and arch. Exit codes: 0 every app passes, 1 one fails, 2 a tool or the network failed.

## app-readme

`apps/<id>/README.md` is generated (contract §9.3) from `onemind.app.yaml`, the rendered manifests and `scan.json`: the links, licence and class, tier, resources, images and the latest scan summary. The hand-written part (what the app is, packaging notes, first-run steps copied from upstream docs with their URL) lives between `<!-- onemind:notes:begin -->` and `<!-- onemind:notes:end -->` and is kept on every run.

```sh
python3 -I sdk/tools/app-readme            # rewrite every README
python3 -I sdk/tools/app-readme --check    # CI: exit 1 if one is out of date
```

## Not checked yet

The gate's Trivy run records the CVE report; a separate syft SBOM (§9.4 item 4 names syft) is not produced, Trivy's CycloneDX output (`--sbom-dir`) is used instead. Debian tracker states as VEX (brief 30 D-B1.5) are not applied to app images.
