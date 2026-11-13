<!-- SPDX-License-Identifier: Apache-2.0 -->
# test/qemu: boot tests

The QEMU harnesses boot the real image and check it against pre-registered criteria
(`CRITERIA*.md`, hashes in `PREREGISTRATION.sha256`; never edited to make a result pass).

| Harness | Criteria | Make target |
|---|---|---|
| `run-tests.py` | CRITERIA.md (T1-T11) | `make battery` |
| `firstboot.py` | CRITERIA-FIRSTBOOT.md (F0-F4) | `make firstboot` |
| `cloudboot.py` | CRITERIA-CLOUD.md (C0-C6) | `make cloud-test` |
| `installer.py` | CRITERIA-INSTALLER.md (I1-I5) | `make installer-test` |

## Fail fast

`failfast.py` watches the serial console while a harness waits (kernel panic, emergency mode, a OneMind unit
that failed to start or restarts in a loop, a OneMind Python traceback). The first-boot, cloud and installer
harnesses abort at once with a `HARNESS FAIL ... fatal sign ...` line instead of waiting out the 15 to 30 minute
timeouts, and when `/healthz` never answers they print the gateway journal (`journalctl -u onemind-gateway`)
into the log. The T-battery does not use it: T6 and T7 panic and fail units on purpose. Unit tests:
`test/unit/test_qemu_failfast.py`.

## Local first boot

Run F0-F4 on your own PC before pushing (the same steps as the `smoke` job in `image.yml`). Needs Docker and
`/dev/kvm`; on Windows use WSL2 Debian (enable nested virtualization; `ls -l /dev/kvm` must exist).

```sh
# inside WSL (or any Linux), in a clone on the Linux filesystem, not under /mnt/c (CRLF breaks the scripts)
sudo apt install -y docker.io make python3
sudo service docker start
git clone https://github.com/onemindos/ONEMINDOS.git ~/onemindos && cd ~/onemindos
git checkout <your branch>
make local-firstboot          # or: test/qemu/local-firstboot.sh BOARD=x86_64-efi FUPTO=F4
```

It builds the rootfs and tools image (a first build takes a while; later builds use the Docker cache), makes the
fixtures and runs `make firstboot` under KVM. Result: a PASS/FAIL line per F-test, `out/firstboot-x86_64-efi/results.json`
and the console log `out/firstboot-x86_64-efi/serial.log`. On a failure the log ends with the gateway journal.
