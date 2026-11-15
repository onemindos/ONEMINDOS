---
pr: pending
branch: feat/281-kvm-scopes
---
Machines (MACH-01, #281 part 2): a real x86 hub can now pass the preflight, because the node's heartbeat reports `kvm` (true when `/dev/kvm` exists, so the CPU's virtualisation is on), and the two machines routes have their own scope rows: any account that may read nodes can read the capabilities, and only the owner role can switch machines on (an unmintable `machines:admin` scope), so a narrow token no longer falls to the full-scope fallback.
