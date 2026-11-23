# SPDX-License-Identifier: Apache-2.0
"""The agent browser (#694): a fresh browser pod per agent session, reachable sites only by owner approval.

policy.py (URL rules, step plans), pods.py (the pod and its NetworkPolicy), proxy.py (the only way out).
The service (allowlist, sessions, visits, audit), its settings and the routes under /v1/agent-browser
land in the next pull request on #694; until then nothing here is mounted or started.
"""
