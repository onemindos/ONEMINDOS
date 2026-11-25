# SPDX-License-Identifier: Apache-2.0
"""Secure Boot helpers for the OneMind image (S-13, first slice): signed unified kernel images (UKI).

A UKI is one EFI program that holds the kernel, the initrd and the kernel command line. Signing that one file
means the firmware checks the command line too, so nobody at the boot menu can add `init=/bin/sh`. The
firmware (UEFI Secure Boot) only runs files signed by a key in its `db` list.

This module only builds and signs. It never creates real keys: the real signing key is made at the founder's
signing ceremony (os/secureboot/README.md). `make_test_keys` makes throwaway keys for the QEMU test.
Tools (in the tools container): systemd-ukify, systemd-boot-efi (the stub), sbsigntool, openssl,
python3-virt-firmware.
"""
import os, subprocess

STUB = "/usr/lib/systemd/boot/efi/linuxx64.efi.stub"
# Same words as CMDLINE in grub.cfg.in (test/unit/test_uki.py keeps them equal). In a UKI the command line is
# signed, so it also names the slot and the root partition instead of leaving them to GRUB.
CMDLINE_TAIL = "panic=10 rootwait ro loglevel=4 splash plymouth.ignore-serial-consoles"
UKI_DIR = "EFI/Linux"


def uki_name(slot):
    return f"onemind-{slot}.efi"


def cmdline(console, partuuid, slot):
    if slot not in ("A", "B"):
        raise ValueError(f"slot must be A or B: {slot!r}")
    return f"{console} {CMDLINE_TAIL} root=PARTUUID={partuuid} rauc.slot={slot}"


def need_files(*paths):
    for p in paths:
        if not p or not os.path.isfile(p):
            raise SystemExit(f"ERROR: Secure Boot signing needs the file {p!r}")


def run(cmd):
    print("[uki] $ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True)


def ukify_cmd(kernel, initrd, cmd, osrel, out, key, cert, stub=STUB):
    """The ukify command that builds and signs one UKI (sbsign does the signing)."""
    return ["ukify", "build", f"--linux={kernel}", f"--initrd={initrd}", f"--cmdline={cmd}",
            f"--os-release=@{osrel}", f"--stub={stub}", "--signtool=sbsign",
            f"--secureboot-private-key={key}", f"--secureboot-certificate={cert}", f"--output={out}"]


def build_uki(kernel, initrd, cmd, osrel, out, key, cert, stub=STUB):
    need_files(kernel, initrd, osrel, key, cert, stub)
    run(ukify_cmd(kernel, initrd, cmd, osrel, out, key, cert, stub))
    return out


def sbsign_cmd(src, dst, key, cert):
    return ["sbsign", "--key", key, "--cert", cert, "--output", dst, src]


def sign_efi(src, dst, key, cert):
    """Sign a plain EFI program (the GRUB binary) with the db key."""
    need_files(src, key, cert)
    run(sbsign_cmd(src, dst, key, cert))
    return dst


def make_test_keys(d):
    """Throwaway PK, KEK and db (RSA 2048, one day). TEST ONLY: the QEMU test makes them inside its own work
    directory and they die with it."""
    os.makedirs(d, exist_ok=True)
    for n in ("PK", "KEK", "db"):
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-sha256",
             "-keyout", os.path.join(d, f"{n}.key"), "-out", os.path.join(d, f"{n}.crt"),
             "-subj", f"/O=OneMind TEST (throwaway)/CN=test-{n}"])
    return {n: (os.path.join(d, f"{n}.key"), os.path.join(d, f"{n}.crt")) for n in ("PK", "KEK", "db")}


def enroll_cmd(vars_in, vars_out, keys_dir, owner="6e0a8b0e-0000-4a00-8000-0000000000ee"):
    """virt-fw-vars command that writes a copy of the firmware variable store with our PK, KEK and db enrolled
    and Secure Boot on (no Microsoft keys: this box trusts only the owner)."""
    c = lambda n: os.path.join(keys_dir, f"{n}.crt")
    return ["virt-fw-vars", "--input", vars_in, "--output", vars_out, "--set-pk", owner, c("PK"),
            "--add-kek", owner, c("KEK"), "--add-db", owner, c("db"), "--secure-boot"]


def enroll(vars_in, vars_out, keys_dir):
    run(enroll_cmd(vars_in, vars_out, keys_dir))
    return vars_out
