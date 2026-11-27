---
pr: pending
branch: claude/ci-speed
---
Faster CI with no test dropped. The gateway test shards now really run on every runner core: ci-core always asked for pytest-xdist, but `make -C core test` ignored the flags, so each shard ran on one core and a PostgreSQL shard took 57 of its 60 minutes in the merge queue. The shard timeout drops to 30 minutes so a hang fails fast. In the battery workflow the non-blocking Secure Boot test (SB1-SB7) now runs after the required firewall and battery steps with a 20-minute limit; it is stopped with SIGINT first so it still writes the verdicts it has and leaves no VM running, and the rootfs tar it needs is moved aside before the battery clean-up. A unit test pins the wiring and the step order.
