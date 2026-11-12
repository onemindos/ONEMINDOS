"""Checks the built PDF: every checklist topic's terms appear, no raw Mermaid/diagram source, all referenced
images embedded, a sane page count, and no host paths, private IPs, tailnet names or e-mail addresses."""
import glob, os, re, subprocess, sys
pdf = sys.argv[1]; here = os.path.dirname(os.path.abspath(__file__)); fails = []
txt = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
flat = re.sub(r"\s+", " ", txt.replace("­", "").replace("-\n", "")).lower()
pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout).group(1))
rows = [l.rstrip("\n").split("\t") for l in open(os.path.join(here, "checklist.tsv"), encoding="utf-8")][1:]
missing = [(t, [x for x in terms.split("|") if x.lower() not in flat]) for _, t, _, terms in rows]
missing = [(t, m) for t, m in missing if m]
for t, m in missing: fails.append(f"topic not found: {t} -> {m}")
for bad in ["```", "flowchart lr", "flowchart tb", "sequencediagram", "statediagram", "graph td", "digraph"]:
    if bad in flat: fails.append(f"raw diagram source in PDF text: {bad}")
refs = set()
for f in glob.glob(os.path.join(here, "chapters", "*.md")):
    refs |= set(re.findall(r"\]\((img/[^)\s]+)\)", open(f, encoding="utf-8").read()))
imgs = subprocess.run(["pdfimages", "-list", pdf], capture_output=True, text=True).stdout.strip().splitlines()[2:]
uniq = len({tuple(l.split()[3:7]) + (l.split()[-1],) for l in imgs})
if len(imgs) < len(refs): fails.append(f"only {len(imgs)} embedded images for {len(refs)} referenced")
for r in refs:
    if not os.path.exists(os.path.join(here, r)): fails.append(f"missing image file {r}")
hyg = {"host path": r"/users/|/home/|\.lab/", "rfc1918": r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)\b",
       "cgnat": r"\b100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d+\.\d+\b", "tailnet": r"\.ts\.net", "email": r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}"}
for k, rx in hyg.items():
    hit = re.findall(rx, flat)
    if hit: fails.append(f"hygiene {k}: {hit[:3]}")
ids = len(set(re.findall(r"c-[a-z0-9-]+-\d{3}", flat)))
print(f"pages={pages} topics={len(rows)} topics_missing={len(missing)} images_referenced={len(refs)} images_embedded={len(imgs)} claim_ids_in_text={ids}")
if not (40 <= pages <= 160): fails.append(f"page count {pages} outside 40-160")
for f in fails: print("FAIL:", f)
sys.exit(1 if fails else 0)
