# Spike W8-1 results: PASS

**Run:** 2026-11-10 (VM clock 01:10 UTC on 2026-11-11), disposable Lima VM `w8lab`, Debian 13 cloud image (aarch64, Apple Silicon host, `vz` VM type), loopback only.

| Item | Value |
|---|---|
| nats-server | v2.15.2 (released 2026-10-26), `nats-server-v2.15.2-linux-arm64.tar.gz`, sha256 `bc2c788dcbf2849af749564e06a0d48c19bced851f2d68a2e21c54d078949b28` (matched the release `SHA256SUMS`) |
| natscli | v0.5.1 (released 2026-10-26), `nats-0.5.1-linux-arm64.zip`, sha256 `91c661f1173ee9bfe07514eef55a29d25ac7757a0868c179e825eba976073adc` (matched the release `SHA256SUMS`) |
| Configs | `hub.conf`, `leaf.conf`, `tel_hub.json` in this folder; script `run.sh`; raw output `run-1.log` |

## Result against the pre-written criteria

| Criterion | Expected | Observed | Verdict |
|---|---|---|---|
| Hub copy before outage | 100 | 100 | pass |
| Leaf stores during hub outage | 600 | 600 (all 500 acked publishes succeeded with the hub down) | pass |
| Hub count after restart | 600 within 60 s | 600 after 40 s; source lag 0 | pass |
| Payload integrity | 1..600, no gaps, no dupes | 600 lines, 600 unique, set equals 1..600 | pass |
| Core-NATS (no stream) messages from the outage | not delivered | 0 seen at the hub after restart | as expected |

## Observations
- The leaf re-established its leafnode connection about 1 s after the hub restarted (leaf log: "Leafnode connection created for account: $G"), but the hub's sourced stream took **about 40 s** to catch up. That delay is the stream-source retry, not the link. A UI that shows "site back online" should wait for source lag 0, not for the link.
- Only data written into a **JetStream stream on the leaf** survives an outage. Plain publish/subscribe traffic and request/reply are lost while the link is down. So every OneMind telemetry or event subject that must survive outages needs a leaf-local stream, and commands must carry a TTL so they are not replayed late.
- The leaf stream needs a size or age limit sized for the longest expected outage, or the leaf disk fills (not tested here).

## Not tested (moved to `22-HARDWARE-LAB-TEST-PLAN.md`)
Lossy or half-open links (tc netem), outages of days, disk-full on the leaf, leaf on a Pi 5 SD card or NVMe after power loss, 100+ leaves into one hub, NATS accounts/credentials per site, and MQTT clients publishing into the leaf's MQTT listener during the outage.
