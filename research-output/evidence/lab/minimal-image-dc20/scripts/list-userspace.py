import json,collections,sys
K={"linux-kernel","linux","linux-headers"}
def load(p): return [m for m in json.load(open(p))["matches"] if m["artifact"]["name"] not in K and m["artifact"]["type"]!="linux-kernel"]
b="/var/lab/dc20/out/measure/legB-buildroot/"
res={(v["id"],a["ref"]) for v in json.load(open(b+"buildroot.cdx.json")).get("vulnerabilities",[]) for a in v.get("affects",[])}
ms=[m for m in load(b+"grype-buildroot-target-cdx.json") if (m["vulnerability"]["id"],m["artifact"]["name"]) not in res]
c=collections.defaultdict(set)
for m in ms: c[(m["artifact"]["name"],m["artifact"]["version"][:20],m["vulnerability"].get("fix",{}).get("state") or "none")].add(m["vulnerability"]["id"])
print("BUILDROOT userspace (target, minus BR-resolved): pkg, version, fix-state, n unique, fixed-in examples")
for k,v in sorted(c.items(),key=lambda x:-len(x[1])):
    fx={tuple(m["vulnerability"].get("fix",{}).get("versions",[]))for m in ms if m["artifact"]["name"]==k[0]}
    print(" ",k,len(v),list(fx)[:3])
d=load("/var/lab/dc20/out/measure/legA-debian/grype-syft-rootfs-nok3s.json")
c=collections.defaultdict(set)
for m in d:
    src=(m["artifact"].get("upstreams") or [{"name":m["artifact"]["name"]}])[0]["name"]
    c[(src,m["vulnerability"].get("fix",{}).get("state"))].add(m["vulnerability"]["id"])
print("DEBIAN userspace by source package, fix-state, n unique")
for k,v in sorted(c.items(),key=lambda x:-len(x[1]))[:25]: print(" ",k,len(v))
