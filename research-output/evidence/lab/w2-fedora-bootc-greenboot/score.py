W={"C1":20,"C2":20,"C3":15,"C4":15,"C5":10,"C6":10,"C7":10}
S={ # ranked candidates only (no FAIL gate)
"A Debian13+Rugix (+L4T flavor)":[2,3,3,3,3,3,3],
"B Fedora IoT / Fedora bootc":[3,1,3,1,4,4,2],
"C RHEL-family bootc (CS10/Alma10/RHEL10 + RHDE)":[3,1,3,3,4,3,4],
"D Ubuntu 26.04 LTS+Pro + Rugix/RAUC + JetPack":[3,3,3,3,3,2,5],
"E Ubuntu Core 24/26":[3,2,4,0,2,2,3],
"F Buildroot+RAUC (HAOS pattern)":[1,2,3,3,2,4,2],
"G Yocto/OE+RAUC (meta-tegra/-raspberrypi)":[2,3,3,2,2,4,2],
}
K=list(W)
def tot(w,s): return sum(w[k]*s[i] for i,k in enumerate(K))/5
def rank(w): r=sorted(((tot(w,s),n) for n,s in S.items()),reverse=True); return r
print("BASE"); [print(f"  {t:5.1f} {n}") for t,n in rank(W)]
print("SENS")
for k in K:
  for d in (5,-5):
    w=dict(W); w[k]+=d; rest=[x for x in K if x!=k]; s=sum(W[x] for x in rest); 
    for x in rest: w[x]=W[x]*(100-w[k])/s
    r=rank(w); print(f"  {k}{d:+d}: winner={r[0][1][:1]} {r[0][0]:.1f}  runner={r[1][1][:1]} {r[1][0]:.1f}  margin={r[0][0]-r[1][0]:.1f}  | A={tot(w,S['A Debian13+Rugix (+L4T flavor)']):.1f} C={tot(w,S['C RHEL-family bootc (CS10/Alma10/RHEL10 + RHDE)']):.1f}")
