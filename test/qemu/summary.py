#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render a battery results.json as a Markdown table (CI job summary).

Result files differ by test: most carry {"env": {board, accel, host_cpus, upto?}}, secureboot writes the same
facts at the top level, and some envs have no "upto". Every header field is optional; a missing one prints "?".
"""
import json, sys


def header(r):
    e = r.get("env") if isinstance(r.get("env"), dict) else {}
    g = lambda k: e.get(k, r.get(k, "?"))
    upto = f" up to {e['upto']}" if "upto" in e else ""
    cpus = e.get("host_cpus", r.get("cpus", "?"))
    return f"### Battery {g('board')}{upto}: accel={g('accel')}, host CPUs={cpus}, {r.get('minutes', '?')} min\n"


def render(r):
    out = [header(r), "| Test | Verdict | Detail |\n|---|---|---|"]
    for t in r.get("results", []):
        out.append(f"| {t.get('test', '?')} | **{t.get('verdict', '?')}** | {str(t.get('detail', '')).replace('|', '/')[:300]} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(render(json.load(open(sys.argv[1]))))
