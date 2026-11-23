# SPDX-License-Identifier: Apache-2.0
"""E2 capability broker (#186, PLG-SOCK-01): host grants for apps, only through an owner approval.

An app's pods never touch the host by default: the install sandbox (policy.py) refuses host
networking (F-01), host paths (F-04), privileged containers (F-06) and extra capabilities (F-07).
A host grant is the one way past those rules, and it is always narrow:

- `kinds.py`: what a grant can name (one device node of a known class, a GPU render node, host
  networking, real-time scheduling) and the `HostAllowance` the sandbox reads. Pure, no I/O.
- `models.py`: the table of granted and revoked grants.
- `broker.py`: files a request as a pending `host.grant` action; only an owner (a person, never an
  agent, automation or standing approval) approves it, and only then the grant becomes active.
  The owner can revoke it at any time; the next render of the app is refused again.

This package does not read or write the app schema's devices or radios keys (#724) or the radio
grant (#733); a grant is filed through the broker's routes, not declared in onemind.app.yaml.
"""
