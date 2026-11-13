# SPDX-License-Identifier: Apache-2.0
"""Migration kit (CORE-DEPLOY-6): move a namespace of an existing Kubernetes cluster onto this box.

kube.py      kubeconfig parsing and the verb-fenced client for the old cluster
inventory.py read one namespace (GET only)
mapper.py    the dry-run report and the private app's objects (pure)
bundle.py    the bundle on disk (manifests/, staging/) and its hash
copyjobs.py  the helper pod (old cluster) and restore Job (this box) that move one volume
repo.py      the append-only restic REST repository the helper writes to
boxkube.py   kubectl calls on this box
store.py     tables: migrate_plans, migrate_copies, migrate_repo_users
service.py   the plan and the four approved steps (import, copy, cutover, revert)

How it fits together: docs/leap/core/MIGRATE.md.
"""
