"""Collects every claim ID cited in chapters/*.md, resolves it in ../evidence/claims/*.csv and writes
chapters/17-appendix-claims.md. Exits non-zero if any cited ID does not resolve. Run with python3 -I."""
import csv, glob, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
CLAIMS = os.path.join(HERE, "..", "evidence", "claims")
ledger = {}
for f in sorted(glob.glob(os.path.join(CLAIMS, "*.csv"))):
    with open(f, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            cid = (r.get("claim_id") or "").strip()
            if cid: ledger[cid] = r
text = ""
for f in sorted(glob.glob(os.path.join(HERE, "chapters", "[0-1][0-9]-*.md"))):
    if "17-appendix-claims" in f: continue
    text += open(f, encoding="utf-8").read()
cited = []
for grp in re.findall(r"\[(C-[^\]]+)\]", text):
    for part in re.split(r",\s*", grp):
        part = part.strip()
        if re.fullmatch(r"C-[A-Za-z0-9-]+-\d{3}", part) and part not in cited: cited.append(part)
missing = [c for c in cited if c not in ledger]
if missing:
    print("UNRESOLVED:", " ".join(missing)); sys.exit(1)
def key(c):
    tag, n = c.rsplit("-", 1); return (tag, int(n))
def brk(u):  # allow line breaks inside long URLs in the PDF
    return u.replace("/", "/​").replace("?", "?​").replace("&", "&​")
rows = ["# Appendix C · Sources for every claim ID in this report {#sec-claims .unnumbered}", "",
        f"This report cites **{len(cited)} claim IDs**. Each row gives the claim's source as recorded in the research ledger "
        "(`research-output/evidence/claims/*.csv`), with its source type and status. The ledger also holds the version, release date, "
        "support end, pinned commit or tag, re-check date and the files that use each claim; saved page text with SHA-256 hashes is in "
        "`research-output/evidence/sources/`. The full bibliography is `research-output/SOURCES.md`. "
        "PRIMARY = official docs, legal text or code at a pinned commit; PRIMARY-METADATA = catalogue or metadata page; "
        "SECONDARY = press or third party; lab rows are this run's own VM experiments.", "",
        "| Claim ID | Type · status | Accessed | Source |", "|---|---|---|---|"]
for c in sorted(cited, key=key):
    r = ledger[c]
    src = (r.get("source_url") or "").strip() or "(see ledger)"
    src = src.replace("|", "/")
    if len(src) > 150: src = src[:147] + "…"
    rows.append(f"| {c} | {r.get('source_type','').strip()} · {r.get('status','').strip()} | {r.get('accessed_date','').strip()} | {brk(src)} |")
open(os.path.join(HERE, "chapters", "17-appendix-claims.md"), "w", encoding="utf-8").write("\n".join(rows) + "\n")
print(f"cited={len(cited)} resolved={len(cited)}")
