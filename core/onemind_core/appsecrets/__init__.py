# SPDX-License-Identifier: Apache-2.0
"""App secrets: declared in the manifest, entered by the owner through an approval, stored
encrypted with the box's key, written into app-<id> as Kubernetes Secrets, never shown back.

Design and API: docs/leap/core/SECRETS.md. Modules: spec (manifest declaration), crypto (store
key, sealed input), store (tables), service (the logic; wired by routers/secrets.py).
"""
