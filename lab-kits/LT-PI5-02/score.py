#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""LT-PI5-02 scorer (D-013, Z-10): turns the founder's observations into the outcome row that
research-output/22 (LT-PI5-02) and 01 section 3.1.6 (h) wrote down BEFORE the test, then prints how
the four D-012 (Z-40) rules read that row. It decides nothing: D-007 stays Debian 13 until Zeus says
otherwise. Pure logic, no network, no device access: run it on the Mac with the filled result.json.

  score.py result.json        print the outcome and the D-012 reading (exit 0 scored, 1 incomplete, 2 bad file)
  score.py --template         print an empty result.json to fill in

Fields (true / false, or null = not measured yet):
  h1_booted_and_healthy        step 1-2: image booted, bootc status sane, switch to the lab image healthy
  bad_image_auto_rollback      step 3: broken image (k3s fails) returned to the good one by itself
  console_or_manual_step_used  step 3: you had to touch a console or run a command to get back
  power_pull_commit            step 4: "automatic" | "manual" | "silent-downgrade" | null
  greenboot_219_fixed          the greenboot version used has #219 fixed (true / false)
"""
import json, sys

TEMPLATE = {
    "kit": "onemind.lt-pi5-02/1",
    "h1_booted_and_healthy": None,
    "bad_image_auto_rollback": None,
    "console_or_manual_step_used": None,
    "power_pull_commit": None,
    "greenboot_219_fixed": None,
    "notes": "",
}
COMMITS = {"automatic", "manual", "silent-downgrade"}

D012 = [
    "Rule 1: the tie-break counts rows across the full table; a draw comes back to Zeus.",
    "Rule 2: 'experimental' vendor support with a documented path scored 3 (doc-only) until this test; this run is the measurement.",
    "Rule 3: 'proven in production' (C4) is scored on the base layer.",
    "Rule 4: no third candidate may enter a tie (Debian does not join a bootc vs Ubuntu count).",
]

OUTCOMES = {
    "fail": (
        "FAIL",
        "bootc's Pi 5 cell drops (C.C2 3 -> 2). D-007 is confirmed: Debian 13 stays the shipping base; "
        "bootc stays the year-2 Industrial profile only.",
    ),
    "pass-open": (
        "PASS, #219 open or a manual commit step",
        "No cell or row moves (map in 01 section 3.1.6 h). Debian 13 stays the shipping base. Whether this "
        "counts as the 'W2-HW-3 passes' reopen trigger of D-007 is Zeus's call; the kit does not make it.",
    ),
    "pass-fixed-auto": (
        "PASS, #219 fixed and an automatic commit",
        "D-007's reopen condition is met. The DC-19 and lab rows are re-counted for Ubuntu vs bootc: bootc "
        "wins 6-4, or a 4-4 draw goes to Zeus (rules 1 and 4 above). Nothing changes until Zeus decides.",
    ),
}


def classify(r):
    """Return (key, missing). key is None while a required answer is still null."""
    need = ["h1_booted_and_healthy", "bad_image_auto_rollback", "console_or_manual_step_used"]
    missing = [k for k in need if r.get(k) is None]
    if missing:
        return None, missing
    # An early failure is a FAIL as soon as it is known; steps after it are not needed.
    if r["h1_booted_and_healthy"] is False:
        return "fail", []
    if r["bad_image_auto_rollback"] is False or r["console_or_manual_step_used"] is True:
        return "fail", []
    pc, fixed = r.get("power_pull_commit"), r.get("greenboot_219_fixed")
    if pc is None or fixed is None:
        return None, [k for k, v in (("power_pull_commit", pc), ("greenboot_219_fixed", fixed)) if v is None]
    if pc not in COMMITS:
        raise ValueError("power_pull_commit must be one of %s or null, got %r" % (sorted(COMMITS), pc))
    return ("pass-fixed-auto" if (pc == "automatic" and fixed is True) else "pass-open"), []


def report(r):
    key, missing = classify(r)
    if key is None:
        return 1, "INCOMPLETE: still to measure: " + ", ".join(missing)
    title, consequence = OUTCOMES[key]
    out = ["LT-PI5-02 outcome: " + title, "Consequence: " + consequence, "", "Read under D-012 (Z-40):"]
    out += ["- " + line for line in D012]
    return 0, "\n".join(out)


def main(argv):
    if argv == ["--template"]:
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        with open(argv[0]) as f:
            r = json.load(f)
        code, text = report(r)
    except (OSError, ValueError) as e:
        print("score.py: %s" % e, file=sys.stderr)
        return 2
    print(text)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
