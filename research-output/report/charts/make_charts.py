"""Charts for the founder report. Every number is copied from a cited research-output file:
scores: evidence/scorecard-rev3.md, 01 §3.1.6 (d) (rev. 4 card) and 03-base-os.md §4 · lifecycle: 03 §6.1 · cost: 01 §3.1.5 (lifecycle-cost-2036.md)
k3s footprint: C-LAB-k3s-footprint-restore-007/008, C-W4-078 · DC-20: C-LAB-minimal-image-dc20-011 · risks: 23-RISK-REGISTER.md §4."""
import sys, os, datetime as dt, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
OUT = sys.argv[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": "#888", "axes.titleweight": "bold", "axes.titlesize": 11.5})
BLUE, GREY, GOLD, RED, GREEN = "#2F5D9E", "#B8C2D1", "#C9A227", "#B04A4A", "#3F8F4F"
def save(name): plt.savefig(os.path.join(OUT, name), dpi=140, bbox_inches="tight", facecolor="white"); plt.close()

# 1. S1 base OS: rev-3 cited card vs rev-4 card (01 §3.1.6 d; rule-6 re-score C3 3 -> 4 for every RAUC stack)
names = ["Ubuntu 26.04 + RAUC (D) — decision of record", "RHEL-family bootc (C)", "Debian 13 + RAUC (A)", "Yocto + RAUC (G)", "Fedora IoT (B)", "Ubuntu Core (E)", "Buildroot + RAUC (F)"]
r3  = [62, 64, 60, 51, 52, 52, 46]
r4  = [65, 64, 63, 54, 52, 52, 49]
fig, ax = plt.subplots(figsize=(8.6, 4.2)); y = range(len(names))
ax.axvspan(62, 65, color=GOLD, alpha=0.15, lw=0); ax.text(63.5, len(names) - 0.35, "within 3 pts of leader;\nonly the top two tie", ha="center", fontsize=8, color="#7A6312")
ax.barh([i + 0.2 for i in y], r3, height=0.38, color=GREY, label="Rev. 3 card, every cell cited (withdrawn verdict)")
ax.barh([i - 0.2 for i in y], r4, height=0.38, color=[GREEN if "record" in n else BLUE for n in names], label="Rev. 4 card, frozen protocol (2026-11-11)")
for i, (a, b) in enumerate(zip(r3, r4)):
    ax.text(b + 0.4, i - 0.2, f"{b}", va="center", fontsize=8.5); ax.text(a + 0.4, i + 0.2, f"{a}", va="center", fontsize=8, color="#555")
ax.set_yticks(list(y)); ax.set_yticklabels(names); ax.invert_yaxis(); ax.set_xlim(40, 70); ax.set_xlabel("Weighted score (0–100, frozen weights)")
ax.set_title("S1 · Base OS: Ubuntu and bootc tie; the locked tie-break gives Ubuntu 6–4"); ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.16), ncol=2, fontsize=8, frameon=False)
save("chart-s1-base-os.png")

# 2. S2–S5 small multiples
panels = [("S2 · Update engine", ["Mender", "RAUC ✓", "bootc+greenboot", "Rugix"], [62, 61, 58, 52]),
          ("S3 · Kubernetes", ["k3s ✓", "RKE2", "Talos", "k0s"], [63, 62, 61, 60]),
          ("S4 · Backups", ["restic ✓", "Kopia", "Velero"], [75, 66, 49]),
          ("S5 · Kernel route", ["K1 board kernel ✓", "K2 own LTS config", "K3 CIP SLTS", "K4 patched"], [71, 66, 61, 46])]
fig, axs = plt.subplots(1, 4, figsize=(12, 3.0))
for ax, (t, n, v) in zip(axs, panels):
    cols = [GREEN if "✓" in x else GREY for x in n]
    ax.barh(range(len(n)), v, color=cols); ax.set_yticks(range(len(n))); ax.set_yticklabels(n, fontsize=8.5); ax.invert_yaxis()
    ax.set_xlim(40, 80); ax.set_title(t, fontsize=10)
    for i, x in enumerate(v): ax.text(x + 0.5, i, str(x), va="center", fontsize=8)
fig.suptitle("Other foundation scorecards (cited cells; unchanged in rev. 4). ✓ = chosen; S2 is a tie that RAUC wins on the tie-break", fontsize=10.5, y=1.04)
save("chart-s2-s5.png")

# 3. Lifecycle to 2036
D = lambda s: dt.date.fromisoformat(s)
rows = [("Debian 13", [("security", "2025-08-09", "2028-08-09", BLUE), ("LTS", "2028-08-09", "2030-06-30", "#6F93C8"), ("ELTS (paid, quote)", "2030-06-30", "2035-06-30", GREY)]),
        ("Ubuntu 26.04 LTS", [("standard", "2026-04-23", "2031-05-31", BLUE), ("Pro (paid)", "2031-05-31", "2036-05-31", GREY), ("Legacy (paid)", "2036-05-31", "2041-05-31", "#DADFE7")]),
        ("AlmaLinux 10", [("security", "2025-05-27", "2035-05-31", BLUE)]),
        ("CentOS Stream 10", [("", "2024-12-12", "2030-05-31", BLUE)]),
        ("Fedora 45", [("", "2026-10-28", "2027-12-08", BLUE)]),
        ("SUSE Linux Micro 6.2", [("", "2025-10-01", "2029-11-30", BLUE)]),
        ("Yocto Wrynose", [("", "2026-04-30", "2030-04-30", BLUE)]),
        ("Buildroot 2025.02", [("", "2025-03-01", "2028-03-31", BLUE)]),
        ("Alpine 3.24", [("", "2026-06-01", "2028-06-01", BLUE)]),
        ("Linux 6.12 / 6.18 LTS", [("kernel.org", "2024-11-17", "2028-12-31", GREEN)]),
        ("CIP 6.12 SLTS kernel", [("", "2024-11-17", "2035-06-30", GREEN)]),
        ("Raspberry Pi 5 / CM5", [("production", "2023-10-23", "2036-01-31", GOLD)]),
        ("Jetson Orin modules", [("available", "2023-03-01", "2032-01-31", GOLD)]),
        ("Jetson T5000", [("available", "2025-08-01", "2035-08-31", GOLD)])]
fig, ax = plt.subplots(figsize=(9.6, 5.0))
for i, (n, segs) in enumerate(rows):
    for lab, a, b, c in segs:
        ax.barh(i, (D(b) - D(a)).days, left=mdates.date2num(D(a)), color=c, height=0.6)
        if lab: ax.text(mdates.date2num(D(a)) + 20, i, lab, va="center", fontsize=7, color="white" if c in (BLUE, GREEN) else "#333")
ax.axvline(mdates.date2num(D("2036-12-31")), color=RED, ls="--"); ax.text(mdates.date2num(D("2036-12-31")) + 30, -0.6, "target:\nend 2036", color=RED, fontsize=8, va="top")
ax.axvline(mdates.date2num(D("2026-11-11")), color="#555", ls=":"); ax.text(mdates.date2num(D("2026-11-11")) + 30, len(rows) - 0.4, "today", fontsize=8)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=8.5); ax.invert_yaxis()
ax.xaxis_date(); ax.xaxis.set_major_locator(mdates.YearLocator(2)); ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
ax.set_xlim(mdates.date2num(D("2023-01-01")), mdates.date2num(D("2041-12-31")))
ax.set_title("No base reaches 2036 on one free release: plan one or two in-place rebases")
save("chart-lifecycle.png")

# 4. Cost per device to 2036 (base scenario)
stacks = ["Debian 13\n(A leg)", "AlmaLinux\nbootc (free)", "Ubuntu 26.04\n(Pro for Devices\n≈ $60/box assumed)", "Red Hat\nDevice Edge"]
k1 = [403, 406, 385, 1756]; k10 = [40, 41, 120, 1391]
fig, ax = plt.subplots(figsize=(8, 3.8)); x = range(len(stacks))
ax.bar([i - 0.2 for i in x], k1, width=0.38, color=BLUE, label="fleet of 1,000 units"); ax.bar([i + 0.2 for i in x], k10, width=0.38, color=GOLD, label="fleet of 10,000 units")
for i, (a, b) in enumerate(zip(k1, k10)):
    ax.text(i - 0.2, a + 25, f"${a:,}", ha="center", fontsize=8); ax.text(i + 0.2, b + 25, f"${b:,}", ha="center", fontsize=8)
ax.set_xticks(list(x)); ax.set_xticklabels(stacks, fontsize=8.5); ax.set_ylabel("USD per device, to 2036")
ax.set_title("Lifecycle cost per device to 2036 (base scenario, labour included)"); ax.legend(frameon=False, fontsize=8.5)
save("chart-cost-2036.png")

# 5. k3s footprint lab (4 GiB arm64 VM, Debian 13)
fig, ax = plt.subplots(figsize=(7.6, 2.6))
items = [("k3s added memory, idle", 936), ("k3s added memory, under load", 1529), ("memory left for apps (W4-1 lab)", 2557)]
ax.barh(range(3), [v for _, v in items], color=[BLUE, "#6F93C8", GREEN])
for i, (_, v) in enumerate(items): ax.text(v + 30, i, f"{v:,} MiB", va="center", fontsize=8.5)
ax.axvline(4096, color=RED, ls="--"); ax.text(4040, 2.45, "4 GiB box", color=RED, fontsize=8, ha="right")
ax.set_yticks(range(3)); ax.set_yticklabels([n for n, _ in items], fontsize=8.5); ax.invert_yaxis(); ax.set_xlim(0, 4300)
ax.set_title("Measured: what k3s costs on a 4 GiB arm64 box"); ax.set_xlabel("MiB")
save("chart-k3s-footprint.png")

# 6. DC-20 distro vs build-from-source CVEs
fig, ax = plt.subplots(figsize=(7.2, 2.6))
lab = ["Debian 13 minimal (mkosi)", "Buildroot target SBOM", "Buildroot, after removals"]
allv = [589, 549, 498]; ch = [186, 195, 175]
ax.barh(range(3), allv, color=GREY, label="unique CVE IDs"); ax.barh(range(3), ch, color=RED, label="of which Critical + High")
for i, (a, c) in enumerate(zip(allv, ch)): ax.text(a + 5, i, str(a), va="center", fontsize=8.5); ax.text(c - 5, i, str(c), va="center", ha="right", color="white", fontsize=8)
ax.set_yticks(range(3)); ax.set_yticklabels(lab, fontsize=8.5); ax.invert_yaxis(); ax.legend(frameon=False, fontsize=8, loc="lower right")
ax.set_title("Building from source shrinks the image 4–6×, but known holes only 7–18%")
save("chart-dc20.png")

# 7. Risk heat map from 23-RISK-REGISTER §4
risks = "RR-01 4 4;RR-02 4 4;RR-03 4 4;RR-04 4 4;RR-05 4 4;RR-06 3 5;RR-07 2 5;RR-08 3 4;RR-09 3 4;RR-10 3 4;RR-11 3 4;RR-12 4 3;RR-13 3 4;RR-14 4 3;RR-15 3 4;RR-16 4 3;RR-17 4 3;RR-18 3 4;RR-19 3 4;RR-20 3 4;RR-21 3 4;RR-22 3 4;RR-23 3 4;RR-24 3 4;RR-25 4 3;RR-26 4 3;RR-27 3 3;RR-28 3 3;RR-29 3 3;RR-30 3 3;RR-31 3 3;RR-32 3 3;RR-33 3 3;RR-34 3 3;RR-38 3 3;RR-39 3 3;RR-40 3 3;RR-45 3 3;RR-48 3 3;RR-49 3 3;RR-50 3 3;RR-51 3 3;RR-52 3 3;RR-53 3 3;RR-36 2 4;RR-44 2 4;RR-54 2 4;RR-55 2 4;RR-35 4 2;RR-37 4 2;RR-41 4 2;RR-42 4 2;RR-46 4 2;RR-43 3 2;RR-47 3 2;RR-56 3 2;RR-57 5 1;RR-60 5 1;RR-58 2 2;RR-59 2 2;RR-61 2 2;RR-62 2 2"
cells = {}
for r in risks.split(";"):
    i, l, im = r.split(); cells.setdefault((int(l), int(im)), []).append(i.replace("RR-", ""))
fig, ax = plt.subplots(figsize=(8.4, 5.6))
for l in range(1, 6):
    for im in range(1, 6):
        s = l * im; c = "#F4C7C3" if s >= 16 else "#FBE3C0" if s >= 12 else "#FFF5CC" if s >= 6 else "#E6F2E6"
        ax.add_patch(plt.Rectangle((im - 0.5, l - 0.5), 1, 1, fc=c, ec="white", lw=2))
        ids = cells.get((l, im), [])
        if ids:
            txt = "\n".join(", ".join(ids[k:k + 5]) for k in range(0, len(ids), 5))
            ax.text(im, l, f"{len(ids)} risks\n{txt}", ha="center", va="center", fontsize=6.6 if len(ids) > 10 else 7.5)
ax.set_xlim(0.5, 5.5); ax.set_ylim(0.5, 5.5); ax.set_xticks(range(1, 6)); ax.set_yticks(range(1, 6))
ax.set_xlabel("Impact (1–5)"); ax.set_ylabel("Likelihood (1–5)"); ax.set_title("Risk register: 62 risks (RR-nn) by likelihood × impact")
save("chart-risk-heatmap.png")
print("ok")
