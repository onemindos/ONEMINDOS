# SPDX-License-Identifier: Apache-2.0
"""Make /data on first boot (btrfs, encrypted when the box has a TPM) and unlock it on every boot
(IMG-LUKS-01, IMG-05 #152; SB-5, finding F-04, H-11).

Why the box does this itself: an image built in CI is copied to every machine. A disk key made at build time
would be the same on every box, so the image ships the data partition BLANK and the box makes its own key.

The founder's rule (2026-11-22, #152): a home hub has to come back by itself after a power cut or an update restart.
  - TPM present: encrypt by default; the TPM unlocks it after every restart, the recovery key goes into the kit.
  - no TPM (a Raspberry Pi 5, say): leave it UNENCRYPTED, unless the owner opts in with the kernel command line word
    `onemind.data_encrypt=passphrase` and accepts typing a passphrase at every restart.

What it does, by what it finds on the onemind-data partition:
  - blank (the first 1 MiB is all zero and blkid sees no signature): by the rule above, either
      LUKS2 with a random key that only ever exists in RAM, btrfs inside it, a recovery key, then a TPM2 key bound
      to PCR 7 (TPM) or the owner's passphrase (opt-in), and the random key's slot is wiped; the recovery key is
      shown once on the screen (never on a serial console unless the owner asks, see key_terminals) and left in
      /run/onemind/data-recovery-key (RAM only) for the recovery-kit step;
      the LUKS2 header also gets the OneMind token (id 30), which the factory reset needs to find the disk;
    or plain btrfs on the partition (no TPM, no opt-in).
    Fail closed: when the firmware announces a TPM 2.0 (the ACPI TPM2 table, or the TPM event log with a kernel-reported
    major version of 2, as systemd's efi_has_tpm2() checks) but /dev/tpmrm0 is not there (its driver probed late or
    failed), the box is a TPM box, so it gets LUKS2 with the recovery key, never plain: plain btrfs is left alone on
    every later boot, so a wrong 'plain' would be unencrypted for good. A TPM 1.2 does not count (it can never unlock
    the disk by itself), so that box follows the no-TPM rule. The unit
    also waits for tpm2.target (systemd-tpm2-generator), so a slow TPM driver normally gets there first.
    The btrfs gets two subvolumes: @ (the default, which /etc/fstab mounts at /data) and @storage (the owner's files,
    mounted at /data/storage), with @storage/.snapshots inside it for snapper (see SUBVOLS).
  - LUKS2: unlock it. First with the TPM (no prompt), else by asking on the console (passphrase or recovery key).
  - ext4 (every box installed before this change) or btrfs (a box without a TPM): do NOTHING. Existing data is
    never touched or converted here; migrating a live box needs its own design (backup, re-create, restore).
  - anything else: do nothing and say so (the data check then puts the box in recovery mode).

A factory reset armed on the ESP (reset_armed) makes it do nothing at all this boot: the wipe unit runs next, erases the
partition and restarts the box, and THAT boot finds a blank partition and formats it as above.

What it will never do: format a partition that holds anything, or write the recovery key or the passphrase to disk,
the journal, a serial console (unless the owner opted in, #1118) or a command line (secrets go on stdin or in a 0600
file in RAM).
Exit status is always 0: a locked disk is reported by the data check (recovery mode), not by a failed unit.

PCR 7 alone is a weak binding on a box without Secure Boot (anyone who boots another OS on the same
firmware measures the same PCR 7). The recovery key is the strong fallback; adding the signed PCR 11 policy
waits for UKIs (docs/leap/core/SECURITY.md).
"""
import contextlib, json, os, re, signal, subprocess, sys, time, uuid

LABEL = "onemind-data"
NAME = "onemind-data"                      # /dev/mapper/onemind-data
RUN = "/run/onemind"
STATE = RUN + "/data-crypt.json"           # no secrets: what happened, for the dashboard and the data check
KEYFILE = "/run/onemind-data-crypt.key"    # random volume key, RAM only, removed before this exits
RECOVERY_FILE = RUN + "/data-recovery-key"
MKFS_MNT = "/run/onemind-data-mkfs"        # where the new btrfs is mounted (top level) to make its subvolumes
# Two subvolumes (D-020 follow-up, plan PR 5):
#   @        the default one, which /etc/fstab mounts at /data: k3s, the databases, the gateway state. Never snapshotted
#            (a database snapshot taken mid-write is not a backup; restic and the app dumps are the backups).
#   @storage the owner's files, mounted at /data/storage by data-storage.mount. snapper keeps its snapshots of it in the
#            nested subvolume @storage/.snapshots, so a snapshot of @storage never contains its own snapshots, and
#            snapshots cannot be taken of @ by accident.
SUBVOLS = ("@", "@storage")                # @ first: it becomes the default subvolume, which /data mounts
SNAPSHOTS_SUBVOL = "@storage/.snapshots"   # where snapper expects them (SUBVOLUME/.snapshots)
STORAGE_DIR = "@/storage"                  # the (empty) mount point of @storage, inside @
# The OneMind LUKS2 token (internal/storage/luks.go: TokenID, TokenType, Token). The factory reset
# (internal/host/reset.go, ops.Candidates) lists a LUKS2 data partition only when it carries this token and the token's
# partuuid is the partition's own; a box that has none refuses to reset. Plain btrfs needs no token: the reset
# recognises it by the system disk, the GPT name and the btrfs label.
TOKEN_ID = 30
TOKEN_TYPE = "onemind-storage"
OPT_IN = "onemind.data_encrypt=passphrase"
MIN_PASSPHRASE = 8
CRYPTSETUP = "/usr/lib/systemd/systemd-cryptsetup"
MODHEX = "cbdefghijklnrtuv"
RECOVERY_RX = re.compile(r"\b([%s]{8}(?:-[%s]{8}){7})\b" % (MODHEX, MODHEX))
TPM_DEV = "/dev/tpmrm0"
# How the firmware announces a TPM 2.0, the same checks as systemd's efi_has_tpm2() (src/shared/efi-api.c), which
# systemd-tpm2-generator uses to decide that a TPM2 should appear:
#   1. the ACPI TPM2 table (x86, ARM servers): only a TPM 2.0 has one (a TPM 1.2 has the TCPA table instead);
#   2. else the firmware's TPM event log, but ONLY when the kernel reports TPM major version 2. The kernel makes that
#      event log for a TPM 1.2 too, and a TPM 1.2 never gets /dev/tpmrm0, so without the version check an older office
#      PC with a TPM 1.2 would be taken for a TPM2 box whose TPM is late, and get a recovery key typed at every restart.
ACPI_TPM2 = "/sys/firmware/acpi/tables/TPM2"
EVENT_LOG = "/sys/kernel/security/tpm0/binary_bios_measurements"
TPM_VERSION_MAJOR = "/sys/class/tpm/tpm0/tpm_version_major"
ZERO_BYTES = 1 << 20
SCRUB_BYTES = 16 << 20                     # a LUKS2 header plus keyslots is up to 16 MiB; wipefs alone leaves it


ACTIVE_CONSOLES = "/sys/class/tty/console/active"
ESP_NODE = "/dev/disk/by-partlabel/onemind-esp"   # the ESP, which /etc/fstab mounts at /boot/efi (later than this runs)
RESET_MARKER = "onemind/factory-reset"            # armed factory reset (internal/host/reset.go MarkerName)
ESP_PROBE = RUN + "/esp-probe"


def console_devices():
    """The terminals the kernel console runs on ("tty0 ttyS0": the screen and the serial port).
    Why not /dev/console alone: with the boot splash (plymouth, grub.cfg.in `splash`) running, plymouth redirects
    /dev/console into its own log, so a line written there during early boot (this unit runs in sysinit.target) reaches
    neither the serial console nor a text screen, and the recovery key would be shown nowhere. The terminals
    themselves are not redirected."""
    names = []
    try:
        with open(ACTIVE_CONSOLES) as f:
            names = f.read().split()
    except OSError:
        pass
    return ["/dev/" + n for n in names]


def to_consoles(line, devices=None, fallback=True):
    """Write one line to every console terminal that takes it, or to /dev/console when none does (unless `fallback`
    is False: the recovery key never goes to /dev/console, which plymouth logs and which is often a serial port).
    Returns how many did.
    Never raises, never blocks the boot (O_NONBLOCK: a serial port with nothing listening must not hang the first boot;
    O_NOCTTY: this service must not take a terminal for its own)."""
    n = 0
    for dev in (console_devices() if devices is None else devices) + [None]:
        if dev is None:
            if n or not fallback:
                break
            dev = "/dev/console"
        try:
            fd = os.open(dev, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError:
            continue
        try:
            os.write(fd, (line + "\r\n").encode("utf-8", "replace"))
            n += 1
        except OSError:
            pass
        finally:
            os.close(fd)
    return n


AGENT = "/usr/bin/systemd-tty-ask-password-agent"
SERIAL_RX = re.compile(r"^(ttyS|ttyAMA|ttyUSB|ttyGS)\d+$")
SCREEN_RX = re.compile(r"^tty\d+$")              # the screen's virtual terminals (tty0 = the one in front)
KEY_SERIAL_OPT_IN = "onemind.recovery_key=serial"


def key_terminals(names=None, text=None):
    """Where the recovery key may be shown (#1118): the screen's own terminals (tty0, tty1) only. A serial console is
    often logged on another machine (a hypervisor serial log, a terminal server, QEMU `-serial file:`), so the key goes
    to a serial port only when the owner booted the first time with `onemind.recovery_key=serial` (a headless box
    whose serial line the owner trusts). Anything else (hvc0, a USB console, /dev/console) never gets it."""
    if names is None:
        names = [d[len("/dev/"):] for d in console_devices()]
    serial_ok = KEY_SERIAL_OPT_IN in (cmdline() if text is None else text).split()
    return ["/dev/" + n for n in names if SCREEN_RX.match(n) or (serial_ok and SERIAL_RX.match(n))]


def show_recovery_key(key, devices=None):
    """Show the key once on the terminals key_terminals allows, never the journal and never /dev/console. Returns
    how many terminals took it (0 on a box with no screen and no opt-in: the key is then only in RECOVERY_FILE)."""
    devs = key_terminals() if devices is None else devices
    if not devs:
        return 0
    return to_consoles("ONEMIND-DATA-CRYPT: RECOVERY KEY (write it down now, it is shown once): " + key, devs,
                       fallback=False)


def serial_consoles(names=None):
    """The serial ports the kernel console runs on (/dev/ttyS0 ...), never the screen (tty0)."""
    if names is None:
        names = [d[len("/dev/"):] for d in console_devices()]
    return ["/dev/" + n for n in names if SERIAL_RX.match(n)]


@contextlib.contextmanager
def serial_prompt_agent(devices=None, popen=subprocess.Popen):
    """While a question is open (the passphrase or recovery key prompt), also ask it on the serial console.
    Why: while the boot splash (plymouth) runs, systemd's own console agent is switched off
    (systemd-ask-password-console.path has ConditionPathExists=!/run/plymouth/pid) and the question goes to plymouth
    only, which draws on the screen and never on a serial port (`plymouth.ignore-serial-consoles`). A box reached over
    a serial console (a VM, a headless server, the QEMU battery) would sit at an invisible prompt. This starts the
    same agent systemd uses, pointed at each serial console; whoever answers first (the screen or a serial line)
    wins and the other agent drops the question. Nothing is started on a box with no serial console, and the agents
    are always stopped afterwards (serial-getty takes the port next)."""
    procs = []
    for dev in (serial_consoles() if devices is None else devices):
        try:
            procs.append(popen([AGENT, "--watch", f"--console={dev}"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True))
        except OSError:
            pass
    try:
        yield len(procs)
    finally:
        for p in procs:
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except OSError:
                pass
            try:
                p.wait(5)
            except (subprocess.TimeoutExpired, OSError):
                pass


def say(msg, journal=True):
    """To the consoles (screen and serial, see console_devices) and (unless `journal` is False) the journal. Never
    for the recovery key: that goes through show_recovery_key (screen only by default, #1118)."""
    line = f"ONEMIND-DATA-CRYPT: {msg}"
    if journal:
        print(line, flush=True)
    to_consoles(line)


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
    if sig in ("ext4", "btrfs"):
        return sig
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


def plan(has_tpm, opted_in, firmware_tpm=False):
    """The founder's rule: 'tpm2' (encrypted, unlocks by itself), 'passphrase' (no TPM, the owner asked), 'recovery-key'
    (the firmware announces a TPM that is not usable this boot: encrypted, never plain) or 'plain'."""
    if has_tpm:
        return "tpm2"
    if opted_in:
        return "passphrase"
    return "recovery-key" if firmware_tpm else "plain"


def read_sysfs(path):
    """The stripped text of a small sysfs file, or None when it cannot be read."""
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def firmware_has_tpm():
    """True when the firmware says this box has a TPM 2.0, whether or not the kernel's driver has made /dev/tpmrm0 yet.
    A TPM 1.2 (or a version that cannot be read) is False, as in systemd's efi_has_tpm2(): such a box follows the
    no-TPM rule (plain unless the owner asks), because a TPM 1.2 can never unlock the disk by itself."""
    if os.path.exists(ACPI_TPM2):
        return True
    return os.path.exists(EVENT_LOG) and read_sysfs(TPM_VERSION_MAJOR) == "2"


def cmdline():
    try:
        with open("/proc/cmdline") as f:
            return f.read()
    except OSError:
        return ""


def wants_passphrase(text):
    return OPT_IN in text.split()


def ask_passphrase(runner=run, tries=3):
    """Ask the owner at the console (systemd's password agents; no timeout) for a new passphrase, twice.
    Returns it, or None after `tries` failed rounds. It is held in memory only and never said or logged."""
    ask = lambda prompt: runner(["systemd-ask-password", "--timeout=0", "--id=onemind-data-new", prompt], check=False)
    with serial_prompt_agent():
        return _ask_twice(ask, tries)


def _ask_twice(ask, tries):
    for _ in range(tries):
        a = ask("Choose a passphrase for the OneMind data disk (it is asked at every restart):")
        if a.returncode != 0:
            say("no passphrase was given")
            continue
        first = a.stdout.rstrip("\n")
        if len(first) < MIN_PASSPHRASE:
            say(f"that passphrase is shorter than {MIN_PASSPHRASE} characters; try again")
            continue
        b = ask("Type the same passphrase again:")
        if b.returncode != 0 or b.stdout.rstrip("\n") != first:
            say("the two passphrases did not match; try again")
            continue
        return first
    return None


def identity(node, runner=run):
    """(LUKS UUID, GPT partition UUID) of `node`, lower case, '' for one blkid cannot read."""
    out = runner(["blkid", "-p", "-o", "export", node], check=False).stdout
    kv = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return kv.get("UUID", "").lower(), kv.get("PART_ENTRY_UUID", "").lower()


def onemind_token(set_uuid, member_uuid, partuuid, generation=1):
    """The token JSON the reset and the boot assembly read (storage.Token): set, member, own partition, generation."""
    return json.dumps({"type": TOKEN_TYPE, "keyslots": [], "set_uuid": set_uuid, "member_uuid": member_uuid,
                       "partuuid": partuuid, "generation": generation})


def write_token(node, set_uuid, runner=run):
    """Give the LUKS2 header the OneMind token (header only: it needs no key). Without the partition's own GPT id
    the token would name no partition and the reset would skip the disk, so then no token is written and the box
    says so; it still works, it just cannot be factory-reset until the token is added."""
    luks_uuid, partuuid = identity(node, runner)
    if not partuuid:
        say("the data partition has no GPT partition id; the OneMind token was not written, so a factory reset "
            "will refuse this box")
        return False
    runner(["cryptsetup", "token", "import", "--token-id", str(TOKEN_ID), node],
           input=onemind_token(set_uuid, luks_uuid, partuuid))
    return True


def make_btrfs(dev, runner=run, force=False, set_uuid=None):
    """btrfs on `dev` with the subvolumes in SUBVOLS, @ set as the default (so /etc/fstab needs no subvol= option and
    the same line still mounts the ext4 of older boxes). `force` only for a LUKS volume made seconds ago, whose
    content is random-looking; on a raw partition mkfs must refuse anything it recognises."""
    runner(["mkfs.btrfs", "-q", "--nodiscard", "-L", LABEL] + (["-U", set_uuid] if set_uuid else []) +
           (["-f"] if force else []) + [dev])
    os.makedirs(MKFS_MNT, mode=0o700, exist_ok=True)
    runner(["mount", "-t", "btrfs", "-o", "subvolid=5", dev, MKFS_MNT])
    try:
        for sv in SUBVOLS:
            runner(["btrfs", "subvolume", "create", f"{MKFS_MNT}/{sv}"])
        runner(["btrfs", "subvolume", "create", f"{MKFS_MNT}/{SNAPSHOTS_SUBVOL}"])
        runner(["chmod", "0750", f"{MKFS_MNT}/{SNAPSHOTS_SUBVOL}"])   # snapper wants its snapshot directory root-only
        os.makedirs(f"{MKFS_MNT}/{STORAGE_DIR}", mode=0o755, exist_ok=True)   # data-storage.mount runs only if this exists
        runner(["btrfs", "subvolume", "set-default", f"{MKFS_MNT}/{SUBVOLS[0]}"])
    finally:
        runner(["umount", MKFS_MNT], check=False)


def make_plain(node, runner=run):
    """No TPM and no opt-in: btrfs straight on the blank partition. On failure, back to blank for the next boot."""
    try:
        make_btrfs(node, runner)
    except BaseException:
        runner(["wipefs", "--all", "--force", node], check=False)
        zero_head(node)
        raise


def first_boot_encrypt(node, has_tpm, runner=run, rand=os.urandom, passphrase=None):
    """Blank partition -> LUKS2 + btrfs + recovery key (+ TPM2, + the owner's passphrase).
    Returns {'recovery_key', 'tpm2', 'passphrase'}. On any failure the partition is wiped (signatures, then the
    first 16 MiB zeroed) back to blank (it held nothing) so the next boot retries."""
    dev = "/dev/mapper/" + NAME
    set_uuid = str(uuid.uuid4())             # the set's id: the btrfs UUID and the OneMind token's set_uuid
    fd = os.open(KEYFILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(rand(64))
    opened = False
    try:
        # The key is 512 random bits, so a slow password hash would only slow every boot: one iteration batch.
        runner(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--cipher", "aes-xts-plain64",
                "--key-size", "512", "--pbkdf", "pbkdf2", "--pbkdf-force-iterations", "1000",
                "--key-file", KEYFILE, node])
        write_token(node, set_uuid, runner)
        runner(["cryptsetup", "open", "--key-file", KEYFILE, "--perf-no_read_workqueue",
                "--perf-no_write_workqueue", "--persistent", node, NAME])
        opened = True
        make_btrfs(dev, runner, force=True, set_uuid=set_uuid)
        out = runner(["systemd-cryptenroll", "--unlock-key-file=" + KEYFILE, "--recovery-key", node]).stdout
        key = parse_recovery_key(out)
        if not key:
            raise RuntimeError("systemd-cryptenroll printed no recovery key")
        if passphrase:
            # Read from stdin to EOF (no newline added): the boot prompt hands systemd-cryptsetup the same bytes.
            runner(["cryptsetup", "luksAddKey", "--batch-mode", "--pbkdf", "argon2id", "--key-file", KEYFILE, node, "-"],
                   input=passphrase)
        tpm2 = False
        if has_tpm:
            r = runner(["systemd-cryptenroll", "--unlock-key-file=" + KEYFILE, "--tpm2-device=auto",
                        "--tpm2-pcrs=7", node], check=False)
            tpm2 = r.returncode == 0
            if not tpm2:
                say("the TPM would not take the key; this box unlocks with the recovery key only")
        # Hygiene: the random key is about to be deleted, so its slot is dead weight. Best effort. luksKillSlot
        # checks the key it is given against the OTHER slots, so the recovery key (a passphrase slot) goes on stdin.
        runner(["cryptsetup", "luksKillSlot", "--batch-mode", "--key-file", "-", node, "0"], input=key, check=False)
        return {"recovery_key": key, "tpm2": tpm2, "passphrase": bool(passphrase)}
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
        say("no TPM here: type the passphrase or the recovery key to unlock the data disk")
    with serial_prompt_agent():
        r = runner([CRYPTSETUP, "attach", NAME, node, "none", "luks,tries=3"], check=False)
    return "recovery-key" if r.returncode == 0 else None


def wait_for(path, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if os.path.exists(path):
            return True
        time.sleep(0.5)
    return os.path.exists(path)


def reset_armed(runner=run, node=ESP_NODE, probe=ESP_PROBE):
    """True when an armed factory reset is waiting on the ESP. Why this unit asks: it runs before the ESP is mounted, and
    the reset (onemind-factory-reset.service, after this) erases the data disk. Unlocking it first would ask a
    passphrase box for the passphrase of data the owner just approved erasing, and a TPM box would open it; after the wipe
    the keyslots are gone, so a headless box would then wait for a recovery key for ever. The ESP is mounted read-only,
    only for this look, and any doubt answers False (a normal boot)."""
    if not os.path.exists(node):
        return False
    try:
        os.makedirs(probe, exist_ok=True)
    except OSError:
        return False
    if runner(["mount", "-o", "ro,nosuid,nodev,noexec", "-t", "vfat", node, probe], check=False).returncode != 0:
        return False
    try:
        return os.path.exists(os.path.join(probe, RESET_MARKER))
    finally:
        runner(["umount", probe], check=False)


def main(runner=run):
    if not wait_for(f"/dev/disk/by-partlabel/{LABEL}"):
        say(f"no partition labelled {LABEL}; nothing to do")
        return 0
    node = os.path.realpath(f"/dev/disk/by-partlabel/{LABEL}")
    if os.path.exists("/dev/mapper/" + NAME):
        return 0                                     # already open (this is not the first run of the boot)
    if reset_armed(runner):
        write_state(state="reset-pending", reason="a factory reset is armed; the data disk is not opened")
        say("a factory reset is armed: not opening or making the data disk; it is wiped next and the box restarts")
        return 0
    has_tpm = os.path.exists(TPM_DEV)
    firmware_tpm = has_tpm or firmware_has_tpm()
    if firmware_tpm and not has_tpm:
        say(f"the firmware announces a TPM 2.0 but {TPM_DEV} is missing (its driver did not come up); the TPM is not "
            "used this boot and the disk is encrypted with the recovery key, never left plain")
    kind = classify(signature(node, runner), head_is_zero(node))
    if kind == "ext4":
        write_state(state="plain", fs="ext4", reason="installed before encryption; left as it is")
        say("the data partition is plain ext4 (an earlier install); left untouched")
    elif kind == "btrfs":
        write_state(state="plain", fs="btrfs", reason="unencrypted (no TPM and no passphrase asked for)")
        say("the data partition is plain btrfs (no TPM); left untouched")
    elif kind == "blank":
        opted_in = wants_passphrase(cmdline())
        mode = plan(has_tpm, opted_in, firmware_tpm)
        if has_tpm and opted_in:
            say("this box has a TPM, so it unlocks by itself; the passphrase option is for boxes without one")
        if mode == "plain":
            say("blank data partition, no TPM: making it plain btrfs, NOT encrypted (a box without a TPM could not "
                f"come back by itself after a power cut; to encrypt, boot the first time with {OPT_IN})")
            make_plain(node, runner)
            write_state(state="plain", fs="btrfs", reason="no TPM; encryption not asked for")
            say("data partition ready (btrfs, unencrypted)")
            runner(["udevadm", "settle", "--timeout=20"], check=False)
            return 0
        passphrase = None
        if mode == "passphrase":
            say("blank data partition, no TPM, encryption asked for: choose the passphrase you will type at every restart")
            passphrase = ask_passphrase(runner)
            if not passphrase:
                write_state(state="blank", reason="encryption asked for but no passphrase chosen; asked again next boot")
                say("no passphrase chosen: the data partition stays blank and is not used this boot")
                return 0
        if mode == "recovery-key":
            say("blank data partition on a TPM box whose TPM is not ready: encrypting anyway (LUKS2 + btrfs), unlocked "
                "with the recovery key until the TPM is enrolled; never left plain")
        else:
            say("blank data partition: making it LUKS2 + btrfs" + (" with TPM2 unlock" if has_tpm else " with your passphrase"))
        res = first_boot_encrypt(node, has_tpm, runner, passphrase=passphrase)
        passphrase = None
        how = "tpm2" if res["tpm2"] else ("passphrase" if res["passphrase"] else "recovery-key")
        keep_recovery_key(res["recovery_key"])
        write_state(state="encrypted", fs="btrfs", unlock=how, tpm2=res["tpm2"])
        shown = show_recovery_key(res["recovery_key"])
        say(f"recovery key made: shown on {shown} terminal(s): the screen, and a serial console only with {KEY_SERIAL_OPT_IN}; "
            "kept in RAM for the recovery kit until the next restart")
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
        write_state(state="unknown", reason="the partition holds something that is neither blank, ext4, btrfs nor LUKS2")
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
