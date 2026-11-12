"""Writes chapters/16-appendix-checklist.md from checklist.tsv, labelling each link with its chapter and
section title. Fails if a checklist row points at a section ID that no chapter defines. Run with python3 -I."""
import glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
titles, chap = {}, 0
for f in sorted(glob.glob(os.path.join(HERE, "chapters", "[0-1][0-9]-*.md"))):
    if os.path.basename(f).startswith(("16-", "17-")): continue
    for line in open(f, encoding="utf-8"):
        m = re.match(r"^(#{1,3}) (.+?) \{#(sec-[a-z0-9-]+)([^}]*)\}\s*$", line)
        if not m: continue
        level, title, sid, cls = len(m.group(1)), m.group(2), m.group(3), m.group(4)
        if level == 1 and "unnumbered" not in cls: chap += 1; cur = chap
        label = f"Ch. {cur}" if "unnumbered" not in cls else "Appendix"
        titles[sid] = f"{label}: {title.replace('|', '/')}"
rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(HERE, "checklist.tsv"), encoding="utf-8")][1:]
bad = [r[2] for r in rows if r[2] not in titles]
if bad: print("UNKNOWN SECTION IDS:", bad); sys.exit(1)
out = ["# Appendix A · Topic checklist: every topic from the founding session {#sec-checklist .unnumbered}", "",
       "Built from `context/00-CONVERSATION-RECORD.md` (sections 1–14, numbered in the first column) plus the deep dives the brief "
       "names (marked –). Each row links to where the topic is answered. The build's verification step (`verify_pdf.py`) checks that "
       "every row's key terms appear in this PDF's text; the terms are listed in `report/checklist.tsv`.", "",
       "| § | Topic | Answered in |", "|---|---|---|"]
for s, t, sid, _ in rows: out.append(f"| {s} | {t} | [{titles[sid]}](#{sid}) |")
open(os.path.join(HERE, "chapters", "16-appendix-checklist.md"), "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"checklist rows={len(rows)}")
