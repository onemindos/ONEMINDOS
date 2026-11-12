# kairos-io/kairos#6027: docs: how to set up automatic updates for a Kairos cluster
state: open created: 2026-11-09T09:02:10Z closed: null

**Is your feature request related to a problem? Please describe.**
Kairos has no documentation page on keeping nodes up to date automatically. This is not a feature of Kairos itself. You build it in your own pipeline, with the Kairos operator or with whatever tool runs your upgrades. Users have no guidance on how.

**Describe the solution you'd like**
A docs page that shows how to set up automatic updates. It should cover:
- upgrades with the Kairos operator (NodeOpUpgrade or the current equivalent), and when to pick it
- upgrades from a CI pipeline or other external tooling
- how to pin to a release channel or semver range, so a node follows weekly releases and not only manual minors
- rollout safety: one node at a time, health checks, and rollback with the A/B partitions

**Depends on**
https://github.com/kairos-io/kairos/issues/5923. Weekly releases have to exist before there is anything to follow automatically. Write the page once the release cadence is settled.

**Describe alternatives you've considered**
N/A

