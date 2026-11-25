#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""A guided, plain-language walk through the root-key ceremony (REL-01, #153, decision D-010).

It wraps os/update/CEREMONY.md and scripts/tuf-bootstrap-root.sh for the one-time job of making
OneMind's root of trust, on the OFFLINE machine. It does not do any cryptography itself: it checks
each condition, tells you what to plug in and what to do, runs the existing ceremony script for you,
verifies each result before moving on, and prints the final sheet.

    python3 scripts/ceremony-guide.py                 the real ceremony (offline machine, a terminal)
    python3 scripts/ceremony-guide.py --rehearsal     the same walk with throwaway keys in a temp
                                                      directory; ends with REHEARSAL PASSED
    python3 scripts/ceremony-guide.py --work DIR      resume an interrupted ceremony (same DIR)

D-010: THREE holders, three encrypted sticks, any 2 of the 3 sign. If one person must do it alone,
pass --solo-differs-from-d010: the keys are the same, but custody is NOT what D-010 asks for and the
founder has to decide whether to accept it. The guide never invents a weaker scheme.

Passphrases: typed only into the ceremony script's own no-echo prompts. This program never reads,
prints, logs, stores or passes one (a throwaway one is set only in --rehearsal). The log it keeps
(<work>/guide.log) holds only its own messages and public values.
"""
import argparse, hashlib, json, os, plistlib, shutil, subprocess, sys, tempfile, time

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPT = os.path.join(REPO, "scripts", "tuf-bootstrap-root.sh")
PASSPHRASE_ENV = "ONEMIND_TUF_PASSPHRASE"
REHEARSAL_PASS = "rehearsal-throwaway-passphrase"
SOLO_FLAG = "--solo-differs-from-d010"
HOLDERS = ("A", "B", "C")
STATE_VERSION = 1

NEEDS = """\
WHAT YOU NEED AND HOW LONG IT TAKES  (one page, read it before you start)

  Time      About 60 to 90 minutes the first time. Rehearsal: about 2 minutes.
  People    Three key holders in one room (you and two people you trust). Only two of them sign,
            but all three make a key. D-010 requires three different holders.
  Things    - 3 USB sticks, one per holder, each ALREADY ENCRYPTED (CEREMONY.md step 3:
              Mac "APFS (Encrypted)", Linux "LUKS"). Plug in only the one asked for. (Signing: the
              two signers' sticks must be plugged in TOGETHER, and the guide says when.)
            - 1 more stick (the "transfer stick"). It carries root.json (public) to the online
              computer. The three online PRIVATE keys ride on it too, only for the GitHub step
              (CEREMONY.md step 9); it is wiped after that. It is never a holder's stick.
            - This computer with the network OFF: Wi-Fi, Bluetooth, cable. Ideally a Debian
              live USB, which forgets everything at shutdown.
            - Paper and a printer for the final sheet (or a pen to copy the numbers).
            - The python-tuf tools, installed BEFORE going offline (CEREMONY.md, step 0).
  Each holder  picks their own passphrase (12+ characters, a few random words is good) and types it
            at a prompt that shows nothing. Nobody else sees it. A lost passphrase cannot be
            recovered, so each holder keeps it safe (a password manager, or paper in a safe).
  The sheet at the end has the numbers all three holders read aloud and sign.
  You can stop at any time (Ctrl+C) and continue later with the same --work folder.
"""

SOLO_WARNING = """\
!! SOLO MODE: this is NOT the ceremony D-010 requires.
!! D-010 says three DIFFERENT holders, each with their own stick and passphrase. Here one person
!! does all three parts, so one person (or one stolen laptop plus the notes) could reach two keys.
!! The keys and the 2-of-3 rule are the same; the custody is weaker. The founder has to decide
!! whether to accept that before this root is used for real. The final sheet repeats this.
"""

D010 = ("D-010 requires: three root keys, each held by a different person on their own encrypted "
        "stick, and any 2 of the 3 must sign. One lost or stolen stick changes nothing by itself.")


class Stop(Exception):
    """A refusal or a failed check: the message says what to do. Nothing unsafe has happened."""


class Io:
    """All talking goes through here so the transcript is logged and tests can script the answers."""

    def __init__(self, log_path=None, auto=False, answers=None):
        self.log_path, self.auto, self.answers = log_path, auto, list(answers or [])
        self.log_file = None

    def open_log(self, path):
        self.log_path = path
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        self.log_file = os.fdopen(fd, "a")

    def say(self, text="", err=False):
        print(text, file=sys.stderr if err else sys.stdout, flush=True)
        if self.log_file:
            self.log_file.write(text + "\n"); self.log_file.flush()

    def ask(self, prompt, auto=None):
        """Ask for a plain (echoed) answer: a name, a folder, a confirmation. Never a passphrase."""
        if self.answers:
            a = self.answers.pop(0)
        elif self.auto:
            a = auto if auto is not None else ""
        else:
            a = input(prompt + " ")
        if self.log_file:
            self.log_file.write(f"{prompt} -> {a}\n"); self.log_file.flush()
        return a.strip()

    def pause(self, prompt="Press Enter to continue"):
        if not (self.auto or self.answers):
            self.ask(prompt)

    def confirm_word(self, prompt, word):
        a = self.ask(f"{prompt} Type {word} to confirm:", auto=word)
        if a != word:
            raise Stop(f"you did not type {word}; stopping here. Nothing was changed. Run the guide again to continue.")


def _probe(cmd):
    """Run one routing-table probe. Returns (ran_ok, stdout, stderr); ran_ok is False if it could not run."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False, "", ""
    return r.returncode == 0, r.stdout, r.stderr


_ROUTE_REASON = None    # why the last default_route() answered True (for the message), else None


def default_route():
    """True when this machine may be online. Deny by default: True also means "could not prove it is offline".

    Checks IPv4 and IPv6 default routes. If a probe cannot run or gives no usable answer, the
    answer is True (refuse), so a minimal system without iproute2 never passes as offline.
    """
    global _ROUTE_REASON
    _ROUTE_REASON = None
    if os.environ.get("ONEMIND_GUIDE_TEST_ROUTE") == "present":   # test hook; can only make it stricter
        return True
    if sys.platform == "darwin":
        for fam in ("-inet", "-inet6"):
            ok, _out, err = _probe(["route", "-n", "get", fam, "default"])
            if ok:
                return True
            if "not in table" not in err:      # failed for some other reason: unknown, so refuse
                return True
        return False
    for fam in ("-4", "-6"):
        ok, out, _err = _probe(["ip", fam, "route", "show", "default"])
        if not ok:
            if fam == "-6" and not os.path.exists("/proc/net/if_inet6"):
                _ROUTE_REASON = ("IPv6 is switched off in this computer's kernel, so the IPv6 half of the network check "
                                 "cannot run and the guide cannot prove the machine is offline. It refuses to be safe. "
                                 "Boot with IPv6 enabled (remove ipv6.disable=1 from the boot options, or use the "
                                 "standard Debian live USB), then run this again.")
            return True                        # cannot tell (no ip binary, or ip failed): refuse
        if any(l.split()[:1] == ["default"] for l in out.splitlines()):
            return True
    return False


def stick_identity(p):
    """A volume identifier for the stick holding folder p, or None where the platform gives none.

    Two sticks can share a label and a mount path, so the path alone cannot tell them apart. macOS:
    diskutil's VolumeUUID; Linux: the filesystem UUID from findmnt. Returns (id_or_None, note); the
    note says what could not be done on which platform."""
    try:
        if sys.platform == "darwin":
            ok, out, _e = _probe(["diskutil", "info", "-plist", p])
            if ok:
                info = plistlib.loads(out.encode())
                v = info.get("VolumeUUID") or info.get("DiskUUID")
                if v:
                    return str(v), None
        elif sys.platform.startswith("linux"):
            ok, out, _e = _probe(["findmnt", "-n", "-o", "UUID", "-T", p])
            if ok and out.strip():
                return out.strip(), None
    except Exception:
        pass
    tool = "diskutil" if sys.platform == "darwin" else "findmnt"
    return None, (f"could not read a volume identifier for that stick on {sys.platform} (this needs {tool}); "
                  "comparing mount folders only, so check by eye that each holder has a different stick")


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if r.returncode:
        raise Stop(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root + os.sep)


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class Guide:
    def __init__(self, io, work, repo=REPO, rehearsal=False, solo=False, channels=("security",),
                 expect_commit=None, stop_after=None, python=None):
        self.io, self.work, self.repo = io, os.path.abspath(work), repo
        self.rehearsal, self.solo, self.channels = rehearsal, solo, tuple(channels)
        self.expect_commit, self.stop_after = expect_commit, stop_after
        self.python = python or os.environ.get("PYTHON") or "python3"
        self.state_path = os.path.join(self.work, "state.json")
        self.state = {"v": STATE_VERSION, "done": [], "holders": {}, "signers": [], "channels": list(self.channels),
                      "rehearsal": rehearsal, "solo": solo}

    # ---- state ----
    def load_state(self):
        if os.path.exists(self.state_path):
            s = json.load(open(self.state_path))
            if s.get("v") != STATE_VERSION or s.get("rehearsal") != self.rehearsal or s.get("solo") != self.solo:
                raise Stop("the work folder holds a ceremony started in a different mode; use a new --work folder")
            self.state = s
            self.channels = tuple(s["channels"])
            return True
        return False

    def save(self):
        tmp = self.state_path + ".tmp"
        with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.state_path)

    def step(self, name, fn):
        if name in self.state["done"]:
            self.io.say(f"[skip] {name}: already done earlier")
            return
        fn()
        self.state["done"].append(name)
        self.save()
        if self.stop_after == name:
            raise Stop(f"stopped after {name} as asked (--stop-after); run again with the same --work to resume")

    # ---- running the real ceremony script ----
    def env(self):
        env = {k: v for k, v in os.environ.items() if k != PASSPHRASE_ENV}
        env["PYTHON"] = self.python
        if self.rehearsal:
            env[PASSPHRASE_ENV] = REHEARSAL_PASS     # throwaway, rehearsal only
        return env

    def run_script(self, *args, capture=False, quiet=False):
        """Run scripts/tuf-bootstrap-root.sh. Not captured: it inherits the terminal so its own
        no-echo prompts work (and this program never sees what is typed)."""
        if capture:
            r = subprocess.run(["sh", SCRIPT, *args], env=self.env(), capture_output=True, text=True)
            if not quiet:
                self.io.say((r.stdout + r.stderr).rstrip())
            return r.returncode
        return subprocess.run(["sh", SCRIPT, *args], env=self.env()).returncode

    # ---- steps ----
    def preflight(self):
        io = self.io
        io.say("STEP 1 of 7: safety checks")
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            raise Stop("refusing: a root key is made by people, offline, never in CI.")
        if default_route():
            msg = ("this computer can reach a network (it has a default route). A real root must be made on a "
                   "computer with NO network: switch off Wi-Fi and Bluetooth, unplug the cable, then run this again.")
            if _ROUTE_REASON:
                msg = _ROUTE_REASON + " (A real root must be made on a computer with NO network.)"
            if not self.rehearsal:
                raise Stop("refusing: " + msg)
            io.say("note (rehearsal only): " + msg)
        else:
            io.say("ok: no network route.")
        if inside(self.work, self.repo):
            raise Stop("--work must be OUTSIDE the repository (the repo has to stay clean). Pick a folder elsewhere.")
        commit = git(self.repo, "rev-parse", "HEAD")
        dirty = git(self.repo, "status", "--porcelain")
        if dirty and not self.rehearsal:
            raise Stop("the repository has uncommitted changes. The ceremony must run from a clean, reviewed commit. "
                       "Run `git status`, undo or commit the changes, then start again.")
        if dirty:
            io.say("note (rehearsal only): the working tree is not clean.")
        io.say(f"repository commit: {commit}")
        if not self.rehearsal:
            want = self.expect_commit or io.ask("Type the first 12 characters of the commit hash written on your checklist:")
            if not want or len(want) < 12 or not commit.startswith(want.lower()):
                raise Stop("that does not match the commit on this computer. Check out the commit on your checklist, then start again.")
            io.say("ok: commit matches your checklist.")
        prev = self.state.get("commit")
        if prev and prev != commit:
            raise Stop(f"this ceremony was started at commit {prev[:12]} and the repo is now at {commit[:12]}. "
                       "Check out the original commit to resume, or use a new --work folder.")
        self.state["commit"] = commit
        r = subprocess.run([self.python, "-c", "import tuf, securesystemslib"], capture_output=True)
        if r.returncode:
            raise Stop("the python-tuf tools are missing. Install them BEFORE going offline: "
                       "python3 -m venv V && V/bin/pip install --require-hashes --only-binary :all: "
                       "-r os/update/requirements-tuf.txt, then run with PYTHON=V/bin/python (CEREMONY.md step 0).")
        io.say("ok: signing tools are installed.")

    def holders(self):
        io = self.io
        io.say("\nSTEP 2 of 7: who is here")
        io.say(D010)
        if self.solo:
            io.say(SOLO_WARNING, err=True)
            name = io.ask("Your name (you will act as holders A, B and C):", auto="Solo Operator") or "operator"
            names = {h: name for h in HOLDERS}
        else:
            names = {}
            for h in HOLDERS:
                n = io.ask(f"Holder {h}, type your own name (you are here in person):", auto=f"Rehearsal {h}")
                if not n:
                    raise Stop("every holder must type their name; stopping.")
                if n.lower() in (v.lower() for v in names.values()):
                    raise Stop("two holders cannot be the same person under D-010 "
                               f"(pass {SOLO_FLAG} only if the founder has accepted that). Stopping.")
                names[h] = n
        self.state["holders"] = names
        io.say("holders: " + ", ".join(f"{h}={n}" for h, n in names.items()))

    def on_work_disk(self, p):
        try:
            return os.stat(p).st_dev in (os.stat(self.work).st_dev, os.stat(self.repo).st_dev)
        except OSError as e:
            raise Stop(f"cannot read that folder: {e}")

    def stick_path(self, h, need_key, keep=()):
        """Ask for holder h's stick folder and check it is a safe place. Returns the folder.

        keep: holders whose sticks must STAY plugged in (signing needs both signers' sticks together)."""
        io, names = self.io, self.state["holders"]
        if self.rehearsal:
            p = os.path.join(self.work, "sticks", f"holder-{h.lower()}")
            os.makedirs(p, mode=0o700, exist_ok=True)
            return p
        who = names[h]
        if keep:
            kept = " and ".join(f"holder {k} ({names[k]})'s" for k in keep)
            io.say(f"\n  >> {who} (holder {h}): plug in YOUR OWN encrypted USB stick now, unlock it, and KEEP {kept} stick "
                   "PLUGGED IN. Do NOT remove it: both signers' sticks must be in at the same time. "
                   "Take out only sticks that belong to nobody signing.")
        else:
            io.say(f"\n  >> {who} (holder {h}): plug in YOUR OWN encrypted USB stick now, unlock it, and remove any other stick.")
        p = io.ask(f"  Type the folder where {who}'s stick is mounted (e.g. /Volumes/STICK-A or /media/user/STICK-A):")
        if not p or not os.path.isdir(p):
            raise Stop("that folder does not exist. Mount the stick, find its folder in your file manager, and try again.")
        p = os.path.realpath(p)
        if inside(p, self.repo) or inside(p, self.work):
            raise Stop("that folder is on this computer's disk, not on a stick. Plug in the stick and give its folder.")
        if self.on_work_disk(p):
            raise Stop("that folder is on the same disk as this computer's work folder, so it is not a separate stick.")
        if not os.access(p, os.W_OK):
            raise Stop("that stick is read-only or locked. Unlock it (write-enabled) and try again.")
        seen = self.state.setdefault("sticks_seen", {})
        ids = self.state.setdefault("stick_ids", {})
        sid, note = stick_identity(p)
        if note:
            io.say("  note: " + note)
        for other, op in seen.items():
            if other == h:
                continue
            oid = ids.get(other)
            same = (sid == oid) if (sid and oid) else (os.path.realpath(op) == p)   # ids when both known, else path
            if same:
                raise Stop(f"that is the same stick as holder {other}. Each holder needs their own stick, even in solo mode.")
        seen[h], ids[h] = p, sid
        io.confirm_word(f"  Is this stick encrypted (CEREMONY.md step 3) and does it belong to {who}?", "ENCRYPTED")
        has = os.path.exists(os.path.join(p, "root.key"))
        if need_key and not has:
            raise Stop(f"no root.key found on that stick; is it holder {h}'s stick?")
        return p

    def make_root_key(self, h):
        io = self.io
        p = self.stick_path(h, need_key=False)
        key, pub = os.path.join(p, "root.key"), os.path.join(p, "root.pub")
        if os.path.exists(key):
            io.say(f"  a root.key is already on holder {h}'s stick (probably an interrupted run).")
            io.confirm_word("  Keep it and carry on with it? (You must remember its passphrase.)", "KEEP")
        else:
            io.say(f"  Now {self.state['holders'][h]} chooses a passphrase (12+ characters). The next two prompts show NOTHING as you type; that is normal.")
            if self.run_script("root-key", p, "root") != 0:
                raise Stop(f"making holder {h}'s key failed (message above). Nothing was kept; fix the problem and run again.")
        self.verify_key_files(h, key, pub)
        os.makedirs(os.path.join(self.work, "pubs"), mode=0o700, exist_ok=True)
        shutil.copyfile(pub, os.path.join(self.work, "pubs", f"{h.lower()}.pub"))
        io.say(f"  ok: holder {h} has root.key (locked with a passphrase) and root.pub.")

    def verify_key_files(self, h, key, pub):
        if not (os.path.isfile(key) and os.path.isfile(pub)):
            raise Stop(f"holder {h}'s stick is missing root.key or root.pub after the step.")
        if b"ENCRYPTED PRIVATE KEY" not in open(key, "rb").read():
            raise Stop(f"holder {h}'s root.key is NOT passphrase-protected. Delete it from the stick and redo this holder.")
        if b"PRIVATE" in open(pub, "rb").read():
            raise Stop(f"holder {h}'s root.pub contains private material. Stop and tell the founder.")

    def keys(self):
        io = self.io
        io.say("\nSTEP 3 of 7: each holder makes their own root key")
        io.say("Each holder, one at a time, with only their own stick plugged in.")
        done = self.state.setdefault("keys_done", [])
        for h in HOLDERS:
            if h in done:
                io.say(f"  holder {h}: key already made."); continue
            io.say(f"\n--- holder {h}: {self.state['holders'][h]} ---")
            self.make_root_key(h)
            done.append(h); self.save()
            if not self.rehearsal:
                io.say("  Now unplug this stick and put it aside. It is the only home of this private key.")
                io.pause()

    def online_keys(self):
        io = self.io
        io.say("\nSTEP 4 of 7: the online keys (targets, snapshot, timestamp)")
        io.say("These three are different from the root keys. The release robot signs with them, so later they go into GitHub as secrets.")
        out = os.path.join(self.work, "online")
        if os.path.isdir(out) and os.listdir(out):
            shutil.rmtree(out)           # a half-made set from an interrupted run: remake it whole
        if self.run_script("online-keys", out) != 0:
            raise Stop("making the online keys failed (message above).")
        for r in ("targets", "snapshot", "timestamp"):
            for ext in ("key", "pub"):
                if not os.path.isfile(os.path.join(out, f"{r}.{ext}")):
                    raise Stop(f"online/{r}.{ext} is missing after the step.")
        io.say("ok: six online key files made.")

    def signers(self):
        io = self.io
        names = self.state["holders"]
        io.say("\nSTEP 5 of 7: choose the two holders who sign")
        if io.auto and not io.answers:
            pick = ["A", "B"]
        else:
            a = io.ask("Which two holders are signing? (default A and B; type two letters, e.g. AB):", auto="AB").upper()
            pick = [c for c in a if c in HOLDERS] or ["A", "B"]
        if len(set(pick)) != 2:
            raise Stop("pick exactly two different holders (the 2 in 2-of-3).")
        self.state["signers"] = sorted(set(pick))
        io.say("signers: " + ", ".join(f"{h}={names[h]}" for h in self.state["signers"]) +
               "; the third holder's stick stays in its safe place, untouched.")

    def sign(self):
        io = self.io
        io.say("\nSTEP 6 of 7: sign the root")
        sigs = self.state["signers"]
        paths = {}
        io.say("Both signers' sticks must be plugged in AT THE SAME TIME when the root is signed.")
        for h in sigs:
            io.say(f"\n--- signer {h}: {self.state['holders'][h]} ---")
            paths[h] = self.stick_path(h, need_key=True, keep=tuple(paths))
        io.say("\nBoth signers' sticks should now be plugged in. Leave them in until signing is finished.")
        pubs = os.path.join(self.work, "pubs")
        others = [os.path.join(pubs, f"{h.lower()}.pub") for h in HOLDERS if h not in sigs]
        online = os.path.join(self.work, "online")
        for ch in self.channels:
            out = os.path.join(self.work, f"out-{ch}")
            if os.path.exists(os.path.join(out, "root.json")):
                io.say(f"channel {ch}: root already made; checking it."); continue
            self.check_signer_keys(paths)       # every signer's key must be readable right now
            io.say(f"\nChannel {ch}: each signer now types their passphrase at the prompt that shows nothing.")
            args = ["create", out, ch, "2", *[os.path.join(paths[h], "root.key") for h in sigs], *others, "--",
                    os.path.join(online, "targets.pub"), os.path.join(online, "snapshot.pub"), os.path.join(online, "timestamp.pub")]
            if self.run_script(*args) != 0:
                self.check_signer_keys(paths)   # a stick pulled out meanwhile is named, not blamed on a passphrase
                raise Stop("signing failed (message above) although both root.key files are still readable, so a wrong "
                           "passphrase is the likely cause. Nothing was written. Run the guide again with the same --work "
                           "folder: it will ask both signers to plug in their sticks together, then retry this step.")
            if not os.path.isfile(os.path.join(out, "root.json")):
                raise Stop("signing reported success but root.json is missing.")

    def check_signer_keys(self, paths):
        """Each signer's root.key must exist and be readable now. Names the holder whose stick is missing."""
        names = self.state["holders"]
        for h, p in paths.items():
            key = os.path.join(p, "root.key")
            try:
                with open(key, "rb") as f:
                    f.read(1)
            except OSError:
                raise Stop(f"holder {h} ({names[h]})'s stick is not plugged in (or is locked): cannot read {key}. "
                           f"Plug it in and unlock it, KEEP the other signer's stick plugged in too (both are needed together), "
                           "then run the guide again with the same --work folder. Nothing was written.")

    def verify_and_sheet(self):
        io = self.io
        io.say("\nSTEP 7 of 7: check the result and print the sheet")
        sheets, solo_note = [], (SOLO_WARNING if self.solo else "")
        for ch in self.channels:
            out = os.path.join(self.work, f"out-{ch}")
            root = os.path.join(out, "root.json")
            if self.run_script("check", out, "2", "3", capture=True) != 0:
                raise Stop(f"the check of channel {ch} FAILED. Do not use these files. Tell the founder.")
            signed = json.load(open(root))["signed"]
            rk = signed["roles"]["root"]
            if rk["threshold"] != 2 or len(set(rk["keyids"])) != 3:
                raise Stop(f"channel {ch}: the root is not 2-of-3 with three different keys. Do not use it.")
            for role in ("targets", "snapshot", "timestamp"):
                if len(signed["roles"][role]["keyids"]) != 1:
                    raise Stop(f"channel {ch}: {role} does not have exactly one key. Do not use it.")
            sheets.append((ch, sha256_file(root), signed))
        lines = ["", "=" * 70, "THE SHEET: all three holders read these lines aloud from the screen, then sign the printout", "=" * 70]
        lines.append("commit:  " + self.state["commit"])
        lines.append("holders: " + ", ".join(f"{h}={n}" for h, n in self.state["holders"].items()) +
                     "   signed: " + "+".join(self.state["signers"]))
        for ch, sha, signed in sheets:
            lines.append(f"\nchannel {ch}   root.json sha256 {sha}")
            lines.append("  root keys (2 of 3 must sign): " + "  ".join(k[:16] for k in signed["roles"]["root"]["keyids"]))
            for role in ("targets", "snapshot", "timestamp"):
                lines.append(f"  {role.ljust(9)} key {signed['roles'][role]['keyids'][0][:16]}")
            lines.append("  expires " + signed["expires"] + "   (put the renewal date in a calendar, 90 days before)")
        if solo_note:
            lines += ["", *solo_note.rstrip().splitlines()]
        lines += ["", "WHAT TO DO WITH EACH STICK AND FILE",
                  "  Holder sticks     Each holder keeps their own stick in their own place: home, off-site, a trusted person (D-010).",
                  "                    The stick is the only copy of the private key. Never copy root.key anywhere else.",
                  "  Passphrases       Each holder keeps their own safe. Never in the repo, chat or email.",
                  "  Transfer stick    First carry out ONLY the public file(s): " + ", ".join(f"out-{c}/root.json" for c in self.channels) + ". Check",
                  "                    on the online computer that `shasum -a 256 root.json` matches the sha256 above (CEREMONY.md step 8).",
                  "  Online keys       online/*.key are PRIVATE. They go into the GitHub Environment tuf-signing (CEREMONY.md step 9) and",
                  "                    ride on the transfer stick only for that step; then wipe the stick and this computer (shut the live USB down).",
                  "                    Never put a holder's root.key on the transfer stick.",
                  "  Next              Commit root.json under os/rootfs/layers/base/usr/lib/onemind/tuf/<channel>/ in a PR (CEREMONY.md step 9).",
                  "=" * 70]
        text = "\n".join(lines)
        io.say(text)
        with open(os.open(os.path.join(self.work, "SHEET.txt"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
            f.write(text + "\n")
        io.say(f"(the sheet is also saved in {os.path.join(self.work, 'SHEET.txt')}; it has public values only)")

    def release_proof(self):
        """Rehearsal only: the existing rehearsal signs a test release and checks it as a box would."""
        d = os.path.join(self.work, "release-proof")
        if os.path.exists(d):
            shutil.rmtree(d)
        if self.run_script("rehearse", d, capture=True, quiet=True) != 0:
            raise Stop("the release proof (a signed test release checked as a box would) FAILED.")

    # ---- the whole walk ----
    def run(self):
        io = self.io
        os.makedirs(self.work, mode=0o700, exist_ok=True)
        os.chmod(self.work, 0o700)
        io.open_log(os.path.join(self.work, "guide.log"))
        io.say(NEEDS)
        if self.rehearsal:
            io.say("REHEARSAL: throwaway keys in " + self.work + ". Nothing here is ever used for real.\n")
        if self.solo:
            io.say(SOLO_WARNING, err=True)
        if self.load_state():
            io.say("Resuming an earlier run: finished steps are skipped.\n")
        else:
            io.pause("Press Enter to begin")
        self.preflight()          # every run, including a resume: the network must be off NOW
        self.save()
        self.step("holders", self.holders)
        self.step("keys", self.keys)
        self.step("online", self.online_keys)
        self.step("signers", self.signers)
        self.step("sign", self.sign)
        self.step("sheet", self.verify_and_sheet)
        if self.rehearsal:
            self.step("release-proof", self.release_proof)
            io.say(f"\n== REHEARSAL PASSED: guided 3-holder walk, 2-of-3 root, online keys, a signed release verified. Delete {self.work}.")
        else:
            io.say("\nCEREMONY COMPLETE. Thank you. Follow the list above, then wipe this computer.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Guided root-key ceremony (D-010). Run it on the offline machine.")
    ap.add_argument("--rehearsal", action="store_true", help="throwaway keys in a temp directory; ends with REHEARSAL PASSED")
    ap.add_argument("--work", help="work folder outside the repo (resume by giving the same one again); default: a new temp folder")
    ap.add_argument("--channel", action="append", help="update channel to make a root for (repeatable; default: security)")
    ap.add_argument("--expect-commit", help="commit hash from your checklist (otherwise you are asked to type it)")
    ap.add_argument(SOLO_FLAG, dest="solo", action="store_true",
                    help="ONE person does all three holders' parts. NOT what D-010 requires: the founder must accept it")
    ap.add_argument("--stop-after", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    io = Io(auto=a.rehearsal)
    try:
        if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
            raise Stop("refusing: a root key is made by people, offline, never in CI.")
        if a.solo and a.rehearsal:
            raise Stop("--rehearsal already uses three throwaway holders; do not combine it with the solo flag.")
        if os.environ.get(PASSPHRASE_ENV) and not a.rehearsal:
            raise Stop(f"{PASSPHRASE_ENV} is set in this shell. A real passphrase is typed, never kept in the environment: unset it and run again.")
        if not a.rehearsal and not (sys.stdin.isatty() and sys.stdout.isatty()):
            raise Stop("the real ceremony needs a person at a terminal (passphrases are typed at no-echo prompts).")
        work = a.work or os.path.join(tempfile.mkdtemp(prefix="onemind-ceremony-"), "work")
        Guide(io, work, rehearsal=a.rehearsal, solo=a.solo, channels=a.channel or ["security"],
              expect_commit=a.expect_commit, stop_after=a.stop_after).run()
    except Stop as e:
        io.say(f"\nSTOP: {e}", err=True)
        return 1
    except KeyboardInterrupt:
        io.say("\nInterrupted. Run the guide again with the same --work folder to continue; nothing unsafe is left behind.", err=True)
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
