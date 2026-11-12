#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Collect per-test fragments into results.json (paths relative to the run dir)."""
import glob, json, os, sys
R, out = sys.argv[1], sys.argv[2]
res = {}
for f in sorted(glob.glob(f"{R}/res/*.json")):
    d = json.load(open(f))
    if "id" in d: res[d["id"]] = {"verdict": d["verdict"], "detail": d["detail"]}
neg = json.load(open(f"{R}/res/t3-neg.json")) if os.path.exists(f"{R}/res/t3-neg.json") else {}
t3 = json.load(open(f"{R}/nats-t/t3-verify.json")) if os.path.exists(f"{R}/nats-t/t3-verify.json") else None
if t3 is not None:
    neg_ok = neg.get("leaf_listener_on_mesh_ip") == 1 and neg.get("other_7422_listeners") == 0 and neg.get("public_ip_7422") == "closed" \
        and neg.get("plaintext_connect_accepted") == 0 and neg.get("no_ca_leaf_connected") == 0 and neg.get("wrong_password_leaf_connected") == 0
    ok = neg_ok and t3["hub_messages"] == 1200 and t3["seconds_to_sync_after_restore"] <= 300 and all(
        v["exactly_1_to_600_in_order"] and v["local_acks_during_outage"] == 500 and v["unacked_during_outage"] == 0 for v in t3["per_node"].values())
    res["T3"] = {"verdict": "PASS" if ok else "FAIL", "detail": {"negative_checks": neg, **t3}}
t5 = f"{R}/t5/t5.json"
if os.path.exists(t5):
    d = json.load(open(t5)); c = d["combined"]
    res["T5"] = {"verdict": "PASS" if c["pss_mib_max"] <= 128 and c["cpu_pct_one_vcpu"] <= 2 else "FAIL", "detail": d}
order = ["T0", "T1a", "T1b", "T1c", "T2", "T3", "T4", "T5", "E1", "E2"]
tests = {k: res[k] for k in order if k in res}
core = [tests.get(k, {}).get("verdict") for k in order[:8]]
verdict = "PASS" if all(v == "PASS" for v in core) else ("INCOMPLETE" if None in core else "FAIL")
json.dump({"spike": "fb3-mesh-nat", "verdict": verdict, "tests": tests}, open(out, "w"), indent=1)
print(verdict, {k: v["verdict"] for k, v in tests.items()})
