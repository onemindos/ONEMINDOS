---
pr: pending
branch: claude/sec-app-roles-write-scope
---
Security: an app Role can no longer grant write verbs (create, update, patch, delete, deletecollection) on Services, Endpoints, Pods, workloads (Deployments, StatefulSets, ReplicaSets, DaemonSets, Jobs, CronJobs), Secrets or ServiceAccounts. The gateway holds those rights in the app namespace, so Kubernetes alone would have allowed such a Role, and an app pod with its default API token could then publish a NodePort or externalIPs Service past gateway sign-in or start unscanned images. Rule R-03 now refuses them (read-only in v0), with negative cases in the policy tests. Still to do: automountServiceAccountToken false on app pods, the k3s DenyServiceExternalIPs plugin, and a cluster-side admission policy.
