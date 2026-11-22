#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Certified hardware list as data (S-11, Refs #234).

One YAML file per machine in lab-kits/hardware/machines/, the reference-box criteria for gate G1 in
lab-kits/hardware/reference-box.yaml, and a generated table in lab-kits/hardware/CERTIFIED.md.

  python3 -I scripts/hardware_list.py check    # validate the data and that CERTIFIED.md is current
  python3 -I scripts/hardware_list.py render   # rewrite CERTIFIED.md

The rule that matters: a machine is "unproven" until its kit has passed on real hardware. An unproven
machine may not list anything under what_works, and a proven one must name its result file, date and
image version. Support is never claimed without a recorded test.
"""
import datetime, os, re, sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, "lab-kits", "hardware")
CLASSES = {"x86-mini-pc", "x86-all-in-one", "sbc", "cloud"}
STATUSES = {"unproven", "proven"}
TEXT = ["name", "cpu", "ram", "disk", "network", "tpm"]
LISTS = ["firmware_needed", "what_works", "what_does_not"]
KEYS = {"id", "name", "class", "board", "status", "cpu", "ram", "disk", "network", "tpm", "firmware_needed",
        "what_works", "what_does_not", "kit", "kit_pending", "result", "proven_on", "image_version"}
# public repo: nothing that looks like a private address, MAC, e-mail or home path may enter the list
PRIVATE = re.compile(r"\b(?:10\.\d+|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.\d+\b|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}"
                     r"|[\w.+-]+@[\w-]+\.\w+|/Users/|/home/", re.I)


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def machines(root=ROOT):
    d = os.path.join(root, "lab-kits", "hardware", "machines")
    return [(n, load(os.path.join(d, n))) for n in sorted(os.listdir(d)) if n.endswith(".yaml")]


def check_machine(fname, m, root=ROOT):
    e = []
    if not isinstance(m, dict):
        return [f"{fname}: not a mapping"]
    if set(m) - KEYS:
        e.append(f"{fname}: unknown keys {sorted(set(m) - KEYS)}")
    for k in KEYS - {"kit_pending"}:
        if k not in m:
            e.append(f"{fname}: missing {k}")
    if e:
        return e
    if m["id"] != fname[:-5]:
        e.append(f"{fname}: id must equal the file name")
    if m["class"] not in CLASSES:
        e.append(f"{fname}: class must be one of {sorted(CLASSES)}")
    if m["status"] not in STATUSES:
        e.append(f"{fname}: status must be one of {sorted(STATUSES)}")
    for k in TEXT:
        if not isinstance(m[k], str) or not m[k].strip():
            e.append(f"{fname}: {k} must be non-empty text (write UNVERIFIED if unknown)")
    for k in LISTS:
        if not isinstance(m[k], list) or not all(isinstance(x, str) and x.strip() for x in m[k]):
            e.append(f"{fname}: {k} must be a list of text")
    if not os.path.isdir(os.path.join(root, "os", "boards", str(m["board"]))):
        e.append(f"{fname}: board {m['board']} is not in os/boards/")
    kit_dir = os.path.join(root, "lab-kits", str(m["kit"]))
    if not os.path.isdir(kit_dir) and not m.get("kit_pending"):
        e.append(f"{fname}: kit {m['kit']} is not in lab-kits/ (say where it is coming from in kit_pending)")
    if m.get("kit_pending") and os.path.isdir(kit_dir):
        e.append(f"{fname}: kit_pending is set but the kit exists; remove kit_pending")
    if m["status"] == "unproven":
        if m["what_works"]:
            e.append(f"{fname}: an unproven machine must have an empty what_works (no claim without a test)")
        for k in ("result", "proven_on", "image_version"):
            if m[k] is not None:
                e.append(f"{fname}: {k} must be null while unproven")
    else:
        if m.get("kit_pending"):
            e.append(f"{fname}: a proven machine needs its kit in the repo")
        if not m["what_works"]:
            e.append(f"{fname}: a proven machine must say what works")
        if not m["result"] or not os.path.isfile(os.path.join(root, str(m["result"]))):
            e.append(f"{fname}: result must be an existing file (the recorded kit result)")
        d = m["proven_on"]
        if not isinstance(d, (datetime.date, str)) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(d)):
            e.append(f"{fname}: proven_on must be a date YYYY-MM-DD")
        if not isinstance(m["image_version"], str) or not m["image_version"].strip():
            e.append(f"{fname}: image_version is required when proven")
        for k in TEXT:
            if "UNVERIFIED" in str(m[k]):
                e.append(f"{fname}: {k} is still UNVERIFIED on a proven machine")
    blob = yaml.safe_dump(m)
    if PRIVATE.search(blob):
        e.append(f"{fname}: looks like a private address, MAC, e-mail or host path; remove it")
    return e


def check_reference(root=ROOT):
    r = load(os.path.join(root, "lab-kits", "hardware", "reference-box.yaml"))
    e, seen = [], set()
    if r.get("gate") != "G1":
        e.append("reference-box.yaml: gate must be G1")
    for c in r.get("criteria") or []:
        if not re.fullmatch(r"RB-\d+", str(c.get("id"))) or c["id"] in seen:
            e.append(f"reference-box.yaml: bad or repeated id {c.get('id')}")
        seen.add(c.get("id"))
        if not str(c.get("text", "")).strip():
            e.append(f"reference-box.yaml: {c.get('id')} has no text")
        if not os.path.isdir(os.path.join(root, "lab-kits", str(c.get("kit")))):
            e.append(f"reference-box.yaml: {c.get('id')} names kit {c.get('kit')} which is not in lab-kits/")
    if not seen:
        e.append("reference-box.yaml: no criteria")
    return e, r


def cell(s):
    return str(s).replace("|", "/").replace("\n", " ")


def render(root=ROOT):
    ms = machines(root)
    _, ref = check_reference(root)
    o = ["<!-- SPDX-License-Identifier: Apache-2.0 -->",
         "<!-- GENERATED by scripts/hardware_list.py render from machines/*.yaml and reference-box.yaml. Do not edit. -->",
         "# Certified hardware", "",
         "A machine is **certified** only after its lab kit has passed on that real machine and the result is filed. "
         "Until then it is listed as **UNPROVEN**, and nothing is claimed to work. No machine is certified today.", "",
         "| Machine | Class | Status | CPU | RAM | Disk | Network | TPM | Kit | Proven on | Image |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, m in ms:
        kit = f"`{m['kit']}`" + (f" ({cell(m['kit_pending'])})" if m.get("kit_pending") else "")
        st = "**proven**" if m["status"] == "proven" else "UNPROVEN"
        o.append("| " + " | ".join([cell(m["name"]), m["class"], st, cell(m["cpu"]), cell(m["ram"]), cell(m["disk"]),
                                    cell(m["network"]), cell(m["tpm"]), kit, str(m["proven_on"] or "-"),
                                    cell(m["image_version"] or "-")]) + " |")
    o += ["", "## Per machine: firmware, what works, what does not", ""]
    for _, m in ms:
        o.append(f"### {m['name']}")
        for title, k in (("Firmware needed", "firmware_needed"), ("What works", "what_works"),
                         ("What does not (known gaps)", "what_does_not")):
            o.append(f"- {title}: " + ("; ".join(m[k]) if m[k] else "none recorded"))
        o.append("")
    o += ["## Reference box criteria for gate G1", "",
          "The reference box is the one machine we name as the buy-this-one answer. It must meet all of these, "
          "measured by the kit shown, on the real machine.", "",
          "| ID | Criterion | Measured by |", "|---|---|---|"]
    for c in ref["criteria"]:
        o.append(f"| {c['id']} | {cell(c['text'])} | `{c['kit']}` |")
    return "\n".join(o) + "\n"


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "check"
    out = os.path.join(HW, "CERTIFIED.md")
    if cmd == "render":
        with open(out, "w", encoding="utf-8") as f:
            f.write(render())
        return 0
    errs = []
    for n, m in machines():
        errs += check_machine(n, m)
    errs += check_reference()[0]
    if not errs:
        want = render()
        have = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
        if want != have:
            errs.append("lab-kits/hardware/CERTIFIED.md is stale: run python3 -I scripts/hardware_list.py render")
    for e in errs:
        print("FAIL", e)
    print("hardware list:", "FAIL" if errs else "PASS")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
