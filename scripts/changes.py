# SPDX-License-Identifier: Apache-2.0
"""Change fragments: one small file per PR instead of every PR editing CHANGELOG.md and docs/leap/STATUS.md.

Why: every merge used to change the same table rows, so every other open PR conflicted, had to be
re-synced and had to re-run CI. A PR now adds only `changes/<branch with / as ->.md`. Format: changes/README.md.

usage (Python standard library only):
  python3 -I scripts/changes.py check     validate every fragment (CI)
  python3 -I scripts/changes.py render    print what collect would write
  python3 -I scripts/changes.py collect   merge fragments into CHANGELOG.md / docs/leap/STATUS.md, delete them
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANGES = os.path.join(ROOT, "changes")
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")
STATUS = os.path.join(ROOT, "docs", "leap", "STATUS.md")
STATES = {"todo", "in-progress", "in-review", "review", "done", "parked", "superseded"}
STATE_RE = re.compile(r"^(" + "|".join(sorted(STATES, key=len, reverse=True)) + r")( \(.*\))?$")
REPO_URL = "https://github.com/onemindos/ONEMINDOS/pull/"
UNRELEASED = "## Unreleased / in progress"


class FragmentError(Exception):
    pass


def slug(branch):
    return branch.replace("/", "-")


def parse(text):
    """Return (meta, body). meta: pr, branch, status_rows (list of (id, state, note))."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FragmentError("must start with a '---' front matter line")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FragmentError("front matter is not closed with '---'")
    meta = {"status_rows": []}
    in_rows = False
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if in_rows and re.match(r"^\s+-\s", raw):
            parts = [p.strip() for p in raw.split("-", 1)[1].split("|")]
            if len(parts) < 2 or len(parts) > 3 or not parts[0] or not parts[1]:
                raise FragmentError("bad status_rows line (want 'ID | state | note'): " + raw.strip())
            meta["status_rows"].append((parts[0], parts[1], parts[2] if len(parts) == 3 else ""))
            continue
        m = re.match(r"^(\w+):\s*(.*)$", raw)
        if not m:
            raise FragmentError("cannot parse front matter line: " + raw.strip())
        key, val = m.group(1), m.group(2).strip().strip('"')
        in_rows = key == "status_rows"
        if key in ("pr", "branch"):
            meta[key] = val
        elif key != "status_rows":
            raise FragmentError("unknown front matter key: " + key)
    body = " ".join(" ".join(lines[end + 1:]).split())
    return meta, body


def validate(path, known_ids=None):
    name = os.path.basename(path)
    errs = []
    try:
        with open(path, encoding="utf-8") as f:
            meta, body = parse(f.read())
    except (FragmentError, OSError, UnicodeDecodeError) as e:
        return None, None, [str(e)]
    pr, branch = meta.get("pr", ""), meta.get("branch", "")
    if not (pr == "pending" or re.fullmatch(r"[1-9]\d*", pr)):
        errs.append('pr must be a number or "pending"')
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        errs.append("branch is missing or has odd characters")
    elif name != slug(branch) + ".md":
        errs.append("file name must be %s.md (branch with / replaced by -)" % slug(branch))
    if not body:
        errs.append("body (the CHANGELOG text) is empty")
    if "|" in body:
        errs.append("body must not contain '|' (it would break the table row)")
    for rid, state, note in meta["status_rows"]:
        if not STATE_RE.match(state):
            errs.append("status row %s: unknown state %r (use one of %s)" % (rid, state, ", ".join(sorted(STATES))))
        if "|" in note:
            errs.append("status row %s: note must not contain '|'" % rid)
        if known_ids is not None and rid not in known_ids:
            errs.append("status row %s: no such ID in docs/leap/STATUS.md" % rid)
    return meta, body, errs


def fragments():
    if not os.path.isdir(CHANGES):
        return []
    return sorted(os.path.join(CHANGES, n) for n in os.listdir(CHANGES)
                  if n.endswith(".md") and n != "README.md")


def status_ids():
    ids = set()
    try:
        with open(STATUS, encoding="utf-8") as f:
            for line in f:
                cells = [c.strip() for c in line.split("|")]
                if len(cells) >= 7 and cells[1] and cells[1] not in ("ID", "PR") and not cells[1].startswith("-"):
                    ids.add(cells[1])
    except OSError:
        return None
    return ids


def load_all():
    ids, out, bad = status_ids(), [], False
    for p in fragments():
        meta, body, errs = validate(p, ids)
        for e in errs:
            print("changes/%s: %s" % (os.path.basename(p), e), file=sys.stderr)
            bad = True
        if not errs:
            out.append((meta, body))
    return out, bad


def pr_cell(pr):
    return "[#%s](%s%s)" % (pr, REPO_URL, pr) if pr.isdigit() else "PR pending"


def changelog_row(meta, body):
    return "| `%s` | %s | %s |" % (meta["branch"], pr_cell(meta["pr"]), body)


def apply_changelog(text, items):
    """Insert (or replace, by branch) one row per fragment at the top of the Unreleased table."""
    lines = text.split("\n")
    try:
        start = lines.index(UNRELEASED)
    except ValueError:
        raise FragmentError("CHANGELOG.md has no '%s' heading" % UNRELEASED)
    sep = next((i for i in range(start, len(lines)) if lines[i].startswith("|---")), None)
    if sep is None:
        raise FragmentError("CHANGELOG.md Unreleased table not found")
    end = sep + 1
    while end < len(lines) and lines[end].startswith("|"):
        end += 1
    rows = lines[sep + 1:end]
    for meta, body in items:
        key = "| `%s` |" % meta["branch"]
        rows = [r for r in rows if not r.startswith(key)]
        rows.insert(0, changelog_row(meta, body))
    return "\n".join(lines[:sep + 1] + rows + lines[end:])


def apply_status(text, items):
    """Set state/branch/PR (and add the note) on existing rows. Columns: ID | what | state | branch | PR."""
    lines = text.split("\n")
    for meta, _ in items:
        for rid, state, note in meta["status_rows"]:
            for i, line in enumerate(lines):
                cells = line.split("|")
                if len(cells) >= 7 and cells[1].strip() == rid:
                    cells[3] = " %s " % state
                    cells[4] = " `%s` " % meta["branch"]
                    if meta["pr"].isdigit():
                        cells[5] = " %s " % pr_cell(meta["pr"])
                    if note and note not in cells[2]:
                        cells[2] = cells[2].rstrip() + " (%s) " % note
                    lines[i] = "|".join(cells)
                    break
    return "\n".join(lines)


def cmd_check():
    items, bad = load_all()
    if bad:
        return 1
    print("changes: %d fragment(s) ok" % len(items))
    return 0


def cmd_render():
    items, bad = load_all()
    if bad:
        return 1
    print("CHANGELOG.md rows (top of '%s' table):" % UNRELEASED)
    for meta, body in items:
        print(changelog_row(meta, body))
    print("\nSTATUS.md rows to update (ID -> state):")
    for meta, _ in items:
        for rid, state, note in meta["status_rows"]:
            print("%s -> %s%s" % (rid, state, " (%s)" % note if note else ""))
    return 0


def cmd_collect():
    items, bad = load_all()
    if bad:
        return 1
    if not items:
        print("changes: nothing to collect")
        return 0
    with open(CHANGELOG, encoding="utf-8") as f:
        cl = apply_changelog(f.read(), items)
    with open(STATUS, encoding="utf-8") as f:
        st = apply_status(f.read(), items)
    with open(CHANGELOG, "w", encoding="utf-8") as f:
        f.write(cl)
    with open(STATUS, "w", encoding="utf-8") as f:
        f.write(st)
    for p in fragments():
        os.remove(p)
    print("changes: collected %d fragment(s)" % len(items))
    return 0


def main(argv):
    cmds = {"check": cmd_check, "render": cmd_render, "collect": cmd_collect}
    if len(argv) != 2 or argv[1] not in cmds:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        return cmds[argv[1]]()
    except FragmentError as e:
        print("changes: " + str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
