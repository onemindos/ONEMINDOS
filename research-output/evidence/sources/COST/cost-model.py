# Lifecycle cost model to 2036 (DC-03). L/B/H = low/base/high scenario.
S = ["L","B","H"]
RATE = dict(L=65, B=120, H=300)          # USD per hour
YEARS_OPS = 10                           # 2027-2036 labour years
YEARS_SUB = 9                            # 2028-2036 per-device subscription years
# base-specific inputs
BASES = {
 "A Debian 13 (+LTS, no ELTS)": dict(
   majors=dict(L=2,B=3,H=4), h_major=dict(L=80,B=160,H=240),
   h_year=dict(L=60,B=120,H=200), fixed_year=dict(L=0,B=1200,H=4800),
   dev_once=dict(L=0,B=0,H=0), dev_year=dict(L=0,B=0,H=0)),
 "D Ubuntu 26.04 + Pro for Devices (+Legacy)": dict(
   majors=dict(L=0,B=0,H=1), h_major=dict(L=80,B=160,H=240),
   h_year=dict(L=50,B=100,H=180), fixed_year=dict(L=0,B=0,H=0),
   dev_once=dict(L=10*1.5,B=60*1.5,H=250*1.5), dev_year=dict(L=0,B=0,H=0)),
 "C Red Hat Device Edge / RHEL bootc": dict(
   majors=dict(L=1,B=1,H=2), h_major=dict(L=40,B=80,H=160),
   h_year=dict(L=80,B=180,H=350), fixed_year=dict(L=0,B=0,H=0),
   dev_once=dict(L=0,B=0,H=0), dev_year=dict(L=50,B=150,H=269)),
 "Y Yocto own-BSP (+RAUC)": dict(
   majors=dict(L=2,B=3,H=5), h_major=dict(L=120,B=240,H=480),
   h_year=dict(L=250,B=500,H=900), fixed_year=dict(L=600,B=2400,H=6000),
   dev_once=dict(L=0,B=0,H=0), dev_year=dict(L=0,B=0,H=0)),
}
# CRA lines (base-neutral except per-major re-documentation)
CRA = dict(h_year=dict(L=60,B=120,H=250), h_once=dict(L=80,B=160,H=300),
           h_per_major=dict(L=20,B=40,H=80), fixed_year=dict(L=300,B=1200,H=3000))
# Jetson add-on (per Jetson device), Jetson share of fleet
JET = dict(share=0.2, branches=dict(L=3,B=4,H=5), h_branch=dict(L=80,B=160,H=320),
           reflash_frac=dict(L=0,B=0.10,H=1.0), reflash_cost=dict(L=40,B=100,H=250))
JMULT = {"A Debian 13 (+LTS, no ELTS)":1.0,"D Ubuntu 26.04 + Pro for Devices (+Legacy)":1.0,
         "C Red Hat Device Edge / RHEL bootc":0.6,"Y Yocto own-BSP (+RAUC)":0.8}

def base_cost(b, s, N):
    p = BASES[b]; r = RATE[s]
    lab_h = p["majors"][s]*p["h_major"][s] + p["h_year"][s]*YEARS_OPS
    fixed = lab_h*r + p["fixed_year"][s]*YEARS_OPS
    per_dev = p["dev_once"][s] + p["dev_year"][s]*YEARS_SUB
    return dict(hours=lab_h, fixed=fixed, per_device=fixed/N + per_dev, fees_dev=per_dev)

def cra_cost(b, s, N):
    p = BASES[b]; r = RATE[s]
    h = CRA["h_year"][s]*YEARS_OPS + CRA["h_once"][s] + CRA["h_per_major"][s]*p["majors"][s]
    fixed = h*r + CRA["fixed_year"][s]*YEARS_OPS
    return dict(hours=h, fixed=fixed, per_device=fixed/N)

def jet_cost(b, s, N):
    nj = N*JET["share"]; r = RATE[s]
    h = JET["branches"][s]*JET["h_branch"][s]*JMULT[b]
    per = h*r/nj + JET["reflash_frac"][s]*JET["reflash_cost"][s]
    return dict(hours=h, per_jetson=per)

out=[]
for N in (1000,10000):
    out.append(f"\n## N={N}")
    out.append("base|scen|base_hours|base_per_dev|fees_per_dev|cra_hours|cra_per_dev|total_per_dev(base+cra)|per_dev_per_year|jetson_hours|jetson_addon_per_jetson_dev")
    for b in BASES:
        for s in S:
            bc=base_cost(b,s,N); cc=cra_cost(b,s,N); jc=jet_cost(b,s,N)
            tot=bc["per_device"]+cc["per_device"]
            out.append(f"{b}|{s}|{bc['hours']:.0f}|{bc['per_device']:.0f}|{bc['fees_dev']:.0f}|{cc['hours']:.0f}|{cc['per_device']:.0f}|{tot:.0f}|{tot/YEARS_SUB:.1f}|{jc['hours']:.0f}|{jc['per_jetson']:.0f}")
# flip test at base: A vs cheapest alternative (base-specific only and with CRA)
out.append("\n## Flip test (base scenario): A / cheapest alternative")
for N in (1000,10000):
    vals={b:base_cost(b,"B",N)["per_device"]+cra_cost(b,"B",N)["per_device"] for b in BASES}
    a=vals["A Debian 13 (+LTS, no ELTS)"]; alt=min(v for k,v in vals.items() if not k.startswith("A"))
    out.append(f"N={N}: A={a:.0f} cheapest alt={alt:.0f} ratio={a/alt:.2f}")
# break-even Pro for Devices one-time fee (incl. Legacy x1.5) making D == A, base scenario
out.append("\n## Break-even Pro for Devices fee (10-yr one-time, before Legacy uplift) vs A, by rate")
for N in (1000,10000):
    for s in S:
        aA=base_cost("A Debian 13 (+LTS, no ELTS)",s,N)["per_device"]+cra_cost("A Debian 13 (+LTS, no ELTS)",s,N)["per_device"]
        D="D Ubuntu 26.04 + Pro for Devices (+Legacy)"
        dNoFee=base_cost(D,s,N)["per_device"]-BASES[D]["dev_once"][s]+cra_cost(D,s,N)["per_device"]
        out.append(f"N={N} scen={s}: A={aA:.0f}, D without fee={dNoFee:.0f}, break-even P={(aA-dNoFee)/1.5:.0f} (with Legacy {aA-dNoFee:.0f})")
# rate sensitivity at base inputs
out.append("\n## Rate sensitivity (base inputs, base+CRA per device)")
for N in (1000,10000):
    for rate in (65,120,200,300):
        RATE["B"]=rate
        row=[f"{b.split()[0]}={base_cost(b,'B',N)['per_device']+cra_cost(b,'B',N)['per_device']:.0f}" for b in BASES]
        out.append(f"N={N} rate={rate}: "+", ".join(row))
    RATE["B"]=120
print("\n".join(out))

# A2: Debian 13 + ELTS (2030-07..2035-06, 5 years), then one rebase for 2035-2036.
print("\n## A2 Debian 13 + ELTS: break-even annual ELTS fee vs A (ELTS paid 5 years)")
BASES["A2"]=dict(majors=dict(L=1,B=1,H=2), h_major=BASES["A Debian 13 (+LTS, no ELTS)"]["h_major"],
   h_year=dict(L=70,B=140,H=230), fixed_year=dict(L=0,B=1200,H=4800),
   dev_once=dict(L=0,B=0,H=0), dev_year=dict(L=0,B=0,H=0))
for N in (1000,10000):
    for s in S:
        a=base_cost("A Debian 13 (+LTS, no ELTS)",s,N)["fixed"]+cra_cost("A Debian 13 (+LTS, no ELTS)",s,N)["fixed"]
        a2=base_cost("A2",s,N)["fixed"]+cra_cost("A2",s,N)["fixed"]
        print(f"N={N} scen={s}: A fixed={a:.0f}, A2 fixed before ELTS={a2:.0f}, break-even ELTS fee per year={(a-a2)/5:.0f}, A2 per device before ELTS={a2/N:.0f}")

print("\n## 25% flip thresholds: max Pro for Devices fee P (pre-Legacy) such that A > 1.25 x D")
D="D Ubuntu 26.04 + Pro for Devices (+Legacy)"; A="A Debian 13 (+LTS, no ELTS)"
for N in (1000,10000):
    for s in S:
        a=base_cost(A,s,N)["per_device"]+cra_cost(A,s,N)["per_device"]
        dn=base_cost(D,s,N)["per_device"]-BASES[D]["dev_once"][s]+cra_cost(D,s,N)["per_device"]
        print(f"N={N} {s}: P_max={(a/1.25-dn)/1.5:.1f}")
print("\n## C-free variant (AlmaLinux 10 bootc, no subscription; same labour as C)")
C="C Red Hat Device Edge / RHEL bootc"
for N in (1000,10000):
    print(N, [round(base_cost(C,s,N)["fixed"]/N + cra_cost(C,s,N)["per_device"]) for s in S])
