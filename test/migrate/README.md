<!-- SPDX-License-Identifier: Apache-2.0 -->
# Migration kit end-to-end test

Runs the whole `onemind migrate` flow against a real k3s and real restic, inside a throwaway
Lima VM (Debian 13). Nothing is installed on the machine that runs it, and no real cluster is
ever contacted.

```console
$ test/migrate/lima-e2e.sh                     # create the VM, run, delete the VM
$ KEEP_VM=1 test/migrate/lima-e2e.sh           # keep the VM to look around (limactl shell omos-migrate-e2e)
```

Needs `limactl` and Go on the machine. The VM downloads k3s (pinned and checked against
`os/versions.lock.yaml`), uv (pinned with its release checksum), Python 3.12 (through uv) and the
container images it runs.

What it does (`in-vm.sh`):

1. Starts k3s and adds the `onemind-local` StorageClass the OS platform layer ships.
2. Starts the gateway with the kubernetes executor.
3. Seeds namespace `legacy-demo` (`fixtures/legacy-demo.yaml`): a notes app with a volume, a
   StatefulSet that writes every 200 ms, a stateless web app, an Ingress, a Secret and a CronJob.
4. Applies `onemind migrate role --copy --cutover` and builds the namespaced kubeconfig with the
   recipe that command prints, then checks that this identity cannot read Secrets or other
   namespaces.
5. plan → import → copy → cutover → revert through the CLI, approving each action over the API,
   and checks: the report, 0 replicas after import, the copy verified, the files identical
   old vs new (hashes, modes, owners), the old writers stopped at switch-over, the database log
   carried over exactly, the old replicas restored by revert, no token in the audit log, no
   restore Secret left behind, and an intact audit chain.

One k3s plays both sides (separate namespaces, separate identities). The scan record the import
gate needs is written by the harness as a labelled stand-in, because the on-box scan of private
bundles (CORE-DEPLOY-2) does not exist yet.
