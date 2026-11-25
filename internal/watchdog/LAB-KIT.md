# Hub watchdog lab kit (issue #687, founder device proof)

What this proves: with the internet off, pulling the hub's power makes a peer node sound its local alert within 2 minutes. The Go test `TestHubStopsPeerAlertsWithin2MinutesNoInternet` proves the logic with a fake clock; this kit proves it on real machines.

You need: the daily-use hub, one other OneMind node (the peer), both on the same LAN switch. Unplug the router's uplink (or the WAN cable) so there is no internet. A speaker or any program that makes a noise on the peer is enough as the "siren".

## 1. On the peer node (as root)

On the image `/etc` and `/usr` are read-only, so everything goes in the node's writable etc dir, `/data/onemind/etc` (the same place `onemindd.service` points `ONEMIND_ETC_DIR` at). On a box set up by `deploy/install.sh` use `/etc/onemind` instead.

```sh
E=/data/onemind/etc
# a shared alert key: 32 random bytes, the same file on every machine that sends or listens
umask 077; head -c 32 /dev/urandom | base64 > $E/watchdog.key
cat > $E/hub-siren <<'S'
#!/bin/sh
# log to the journal: onemindd has PrivateTmp, so a temp file would be invisible to your shell
logger -t hub-siren "$ONEMIND_WATCHDOG_EVENT after $ONEMIND_WATCHDOG_SILENT_S s"
[ "$ONEMIND_WATCHDOG_EVENT" = hub_down ] && speaker-test -t sine -f 880 -l 1 >/dev/null 2>&1
S
chmod 0755 $E/hub-siren
cat > $E/watchdog.json <<J
{"hub_timeout_s": 60, "hook": ["$E/hub-siren"], "key_file": "$E/watchdog.key", "listen": true}
J
# the image firewall drops all input; open the alert port for the LAN only (the "lan" chain is reached only from private sources).
# This rule lives in memory: run it again after a reboot or a firewall restart.
nft add rule inet onemind_host lan udp dport 7481 accept
systemctl restart onemindd
```

## 2. Optional: a second node that pushes to the peer

Copy the same key to it and set `"peers": ["<peer LAN address>"]` in its `watchdog.json`. Do step 1's `nft add rule` line on the peer first, because the image drops UDP 7481 by default. The alert then reaches the peer over UDP port 7481 even if the peer's own NATS link is down.

## 3. The test

1. Confirm the internet is off: `curl -m 3 https://example.com` must fail on both machines.
2. Quiet period: wait 3 minutes after the restart, longer than the 60 s timeout. `journalctl -u onemindd | grep watchdog` and `journalctl -t hub-siren` must show no alert in that time. If one appears, stop: the peer is not seeing the hub (check `onemind fabric status`), and the test would prove nothing.
3. Only after the quiet period, note the time, then pull the hub's power cord.
4. Expected: the siren sounds on the peer and `journalctl -t hub-siren` has a `hub_down` line within 2 minutes (the leaf notices the dead link within 45 s, then the 60 s timeout runs: 105 s at worst, often about 70 to 100 s).
5. Plug the hub back in. When it beats again the peer logs `hub_recovered`.

Record: the pull time, the `hub_down` line time, and the difference. Pass means 120 s or less. Send the log line, not the key. The phone half of the proof belongs to the wave P phone watcher.
