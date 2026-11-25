# SPDX-License-Identifier: Apache-2.0
"""The agent browser (#694): a fresh browser pod per agent session, reachable sites only by owner approval.

policy.py (URL rules, step plans), pods.py (the pod and its NetworkPolicy), proxy.py (the only way out),
service.py (allowlist, sessions, visits, audit), settings.py. Routes: routers/agentbrowser.py.
"""
