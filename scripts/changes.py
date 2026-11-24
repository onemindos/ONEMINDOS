# SPDX-License-Identifier: Apache-2.0
"""Change fragments: one small file per PR instead of every PR editing CHANGELOG.md and docs/leap/STATUS.md.

Why: every merge used to change the same table rows, so every other open PR conflicted, had to be
re-synced and had to re-run CI. A PR now adds only `changes/<branch with / as ->.md`. Format: changes/README.md.

usage (Python standard library only):
  python3 -I scripts/changes.py check     validate every fragment (CI)
  python3 -I scripts/changes.py render    print what collect would write
  python3 -I scripts/changes.py collect   merge fragments into CHANGELOG.md / docs/leap/STATUS.md, delete them
  python3 -I scripts/changes.py collect --preserve   collect local fragments without deleting them
  python3 -I scripts/changes.py preview   JSON preview from committed origin/main; no writes
  python3 -I scripts/changes.py generate  write that preview's documents; retain all fragments
  python3 -I scripts/changes.py audit [--prs FILE]
                                          compare STATUS rows with GitHub PR state (gh, or a
                                          `gh pr list --state all --json number,state` file); exit 1 on drift
Fetch origin/main first. Fragment states are declarations, not proof of full epic acceptance.
"""
from collections import Counter
from datetime import datetime, timezone
import json
import os
import re
import subprocess
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


def validate(path, known_ids=None, text=None):
    name = os.path.basename(path)
    errs = []
    try:
        if text is None:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        meta, body = parse(text)
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
                    cells[5] = " %s " % pr_cell(meta["pr"])
                    if note and note not in cells[2]:
                        cells[2] = cells[2].rstrip() + " (%s) " % note
                    lines[i] = "|".join(cells)
    return "\n".join(lines)


def git(*args):
    """Read source objects without checking out or modifying another worktree."""
    result = subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True)
    if result.returncode:
        raise FragmentError("cannot read committed origin/main: " + result.stderr.strip())
    return result.stdout


def epic_rows(text):
    """Only five-column epic rows, never the foundation PR or summary tables."""
    if "## Every epic\n" not in text:
        raise FragmentError("STATUS.md has no 'Every epic' heading")
    rows = []
    for line in text.split("## Every epic\n", 1)[1].splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) != 7 or not cells[1] or cells[1].lower() == "id" or cells[1].startswith("-"):
            continue
        match = STATE_RE.fullmatch(cells[3])
        if not match:
            raise FragmentError("unknown epic state for " + cells[1])
        state = match.group(1)
        rows.append((cells[1], "in-review" if state == "review" else state))
    return rows


def main_preview() -> dict:
    """Render immutable main inputs, including coverage limits, retaining duplicate rows."""
    source = git("rev-parse", "--verify", "refs/remotes/origin/main^{commit}").strip()
    status = git("show", source + ":docs/leap/STATUS.md")
    changelog = git("show", source + ":CHANGELOG.md")
    ids = {rid for rid, _ in epic_rows(status)}
    paths = git("ls-tree", "-r", "--name-only", source, "--", "changes/").splitlines()
    # First-parent history reflects landing order, not branch author timestamps.
    history = git("log", "--first-parent", "--diff-merges=first-parent", "--format=%H",
                  "--name-only", source, "--", "changes/").splitlines()
    ranks, rank = {}, 0
    for line in history:
        if re.fullmatch(r"[0-9a-f]{40,64}", line):
            rank += 1
        elif line.startswith("changes/"):
            ranks.setdefault(line, rank)
    items, declarations = [], {}
    for path in sorted(paths, key=lambda p: (-ranks.get(p, 0), p)):
        if not path.endswith(".md") or path == "changes/README.md":
            continue
        meta, body, errors = validate(path, ids, git("show", source + ":" + path))
        if errors:
            raise FragmentError(path + ": " + "; ".join(errors))
        assert meta is not None
        for rid, state, note in meta["status_rows"]:
            key = (ranks.get(path, 0), rid)
            value = (state, note, meta["branch"], meta["pr"])
            if key in declarations and declarations[key] != value:
                raise FragmentError("conflicting declarations in one main landing for " + rid)
            declarations[key] = value
        items.append((meta, body))
    status = apply_status(status, items)
    rows = epic_rows(status)
    counts = dict(sorted(Counter(state for _, state in rows).items()))
    updated_ids = {rid for meta, _ in items for rid, _, _ in meta["status_rows"]}
    updated_rows = sum(rid in updated_ids for rid, _ in rows)
    unique_ids = len({rid for rid, _ in rows})
    today = datetime.now(timezone.utc).date().isoformat()
    stamp = ("**Last updated:** %s (generated UTC from committed main `%s`; "
             "not a full row truth audit)." % (today, source))
    status, n = re.subn(r"^\*\*Last updated:\*\*.*$", stamp, status, count=1, flags=re.M)
    if n != 1:
        raise FragmentError("STATUS.md has no Last updated field")
    summary = ["## Summary", "", "| State | Rows |", "|---|---|"]
    summary.extend("| %s | %d |" % pair for pair in counts.items())
    coverage = ("(Counted from the rows below on %s UTC: %d rows, %d unique IDs; "
                "%d duplicate row(s) retained. %d row(s) updated by %d main fragment(s). "
                "States are fragment declarations or inherited baseline, not independently audited "
                "acceptance. Merged partial work is not automatically done; unmerged approvals "
                "are excluded. Historical prose below is not refreshed.)" %
                (today, len(rows), unique_ids, len(rows) - unique_ids, updated_rows, len(items)))
    pattern = r"## Summary\n.*?\(Counted from the rows below[^\n]*\)"
    status, n = re.subn(pattern, "\n".join(summary) + "\n\n" + coverage, status, count=1, flags=re.S)
    if n != 1:
        raise FragmentError("STATUS.md summary/count marker not found")
    return dict(source=source, fragments=len(items), counts=counts, rows=len(rows),
                unique_ids=unique_ids, updated_rows=updated_rows,
                status=status, changelog=apply_changelog(changelog, items))


def cmd_preview():
    print(json.dumps(main_preview(), indent=2))
    return 0


def cmd_generate():
    data = main_preview()
    if git("rev-parse", "HEAD").strip() != data["source"]:
        raise FragmentError("generate requires HEAD at origin/main; use preview on feature branches")
    outputs = [(CHANGELOG, "CHANGELOG.md", data["changelog"]),
               (STATUS, "docs/leap/STATUS.md", data["status"])]
    # Preflight both targets before writing either; never overwrite unrelated edits.
    for path, relative, rendered in outputs:
        with open(path, encoding="utf-8") as f:
            if f.read() not in (rendered, git("show", data["source"] + ":" + relative)):
                raise FragmentError("refusing to overwrite edited " + relative)
    for path, _, rendered in outputs:
        with open(path, "w", encoding="utf-8") as f:
            f.write(rendered)
    print("changes: generated %d rows from %d main fragment(s); all fragments retained" %
          (data["rows"], data["fragments"]))
    return 0


def pr_states(path=None):
    """Return {pr number: OPEN|MERGED|CLOSED} from a gh JSON file, or from `gh pr list` live."""
    if path:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    else:
        result = subprocess.run(["gh", "pr", "list", "--state", "all", "--limit", "2000",
                                 "--json", "number,state"], capture_output=True, text=True)
        if result.returncode:
            raise FragmentError("cannot read PR state from gh: " + result.stderr.strip())
        raw = result.stdout
    try:
        return {int(p["number"]): p["state"] for p in json.loads(raw)}
    except (ValueError, KeyError, TypeError) as e:
        raise FragmentError("bad PR state JSON: %s" % e)


def audit_rows(status_text, states):
    """Return drift findings (id, message) between epic rows and GitHub PR state.

    Only provable contradictions are reported: a row that says work is open while its own PR is
    merged or closed, or says done while its PR is still open. Rows whose state already says
    `(merged in #N ...)` declare a partial landing and are left alone. Rows without a PR are not judged.
    """
    findings = []
    for line in status_text.split("## Every epic\n", 1)[-1].splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) != 7 or not cells[1] or cells[1].lower() == "id" or cells[1].startswith("-"):
            continue
        rid, raw_state, pr_cell_text = cells[1], cells[3], cells[5]
        m = STATE_RE.fullmatch(raw_state)
        pr = re.match(r"\[#?(\d+)\]", pr_cell_text)
        if not m or not pr:
            continue
        state, number = m.group(1), int(pr.group(1))
        live = states.get(number)
        if live is None:
            findings.append((rid, "PR #%d is not on GitHub" % number))
        elif live == "MERGED" and state in ("todo", "in-progress", "in-review", "review") \
                and "merged in" not in raw_state:
            findings.append((rid, "row says %s but PR #%d is merged" % (state, number)))
        elif live == "CLOSED" and state in ("in-progress", "in-review", "review", "done"):
            findings.append((rid, "row says %s but PR #%d was closed unmerged" % (state, number)))
        elif live == "OPEN" and state == "done":
            findings.append((rid, "row says done but PR #%d is still open" % number))
    return findings


def cmd_audit(prs_file=None):
    with open(STATUS, encoding="utf-8") as f:
        findings = audit_rows(f.read(), pr_states(prs_file))
    for rid, msg in findings:
        print("%s: %s" % (rid, msg))
    print("changes: audit found %d drifting row(s)" % len(findings))
    return 1 if findings else 0


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


def cmd_collect(preserve=False):
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
    if not preserve:
        for p in fragments():
            os.remove(p)
    print("changes: collected %d fragment(s)" % len(items))
    return 0


def main(argv):
    if argv[1:] == ["collect", "--preserve"]:
        return cmd_collect(preserve=True)
    if len(argv) >= 2 and argv[1] == "audit" and (len(argv) == 2 or (len(argv) == 4 and argv[2] == "--prs")):
        try:
            return cmd_audit(argv[3] if len(argv) == 4 else None)
        except (FragmentError, OSError) as e:
            print("changes: " + str(e), file=sys.stderr)
            return 1
    cmds = {"check": cmd_check, "render": cmd_render, "collect": cmd_collect,
            "preview": cmd_preview, "generate": cmd_generate}
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
