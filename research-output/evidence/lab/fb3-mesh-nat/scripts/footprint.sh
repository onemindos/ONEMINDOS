#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# T5: idle cost of home-a's tailscaled + NATS leaf (PSS, RSS, CPU) over WINDOW_S after SETTLE_S.
set -uo pipefail; . "$(dirname "$0")/lib.sh"
SETTLE_S=${SETTLE_S:-120}; WINDOW_S=${WINDOW_S:-600}; L=$R/t5; mkdir -p $L
TS=$(pgrep -f "tailscaled --statedir=$R/home-a " | head -1); NL=$(pgrep -f "nats-server -c $R/nats/home-a.conf" | head -1)
log "T5 pids tailscaled=$TS ($(cat /proc/$TS/comm)) natsleaf=$NL ($(cat /proc/$NL/comm)); settle ${SETTLE_S}s"
sleep $SETTLE_S
cpu(){ awk '{print $14+$15}' /proc/$1/stat; }
pss(){ awk '/^Pss:/{print $2}' /proc/$1/smaps_rollup; }
rss(){ awk '/^VmRSS:/{print $2}' /proc/$1/status; }
c0t=$(cpu $TS); c0n=$(cpu $NL); t0=$(date +%s.%N); echo "t,ts_pss_kb,ts_rss_kb,leaf_pss_kb,leaf_rss_kb" > $L/samples.csv
for i in $(seq 0 30 $WINDOW_S); do echo "$i,$(pss $TS),$(rss $TS),$(pss $NL),$(rss $NL)" >> $L/samples.csv; [ $i -lt $WINDOW_S ] && sleep 30; done
c1t=$(cpu $TS); c1n=$(cpu $NL); t1=$(date +%s.%N); HZ=$(getconf CLK_TCK)
python3 - "$L" "$c0t" "$c1t" "$c0n" "$c1n" "$t0" "$t1" "$HZ" <<'PY'
import csv, json, sys
L, c0t, c1t, c0n, c1n, t0, t1, hz = sys.argv[1], *map(float, sys.argv[2:])
rows = list(csv.DictReader(open(f"{L}/samples.csv"))); el = t1 - t0
f = lambda k: [int(r[k]) / 1024 for r in rows]
comb = [a + b for a, b in zip(f("ts_pss_kb"), f("leaf_pss_kb"))]
cpu_t = (c1t - c0t) / hz / el * 100; cpu_n = (c1n - c0n) / hz / el * 100
out = {"window_s": round(el), "samples": len(rows),
       "tailscaled": {"pss_mib_mean": round(sum(f("ts_pss_kb")) / len(rows), 1), "rss_mib_max": round(max(f("ts_rss_kb")), 1), "cpu_pct_one_vcpu": round(cpu_t, 3), "cpu_s": (c1t - c0t) / hz},
       "nats_leaf": {"pss_mib_mean": round(sum(f("leaf_pss_kb")) / len(rows), 1), "rss_mib_max": round(max(f("leaf_rss_kb")), 1), "cpu_pct_one_vcpu": round(cpu_n, 3), "cpu_s": (c1n - c0n) / hz},
       "combined": {"pss_mib_max": round(max(comb), 1), "pss_mib_mean": round(sum(comb) / len(comb), 1), "cpu_pct_one_vcpu": round(cpu_t + cpu_n, 3)},
       "budget": {"pss_mib": 128, "cpu_pct": 2}}
ok = out["combined"]["pss_mib_max"] <= 128 and out["combined"]["cpu_pct_one_vcpu"] <= 2
json.dump(out, open(f"{L}/t5.json", "w"), indent=1); print(("PASS" if ok else "FAIL") + " " + json.dumps(out))
PY
