<!-- SPDX-License-Identifier: Apache-2.0 -->
# Mac developer loop (CI-05)

This is the local-loop guide for [issue #230](https://github.com/onemindos/ONEMINDOS/issues/230),
feeding brief 30's BM0 developer tooling and BM1 image builds. It changes no
[locked decision](../DECISIONS.md): Debian 13 remains the shipping base (D-007).

## Native tests: no Docker or VM needed

Prerequisites: Git, Go at least the version in [`go.mod`](../../go.mod), Python 3.12
and `uv`. `uv` can supply Python 3.12 if it is not already available. For lint and
secret scanning, also provide `shellcheck` and `gitleaks`. Do not install packages
into the system Python. From the root of your isolated issue worktree:

```sh
uv venv --python 3.12 work/dev-venv
uv pip install --python work/dev-venv/bin/python -r requirements-dev.txt
source work/dev-venv/bin/activate
make test
make lint
python3 scripts/changes.py check
python3 scripts/hygiene.py
gitleaks detect --no-banner
go test ./...
```

A **virtual environment** keeps Python packages in one project directory, not in
macOS's Python. `work/` is already ignored by Git. Activation makes `make test`'s
`python3 -I` use this environment; `-I` ignores user packages and `PYTHONPATH`, not
the environment's installed packages. [`requirements-dev.txt`](../../requirements-dev.txt)
pins PyYAML, required by the OS unit tests and assembler. Gateway and TUF suites
have separate dependencies; this file does not claim to install those.

If Go reports `error obtaining VCS status` in a linked worktree, inspect with
`go list -x ./cmd/onemind`. Some Go versions discover a parent `.git` directory
instead of the worktree's `.git` file. In that case, explicitly select this
worktree for the current shell, then rerun the unchanged tests:

```sh
export GIT_DIR="$(git rev-parse --absolute-git-dir)"
export GIT_WORK_TREE="$PWD"
go test ./...
```

This preserves version stamping; it does not disable tests or change Git config.
Use a separate shell for other checkouts.

The safeFS fixture resolves **only its trusted temporary root** with
`filepath.EvalSymlinks`: macOS can place temp directories behind `/var`'s symlink.
Production restore paths still reject symlink components. The tests cover real
directory creation and rejection of a deliberately planted link.

## Image builds: Docker Desktop or Docker inside Lima

The Mac container choices are **Docker Desktop** or **Docker Engine inside a
Linux Lima VM**, consistent with the agent engineering guide. Both supply a
Linux Docker engine for the existing Containerfile; native unit tests above
need neither. This task exercised neither container/VM path, so these are setup
instructions, not a claim of a passing image build on either backend.

For Docker Desktop, start its Linux engine and check `docker info` and
`docker buildx version` from the worktree before running the rootfs target below.
Image assembly and release scripts also need Linux tools: run those in a Linux
build environment, not directly in macOS merely because Docker Desktop is
running. The Lima option below puts the Docker engine and build tools in the
same Linux guest.

With owner authorization to create a VM, provision a Lima `template:docker`
instance with the worktree mounted writable, `make` and `python3-yaml` available
in the guest. Enter it with `limactl shell <name>`, change to the mounted worktree,
and run the Makefile there. Check `docker info` and `docker buildx version` first.
For an Apple Silicon host, start with native arm64:

```sh
make rootfs BOARD=arm64-efi
make image BOARD=arm64-efi
```

An amd64 target on an arm64 guest additionally needs guest-side binfmt/QEMU
emulation (`qemu-user-binfmt`); do not infer x86 hardware performance from it.
The build tools and image pins come from
[`os/rootfs/Containerfile`](../../os/rootfs/Containerfile) and
[`os/versions.lock.yaml`](../../os/versions.lock.yaml).
See [image coverage](../leap/core/IMAGES.md) and
[update-specific commands](../../os/update/README.md#running-it-locally).
This local-loop fix does **not** claim a new VM/image/battery run, hardware boot,
or OVA import validation. `convert.sh`'s OVA import remains UNVERIFIED on
VirtualBox/VMware; the VMDK/VDI outputs remain the documented fallback.

## Guard against committing into the wrong checkout

Many agents share one repository through linked worktrees, and they all read the **same** config file,
`<repo>/.git/config`. If anything sets `core.worktree` there, it points **every** worktree at one other
folder: `git status` shows that folder's files and `git add` / `git commit` act on them, with no error.
This has happened twice. [`scripts/git-guard.sh`](../../scripts/git-guard.sh) catches it: it exits 1 and prints
the fix when the shared config sets `core.worktree`, or when git's top level is not the folder you are in.

Run it before you commit, or install it once per clone as a hook (one line; hooks live in the shared
`.git/hooks`, so it covers every worktree):

```sh
H="$(git rev-parse --path-format=absolute --git-common-dir)"; printf '#!/bin/sh\nexec sh "%s/../scripts/git-guard.sh"\n' "$H" > "$H/hooks/pre-commit" && chmod +x "$H/hooks/pre-commit"
```

The hook is `.git/hooks/pre-commit`, so it is yours alone and never committed. If it fires, do not commit:
remove the key with the command it prints, then check `git rev-parse --show-toplevel` again. Never set that
key with plain `git config`; use `git config --worktree` for anything that belongs to one worktree.

## Evidence and limits

The reported pre-fix Mac failures were reproduced: safeFS refused the temp
root's symlink ancestor; `make test` could not import `yaml`. With canonical test
roots and the isolated dependencies, both suites run on Apple Silicon. The
reachability test's nested `go list` also passed using the explicit worktree
selection above. Sources are the executable
[`Makefile`](../../Makefile),
[`safeFS tests`](../../internal/backup/safefs_test.go), and
[`reachability test`](../../cmd/wiring_test.go).
Existing unit tests can emit unclosed-file `ResourceWarning`s; those are not
silenced or presented as newly fixed here.

This is developer tooling reachable through `make` and `go test`, not a new
screen, route or gateway feature. No user-reachable fake data is added, and no
actuation or approval policy changes.
