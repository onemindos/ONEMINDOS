import os, sys, csv, re, yaml, collections
SRC = os.environ.get("LAB_SRC", "work/.lab/src")  # holds umbrel-apps@3a087384 and beclab/apps@37a1fb4f
OUT = os.path.dirname(os.path.abspath(__file__))

def norm(u):
    if not u: return ""
    u = str(u).strip().lower().rstrip("/")
    u = re.sub(r"\.git$", "", u)
    m = re.match(r"https?://(www\.)?github\.com/([^/]+)/([^/#?]+)", u)
    return f"github.com/{m.group(2)}/{m.group(3)}" if m else u

rows = []
um = os.path.join(SRC, "umbrel-apps")
for d in sorted(os.listdir(um)):
    p = os.path.join(um, d, "umbrel-app.yml")
    if not os.path.isfile(p): continue
    try: y = yaml.safe_load(open(p))
    except Exception as e: print("ERR", p, e, file=sys.stderr); continue
    rows.append(dict(store="umbrel", id=y.get("id", d), name=y.get("name"), category=y.get("category"),
                     repo=norm(y.get("repo")), license="", mem="", arch="",
                     perms=";".join(y.get("permissions") or [])))
ol = os.path.join(SRC, "apps")
for d in sorted(os.listdir(ol)):
    p = os.path.join(ol, d, "OlaresManifest.yaml")
    if not os.path.isfile(p): continue
    try:
        txt = open(p).read()
        txt = "\n".join(l for l in txt.splitlines() if "{{" not in l and "{%" not in l)
        y = yaml.safe_load(txt)
    except Exception as e: print("ERR", p, e, file=sys.stderr); continue
    md = y.get("metadata") or {}; sp = y.get("spec") or {}
    lic = ";".join(str(l.get("text")) for l in (sp.get("license") or []) if isinstance(l, dict))
    rows.append(dict(store="olares", id=md.get("appid") or md.get("name") or d, name=md.get("title"),
                     category=";".join(map(str, md.get("categories") or [])),
                     repo=norm(sp.get("sourceCode")), license=lic, mem=sp.get("requiredMemory", ""),
                     arch=";".join(sp.get("supportArch") or []), perms=""))
with open(os.path.join(OUT, "catalog.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
c = collections.Counter(r["store"] for r in rows); print(c)
for s in ("umbrel", "olares"):
    cc = collections.Counter()
    for r in rows:
        if r["store"] == s:
            for k in (r["category"] or "none").split(";"): cc[k] += 1
    print(s, cc.most_common(40))
# overlap by repo
ur = {r["repo"] for r in rows if r["store"] == "umbrel" and r["repo"].startswith("github.com")}
orr = {r["repo"] for r in rows if r["store"] == "olares" and r["repo"].startswith("github.com")}
print("umbrel gh repos", len(ur), "olares gh repos", len(orr), "overlap", len(ur & orr))
open(os.path.join(OUT, "overlap.txt"), "w").write("\n".join(sorted(ur & orr)))
open(os.path.join(OUT, "allrepos.txt"), "w").write("\n".join(sorted(ur | orr)))
lc = collections.Counter(r["license"] or "none" for r in rows if r["store"] == "olares")
print("olares declared licenses", lc.most_common(25))
