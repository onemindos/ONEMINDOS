---
title: Security
description: What OneMind protects today, what it does not protect yet, and the plan.
status: mixed
---

<!-- SPDX-License-Identifier: Apache-2.0 -->

This page says plainly what is protected now and what is not, because a security page that only lists strengths is marketing.

## Protected today <span class="om-tag om-tag--ok">works today</span>

- **Human approval in the gateway.** State changes are actions that only an owner can approve. Agents cannot approve, and refused attempts are logged.
- **Tamper-evident audit log.** Hash-chained, so edits, deletions and reordering are detectable.
- **No usable secrets at rest for tokens.** The gateway's tokens file stores only SHA-256 hashes of tokens.
- **Privacy in heartbeats.** No serials, MACs, IPs or user names leave a node.
- **Pinned supply chain for the OS build.** The Debian base, k3s, RAUC and every CI action are pinned by digest, hash or commit in [`os/versions.lock.yaml`](https://github.com/onemindos/ONEMINDOS/blob/main/os/versions.lock.yaml). CI checks the installer's k3s and Debian pins in `deploy/` against that file (`deploy/check-pins.py`).
- **Public-repo hygiene.** gitleaks and pattern checks for secrets, private addresses and host paths run on every pull request.
- **Scan gate for apps.** No install without a passing Trivy and ClamAV scan newer than 7 days, checked again at the moment of approval.

## Being built <span class="om-tag om-tag--unknown">being built</span>

- **Nightly security rebuilds** of the image when Debian ships a fix, signed and published to the security channel. The pipeline is on `main`; nothing is published yet.

The box side, the update client that verifies signed TUF metadata, is on `main` but has nothing to install until the image ships ([Updates and rollback](../updates-and-rollback/)).

## In review <span class="om-tag om-tag--warn">in review</span>

- **App sandbox**: restricted Pod Security and default-deny network rules for apps, and narrower Kubernetes permissions for the gateway.
- **Household identity**: sessions, passkeys and scoped API tokens instead of static tokens.

## Not protected yet

These are **v0 shortcuts**, written down so nobody mistakes them for features:

- **Static bearer tokens.** Single sign-on with a local identity provider comes later.
- **Plain HTTP to the hub.** TLS with a per-box certificate authority comes with the gateway's HTTPS. Keep the hub on a trusted network.
- **Developer installs have no rollback** and no verified boot.
- **Nodes publish straight to the hub's NATS.** Authenticated leaf links come with the fabric.

## Planned

- **Secure Boot, TPM-sealed disk keys and a verified root.** The disk layout and boot loader are being chosen now so these can be added later without repartitioning.
- **App sandboxing** by default: restricted Pod Security, default-deny network egress, AppArmor; a gVisor sandbox for untrusted or AI-generated code.
- **EU Cyber Resilience Act**: OneMind counts as an operating system, an "important product". The update policy (automatic security updates on by default, easy opt-out) is designed with that in mind.

## Reporting a problem

See [Community](../../../community/#security).
