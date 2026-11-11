# W5 P0-1 refuter: longevity and vendor risk

| Field | Value |
|---|---|
| Claim | W5-P0-1: on k3s v1.37.2+k3s1 with the default single-server SQLite datastore, `k3s etcd-snapshot` cannot back up the cluster. With no managed etcd driver, k3s answers its `/db/` snapshot routes with "etcd datastore disabled", and `k3s etcd-snapshot save` exits 1 with that error. |
| Cited claims | C-W5-001 (k3s `pkg/cluster/managed.go` @f6973cb L70-L75, L145-L157), C-W5-002 (lab log a1.log) |
| Lens | Longevity and vendor risk (third refuter; technical and security ran earlier) |
| Protocol | RESEARCH-MISSION.md §2 rule 7. This refuter read only the claim, its cited sources and the new sources below; it did not read the author's reasoning or the other refuter files first. |
| Date | 2026-11-11 |
| Verdict | **upheld**, with one longevity condition attached to the decision that rests on it |

## 1. Cited sources re-opened

| Source | Result |
|---|---|
| `k3s-io/k3s@f6973cb pkg/cluster/managed.go` | Confirmed. `registerDBHandlers` returns `handlerNoEtcd(handler)` when `c.managedDB == nil`; `handlerNoEtcd` answers every `/db/` route with `errors.New("etcd datastore disabled")`, HTTP 400. |
| Lab C-W5-002 | Not re-run by this refuter. The log path is outside the repo (`work/.lab/...`), so the reproduction can't be checked from the public PR. It doesn't change the verdict, because the code alone establishes the claim. |

## 2. Strongest counter-argument (longevity)

"The claim is pinned to one patch release. k3s and kine change fast (17-18 month minors, a new kine driver per release), so 'etcd-snapshot can't back up SQLite' is a statement about today's code, not something a 10-year architecture can rely on. If a future k3s gives kine a snapshot endpoint, ADR-001 D5's original wording becomes right again. If k3s instead moves the single-server default away from SQLite (it just added T4 and Memory drivers [C-REF-W5-longevity-008]), the whole SQLite-specific procedure becomes legacy."

## 3. New failure-seeking sources

| ID | What it shows | Effect on the claim |
|---|---|---|
| C-REF-W5-longevity-001 | kine maintainer, 2021: "Kine will never support dumping to an etcd compatible snapshot, as it doesn't use the same database format." The supported route is `--cluster-init` migration to embedded etcd, then etcd snapshots. | **Strengthens** the claim's durability. The vendor states this as a design limit, not a missing feature. The first half of the counter-argument fails. |
| C-REF-W5-longevity-002 | In k3s v1.32.5+k3s1 the SQLite-to-etcd migration (`--cluster-init`) **panicked in kine's compactor, and the restart came up as an empty cluster**. Maintainer: "this was broken by k3s-io/kine#464." Fixed through k3s PR #12293. | Doesn't touch the claim. It does hit the **escape hatch** the claim pushes users towards (convert to etcd to get snapshots). The exit path has regressed silently once. |
| C-REF-W5-longevity-003 | k3s had **no end-to-end test** of SQLite-to-etcd migration until a maintainer asked for one in June 2025, after the regression. | Same as above: the exit path only became regression-tested in mid-2025. |
| C-REF-W5-longevity-008 | k3s 1.37 adds kine T4 (S3-backed) and Memory drivers. The release post doesn't mention SQLite, and no deprecation of SQLite was found. | Neutral. There's no sign that the SQLite default is being removed, but kine's investment is going into new drivers. |

Search terms used: k3s sqlite corruption kine; k3s etcd-snapshot sqlite feature request; SUSE k3s kine maintainers layoffs; k3s lifecycle. No SUSE or Rancher layoff news affecting k3s was found.

## 4. Verdict: upheld

The narrow claim is in pinned source code, and the vendor's own position (C-REF-W5-longevity-001) makes it durable: kine won't produce etcd snapshots, so `etcd-snapshot` on SQLite won't start working by accident. The counter-argument that this is only a fact about one patch release fails.

**Longevity condition (for the decision, not the claim).** Any OneMind text that says "migrate to etcd with `--cluster-init`, then use `etcd-snapshot`" depends on a path that broke in a shipped k3s patch (v1.32.5) and could leave an empty cluster. So:
1. Take a verified SQLite backup **immediately before** any `--cluster-init` conversion, and confirm the object count after it.
2. Run the conversion in OneMind's own CI for every k3s version OneMind ships. Don't rely on upstream's test, which only dates from 2025.

## 5. What would flip it

- **To refuted:** a k3s release where `k3s etcd-snapshot save` succeeds on a SQLite server, for example a kine snapshot or dump handler wired to the `/db/` routes, or `handlerNoEtcd` being removed.
- **To moot:** k3s changing the single-server default from SQLite to another driver (etcd, T4 or Memory), or announcing a SQLite deprecation. The claim would still be true, but it would no longer describe the default that OneMind boxes get.
- **To weakened:** a second shipped regression of `--cluster-init` migration after the 2025 e2e test, which would mean the escape hatch still isn't reliably guarded upstream.
