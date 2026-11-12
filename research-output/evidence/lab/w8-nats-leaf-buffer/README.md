# Spike W8-1: NATS leaf node store-and-forward during a hub outage

**Owner:** W8 · **Written before running:** 2026-11-10 · **Serves:** N-6, F-11, F-13, AI-7, P-8 · **Bank:** Q139, Q219, DC-02(e)

## Goal
Show whether a site node (a "leaf") keeps accepting telemetry while its link to the hub is down, and delivers it to the hub after the link returns, with no loss and no duplicates. Earlier research (`research/platform/robotics-iot-xr-nvidia.md` §7) could not confirm this from docs: "intermittent-link behavior is UNVERIFIED and must be tested".

## Hypothesis
With JetStream enabled on the leaf in its **own domain**, a stream on the leaf that captures the telemetry subjects, and a stream on the hub that **sources** from the leaf stream across the domain, messages published at the leaf during a hub outage are stored locally and copied to the hub after reconnection. Plain core-NATS (no JetStream) messages published during the outage are not delivered to hub subscribers (expected: fire-and-forget).

## Setup (pinned)
- Disposable Lima VM `w8lab` (Debian 13 template, aarch64, 2 vCPU, 2 GiB), no host mounts, no credentials.
- `nats-server` and `natscli` official release binaries from GitHub, SHA-256 checked against the release checksum file (versions and hashes recorded in `results.md`).
- Two `nats-server` processes on one VM: `hub` (JetStream domain `hub`, leafnode listener 7422) and `leaf` (JetStream domain `site1`, leafnode remote to the hub). Shared account `APP` on both.

## Steps
1. Create stream `TEL` on the leaf (`tel.>`, file storage). Create stream `TEL_HUB` on the hub with a source `TEL` from domain `site1`.
2. Publish 100 messages to `tel.greenhouse1.air.temp` at the leaf. Check hub `TEL_HUB` count.
3. Stop the hub process (simulates WAN/satellite/mesh link loss and hub reboot).
4. Publish 500 more messages at the leaf. Check leaf `TEL` count.
5. Also publish 50 core-NATS messages on `evt.test.outage` at the leaf, with a hub-side subscriber planned for after restart (shows they are not stored).
6. Restart the hub with the same store directory. Wait up to 60 s.
7. Check hub `TEL_HUB` message count and sequence/duplicate state.

## Pass / fail (fixed before the run)
- **PASS** if: leaf `TEL` = 600 after step 4, **and** hub `TEL_HUB` = 600 within 60 s of hub restart, **and** the payload sequence numbers 1..600 at the hub have no gaps and no duplicates.
- **FAIL** if the hub count is below 600 after 60 s, or duplicates/gaps appear.
- Core-NATS messages from step 5 are expected **not** to reach the hub; if they did, record it as a surprise.

## Limits of this spike
One VM, loopback network, a clean stop of the hub. It does not test packet loss, a half-open TCP link, days-long outages, disk-full on the leaf, or hundreds of leaves. Those go to `22-HARDWARE-LAB-TEST-PLAN.md`.
