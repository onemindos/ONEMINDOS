---
pr: pending
branch: rel/302-root-renewal
---
REL-03 (#302): the TUF root can now be renewed before it expires. `scripts/tuf-bootstrap-root.sh renew` writes root version N+1 with the same keys and a new expiry, signed by the threshold of the current root holders, and checks that a box holding version N accepts it; `rehearse-renewal` practises it on throwaway keys, including a one-holder refusal and a client following the chain. The nightly has a `root-expiry` job that fails 60 days before a committed root expires. CEREMONY.md has "Renewing the root" and the checklist a part B.
