---
title: App manifest
description: The onemind.app.yaml format that every Market app uses.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

Every app lives in `apps/<id>/` with an `onemind.app.yaml`, an icon and a `manifests/` directory (a `kustomization.yaml` plus plain Kubernetes objects). The JSON Schema is `sdk/schema/onemind.app.schema.json`. The format is Apache-2.0, like the rest of OneMind.

## Version 1 alpha 1 <span class="om-tag om-tag--ok">works today</span>

```yaml
apiVersion: onemind.app/v1alpha1
kind: App
metadata:
  id: uptime-kuma              # at most 59 characters; installs into namespace app-<id>
  name: Uptime Kuma
  version: "2.5.10"
  description: Self-hosted uptime monitoring
  category: monitoring
  icon: icon.svg
  license: MIT                 # SPDX; CI re-reads it from upstream
  source: https://github.com/louislam/uptime-kuma
spec:
  archs: [amd64, arm64]
  requires: {gpu: false, minMemoryMb: 256}
  web: {port: 3001}
  manifests: manifests/        # images pinned by tag and digest
```

## Additions for intake at scale <span class="om-tag om-tag--ok">works today</span>

```yaml
metadata:
  links:
    docs: https://…
    github: https://github.com/owner/repo
    website: https://…
    support: https://…/issues
  upstream: {release: "v1.2.3", released_at: "…", archived: false}
  tier: verified | community | blocked    # set by CI, never by hand
spec:
  updates: {channel: security|stable, automerge: patch|none}
  agent: {principal: true, secret: <name>} # the app gets its own agent identity
```

## Planned

- `backup:` hot or cold, pre and post commands, SQLite paths, excludes, post-restore steps.
- `grants:` devices, host network, GPU; each shown to the owner before install.
- `multiUser:` `native`, `perUserInstance` or `ownerOnly`.
- `diagnostics.redact:` keys removed from support bundles.

## Add an app

Add a line to [`apps/_intake/queue.yaml`](https://github.com/onemindos/ONEMINDOS/blob/main/apps/_intake/queue.yaml) and open a pull request. See [Apps and trust cards](../../concepts/apps-and-trust-cards/).
