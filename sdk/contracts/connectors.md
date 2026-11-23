<!-- SPDX-License-Identifier: Apache-2.0 -->
# Bridges, connectors and the terms record (manifest v1, #604)

**Why this exists.** Outside data (a quake feed, a weather API, a camera, someone's fitness account) must come into OneMind one way, with its licence and terms attached, so the map, News, search and notifications can trust it. Every source is an ordinary app with blocks in the one app manifest (`sdk/schema/onemind.app.schema.json`); there is no second manifest file. The validator is the same everywhere: the gateway's `Catalog.validate` (CI's `validate-apps` and the box) and the Go validator behind `onemind plugin validate`. Both read the golden cases in `sdk/testdata/manifest-v1/`.

Words used here:
- **Bridge** (`spec.extensions.bridge`): code in the app's own workload that fetches or receives outside data and hands it to the gateway's intake (`POST /v1/bridges/<id>/events`, issue #610). It never writes to the map, NATS or another app directly.
- **Connector** (`spec.extensions.connector`): an outside account the owner connects. The gateway holds the credential and runs it; the manifest names only the auth type (`none`, `api-key`, `oauth-code`, `oauth-device`).
- **Video source** (`spec.extensions.videoSource`): a camera or feed for the video engine. Camera state and events travel on the bus, frames never do.
- **Terms record** (`spec.terms`): the provider terms a person read, one entry per provider. The code licence is `metadata.license`.
- **NATS account** (`spec.extensions.nats`): the app's own `APP_<id>` account, with exact subjects under its own prefix `onemind.plugin.<id>.`.

## The rules (each one has a failing golden case)

1. **The terms record is mandatory** for every app with a bridge, connector or video source, and every such block names a provider that has an entry in `spec.terms.providers`.
2. **`personData` is always false.** No app tracks private individuals, looks up faces or plates, or guesses credentials.
3. **Hostnames only.** `hosts` are plain lowercase hostnames: no wildcard, no port, no IP literal. Each must also be listed in `spec.egress`, the default-deny internet allow list.
4. **Emits stay inside the app's own source.** An emit names a kind (`intel`, `article`, `alert`, `layer`, `asset`) and a name, never a source: the gateway stamps the app id as the source. A `layer` emit must name one of the app's own `spec.mapLayers` with `source: emits`.
5. **Interval floor.** Every schedule is at least 60 seconds (the hub floor) and never faster than the provider's own `minIntervalSeconds`.
6. **Non-commercial or personal-use terms cannot allow redistribution** (mesh, TAK or public share). Person-scoped data (one person's own account) is never redistributed either.
7. **Embed-only and link-only providers are never stored or redistributed,** and a video source can only `record` from a provider with `display: full` and a store.
8. **Loosening needs a new approval.** `onemind plugin validate NEW --previous OLD` sets `widens_grants` when a version adds a host, provider, key, scope, NATS subject or import, data class, service or job, or widens redistribution, storage, display, use or cache time. The owner then approves the update again.
9. **No credential in any field.** A value that looks like a key, token, private key, password-in-a-URL or key-in-a-query, or a field named like a credential, is refused. Errors name the field, never the value. Keys belong in `spec.secrets` (names only); the owner enters values in the install approval.

Also refused by the same validator: `runtime: module` outside the signed system apps list, a tool with `effect: actuate` (only a lab build could ever allow it), unknown blocks, a job or notification button that calls an undeclared tool, a job that calls a destructive tool, and an Approve button: the host alone draws Review and Deny.

## Naming

The design notes spell some names with underscores (`video_source`, `map_layer`, `person_data`, `widens_grants`). The manifest uses the camelCase of every other manifest field: `videoSource`, `mapLayers`, `personData`. `widens_grants` is the output field of `onemind plugin validate --previous`, not a manifest field. Map layers live in `spec.mapLayers`, the same block a built-in descriptor carries (#603), so there is one place for them.
