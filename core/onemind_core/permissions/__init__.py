# SPDX-License-Identifier: Apache-2.0
"""The gateway's permission engine (gateway permissions design §3.4, §3.5.2; D-027, D-028).

- `floor.py`: the hard floor, the checks no mode or rule can turn into an automatic yes.
- `decide.py`: `decide()`, the one ordered decision every filing path asks (deny first).
- `denies.py`: deny rules, a per-principal "never" checked before anything that could say yes.
- `clock.py`: no automatic approval while the clock cannot be trusted.
- `engine.py`: gathers the facts for one request and applies the decision on the filing paths.

The rule it all serves (D-027, F-1 = b): AI never acts without a person's approval, given at the
time, or in advance through a narrow, expiring, revocable, recorded rule.
"""
