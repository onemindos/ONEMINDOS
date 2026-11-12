#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render a battery results.json as a Markdown table (CI job summary)."""
import json, sys

r = json.load(open(sys.argv[1]))
e = r["env"]
print(f"### Battery {e['board']} up to {e['upto']}: accel={e['accel']}, host CPUs={e['host_cpus']}, {r['minutes']} min\n")
print("| Test | Verdict | Detail |\n|---|---|---|")
for t in r["results"]:
    print(f"| {t['test']} | **{t['verdict']}** | {t['detail'].replace('|', '/')[:300]} |")
