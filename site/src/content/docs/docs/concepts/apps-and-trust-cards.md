---
title: Apps and trust cards
description: How an app gets into OneMind, what is checked, and what the trust card on each app tells you.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

Every OneMind app is a directory in the repository, `apps/<id>/`, with a manifest (`onemind.app.yaml`), an icon and plain Kubernetes manifests. The [apps catalog](../../../apps/) on this site is generated from those files at build time, so it can never list an app that does not exist.

## The trust card

Each app page shows a **trust card**: the facts you would want before you install something on the machine that holds your photos. Every line comes from a file in Git:

| Line | What it means | Source |
|---|---|---|
| Licence | The SPDX licence read from the upstream repository at the pinned release, and its class. **L1/L2** are allowed in the Market. Unknown or non-commercial licences are **blocked**. | CI gate |
| Images pinned by digest | Every image is pinned by tag **and** `sha256` digest, so what was scanned is exactly what runs. | `manifests/` |
| Vulnerabilities | Trivy CVE scan. A critical CVE with a fix available fails the app. | `scan.json` |
| Malware | ClamAV over the image's files, with signatures updated in the same job. Any hit blocks the app until a human looks. | `scan.json` |
| Secrets in image | Trivy's secret scanner. | `scan.json` |
| Signature | cosign verification when the upstream signs its images. | `scan.json` |
| Smoke test | Installed on a throwaway k3s in CI; the web port must answer HTTP 200. | `scan.json` |
| Scan age | The gateway refuses to install an app without a passing scan newer than 7 days. | `scan.json` |

<span class="om-tag om-tag--ok">works today</span> all of it: manifests, digest pins, the generated catalog, the CI gate that writes `scan.json`, the daily rescan, and the gateway check that refuses unscanned apps (`409 stale_precondition`). An app with no scan record shows "Not scanned" and cannot be installed. We would rather show a grey dot than a green one we haven't earned. Step by step in the dashboard: [Apps](../../guides/apps/).

## Adding apps at scale <span class="om-tag om-tag--ok">works today</span>

The goal is 100+ apps, added continuously, without hand-crafting YAML:

1. **Queue.** One line per app in [`apps/_intake/queue.yaml`](https://github.com/onemindos/ONEMINDOS/blob/main/apps/_intake/queue.yaml): name, GitHub repo, optional docs link.
2. **Scaffolder.** Fills the manifest from primary sources only: the GitHub API, the upstream's own compose file or Helm chart, and the registry for digests and architectures. Anything it cannot verify is written as `UNVERIFIED` and blocks the `verified` tier. It never guesses an image name.
3. **CI gate.** Runs every check above on each pull request.
4. **Updates.** Renovate opens pull requests that bump tag and digest. The gate runs again. Patch bumps of verified apps can merge automatically when green; minor and major bumps wait for a human. A new critical CVE or malware hit marks the app `blocked`. Alerting the owners who have it installed is planned.

## Tiers

- **verified**: every check passed.
- **community**: the upstream is archived or has not released in 18 months.
- **blocked**: licence, malware or a failing critical check.

The tier is set by CI, never by hand. OneMind's own apps pass the same checks: no exemptions for our own namespace.

## Planned

- **Grants and a trust rating.** Apps that need a device, the host network or a GPU will declare it, you will see each grant before you approve, and each one lowers the app's visible trust rating.
- **Publisher signing with a OneMind countersignature**, and a signed revocation list.
- **"Open in OneMind" buttons** on these pages: the website sends you to your own box, which shows the permissions and asks you to confirm. The website never learns your box's address.
