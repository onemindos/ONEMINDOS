# SPDX-License-Identifier: Apache-2.0
"""Encrypt /data with LUKS2 on first boot and unlock it on every boot (IMG-LUKS-01; SB-5, finding F-04, H-11).

Why the box does this itself: an image built in CI is copied to every machine. A disk key made at build time
would be the same on every box, so the image ships the data partition BLANK and the box makes its own key.

What it does, by what it finds on the onemind-data partition:
  - blank (the first 1 MiB is all zero and blkid sees no signature): make a LUKS2 volume with a random key that only
    ever exists in RAM, put ext4 on it, add a recovery key and (when the machine has a TPM) a TPM2 key bound to
    PCR 7, then drop the random key. The recovery key is printed once on the console and left in
    /run/onemind/data-recovery-key (RAM only) for the recovery-kit step to show and then delete.
  - LUKS2: unlock it. First with the TPM (no prompt), else by asking for the recovery key on the console.
  - ext4 (every box installed before this change): do NOTHING. Existing data is never touched or converted here;
    migrating a live box needs its own design (backup, re-create, restore).
  - anything else: do nothing and say so (the data check then puts the box in recovery mode).

What it will never do: format a partition that holds anything, or write the recovery key to disk or the journal.
Exit status is always 0: a locked disk is reported by the data check (recovery mode), not by a failed unit.

PCR 7 alone is a weak binding on a box without Secure Boot (anyone who boots another OS on the same
firmware measures the same PCR 7). The recovery key is the strong fallback; adding the signed PCR 11 policy
waits for UKIs (docs/leap/core/SECURITY.md).
"""
import json, os, re, subprocess, sys, time

LABEL = "onemind-data"
NAME = "onemind-data"                      # /dev/mapper/onemind-data
RUN = "/run/onemind"
STATE = RUN + "/data-crypt.json"           # no secrets: what happened, for the dashboard and the data check
KEYFILE = "/run/onemind-data-crypt.key"    # random volume key, RAM only, removed before this exits
RECOVERY_FILE = RUN + "/data-recovery-key"
CRYPTSETUP = "/usr/lib/systemd/systemd-cryptsetup"
MODHEX = "cbdefghijklnrtuv"
RECOVERY_RX = re.compile(r"\b([%s]{8}(?:-[%s]{8}){7})\b" % (MODHEX, MODHEX))
ZERO_BYTES = 1 << 20
SCRUB_BYTES = 16 << 20                     # a LUKS2 header plus keyslots is up to 16 MiB; wipefs alone leaves it


def say(msg, journal=True):
    """To the console and (unless `journal` is False) the journal. The recovery key goes to the console only."""
    line = f"ONEMIND-DATA-CRYPT: {msg}"
    if journal:
        print(line, flush=True)
    try:
        with open("/dev/console", "w") as c:
            c.write(line + "\n")
    except OSError:
        pass


def run(cmd, input=None, check=True):
    """Run a command; the secret never goes on a command line, only on stdin or in a 0600 file."""
    return subprocess.run(cmd, input=input, check=check, capture_output=True, text=True)


def signature(node, runner=run):
    r = runner(["blkid", "-p", "-o", "value", "-s", "TYPE", node], check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def head_is_zero(node):
    with open(node, "rb") as f:
        return not any(f.read(ZERO_BYTES))


def zero_head(node, nbytes=SCRUB_BYTES):
    """Overwrite the first `nbytes` with zeros (stops at the end of a smaller device). wipefs only erases the
    magic numbers; the LUKS2 JSON header and keyslots would stay and the head would never read as blank again."""
    try:
        fd = os.open(node, os.O_WRONLY)
        try:
            chunk, left = bytes(1 << 20), nbytes
            while left > 0:
                n = os.write(fd, chunk[:left])
                if n <= 0:
                    break
                left -= n
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as e:
        say(f"could not zero the head of {node} ({e}); the next boot may treat it as unknown data")


def classify(sig, zero):
    """'blank' only when there is no signature AND the head is zero; unknown data is never formatted."""
    if sig == "crypto_LUKS":
        return "luks"
    if sig == "ext4":
        return "ext4"
    if sig == "" and zero:
        return "blank"
    return "unknown"


def parse_recovery_key(text):
    m = RECOVERY_RX.search(text)
    return m.group(1) if m else None


def write_state(**kw):
    os.makedirs(RUN, mode=0o755, exist_ok=True)
    tmp = STATE + ".new"
    with open(tmp, "w") as f:
        json.dump(dict(kw, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATE)


def keep_recovery_key(key):
    """RAM only (/run is a tmpfs), root only. The recovery-kit step reads and deletes it."""
    os.makedirs(RUN, mode=0o755, exist_ok=True)
    os.chmod(RUN, 0o755)
    fd = os.open(RECOVERY_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")


def first_boot_encrypt(node, has_tpm, runner=run, rand=os.urandom):
    """Blank partition -> LUKS2 + ext4 + recovery key (+ TPM2). Returns {'recovery_key', 'tpm2'}.
    On any failure the partition is wiped (signatures, then the first 16 MiB zeroed) back to blank (it held nothing) so the next boot retries."""
    dev = "/dev/mapper/" + NAME
    fd = os.open(KEYFILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(rand(64))
    opened = False
    try:
        # The key is 512 random bits, so a slow password hash would only slow every boot: one iteration batch.
        runner(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--cipher", "aes-xts-plain64",
                "--key-size", "512", "--pbkdf", "pbkdf2", "--pbkdf-force-iterations", "1000",
                "--key-file", KEYFILE, node])
        runner(["cryptsetup", "open", "--key-file", KEYFILE, "--perf-no_read_workqueue",
                "--perf-no_write_workqueue", "--persistent", node, NAME])
        opened = True
        runner(["mkfs.ext4", "-q", "-L", LABEL, "-E", "root_owner=0:0,lazy_itable_init=1", dev])
        out = runner(["systemd-cryptenroll", "--unlock-key-file=" + KEYFILE, "--recovery-key", node]).stdout
        key = parse_recovery_key(out)
        if not key:
            raise RuntimeError("systemd-cryptenroll printed no recovery key")
        tpm2 = False
        if has_tpm:
            r = runner(["systemd-cryptenroll", "--unlock-key-file=" + KEYFILE, "--tpm2-device=auto",
                        "--tpm2-pcrs=7", node], check=False)
            tpm2 = r.returncode == 0
            if not tpm2:
                say("the TPM would not take the key; this box unlocks with the recovery key only")
        # Hygiene: the random key is about to be deleted, so its slot is dead weight. Best effort.
        runner(["cryptsetup", "luksKillSlot", "--batch-mode", "--key-file", KEYFILE, node, "0"], check=False)
        return {"recovery_key": key, "tpm2": tpm2}
    except BaseException:
        if opened:
            runner(["cryptsetup", "close", NAME], check=False)
        runner(["wipefs", "--all", "--force", node], check=False)
        zero_head(node)
        raise
    finally:
        try:
            os.remove(KEYFILE)
        except OSError:
            pass


def unlock(node, has_tpm, runner=run):
    """Returns 'tpm2', 'recovery-key' or None. systemd-cryptsetup does the asking (console and plymouth) and
    accepts the recovery key in any of the forms people type it."""
    if has_tpm:
        r = runner([CRYPTSETUP, "attach", NAME, node, "none", "luks,tpm2-device=auto,headless=true"], check=False)
        if r.returncode == 0:
            return "tpm2"
        say("the TPM did not unlock the data disk (moved disk, firmware change or no key); asking for the recovery key")
    else:
        say("no TPM here: enter the recovery key to unlock the data disk")
    r = runner([CRYPTSETUP, "attach", NAME, node, "none", "luks,tries=3"], check=False)
    return "recovery-key" if r.returncode == 0 else None


def wait_for(path, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    return os.path.exists(path)


def main(runner=run):
    if not wait_for(f"/dev/disk/by-partlabel/{LABEL}"):
        say(f"no partition labelled {LABEL}; nothing to do")
        return 0
    node = os.path.realpath(f"/dev/disk/by-partlabel/{LABEL}")
    if os.path.exists("/dev/mapper/" + NAME):
        return 0                                     # already open (this is not the first run of the boot)
    has_tpm = os.path.exists("/dev/tpmrm0")
    kind = classify(signature(node, runner), head_is_zero(node))
    if kind == "ext4":
        write_state(state="plain", reason="installed before encryption; left as it is")
        say("the data partition is plain ext4 (an earlier install); left untouched")
    elif kind == "blank":
        say("blank data partition: making it LUKS2" + (" with TPM2 unlock" if has_tpm else " (no TPM: recovery key only)"))
        res = first_boot_encrypt(node, has_tpm, runner)
        keep_recovery_key(res["recovery_key"])
        write_state(state="encrypted", unlock="tpm2" if res["tpm2"] else "recovery-key", tpm2=res["tpm2"])
        say("RECOVERY KEY (write it down now, it is shown once): " + res["recovery_key"], journal=False)
        runner(["udevadm", "settle", "--timeout=20"], check=False)
    elif kind == "luks":
        how = unlock(node, has_tpm, runner)
        if how:
            write_state(state="encrypted", unlock=how, tpm2=has_tpm)
            say(f"data disk unlocked ({how})")
            runner(["udevadm", "settle", "--timeout=20"], check=False)
        else:
            write_state(state="locked", reason="could not unlock")
            say("the data disk is locked: starting recovery mode")
    else:
        write_state(state="unknown", reason="the partition holds something that is neither blank, ext4 nor LUKS2")
        say("the data partition holds something unexpected; not touching it")
    return 0


def safe_main():
    try:
        return main()
    except subprocess.CalledProcessError as exc:
        say(f"failed: {' '.join(map(str, exc.cmd))}: {(exc.stderr or '').strip()[-300:]}")
    except Exception as exc:  # noqa: BLE001 (nothing may fail the boot: the data check decides)
        say(f"failed ({type(exc).__name__}): {str(exc)[:300]}")
    return 0


if __name__ == "__main__":
    sys.exit(safe_main())
