# SPDX-License-Identifier: Apache-2.0
"""App store depth (contract §12.22; umbrel-parity PD-09…PD-13, PD-17; PD-08 logs are §12.15).

One package, one feature (`appstore`), registered by `routers/appstore.py`:

- `appsettings` spec.settings fields, value validation, the onemind-settings ConfigMap
- `deps`       spec.dependencies with alternatives, and the dependants of an app
- `hostports`  spec.hostPorts declarations and their conflicts
- `compose`    Docker Compose -> private app folder, refusing what the install sandbox refuses
- `sources`    community catalog sources pinned to a commit, fetched and scanned on the box
- `exposure`   private / mesh / public tiers, each changed by its own request
- `service`    the action types and preconditions, wired into the gateway's ActionService

Nothing here executes store content on the host. git is run with an argv list
(no shell), fixed options and timeouts; the install sandbox (CORE-SANDBOX) stays the only
judge of what reaches the cluster.
"""
