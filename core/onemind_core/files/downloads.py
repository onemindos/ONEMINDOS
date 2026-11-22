# SPDX-License-Identifier: Apache-2.0
"""Browser downloads: quarantine, scan, then Files (#693).

A file a person downloads in their browser lands in their intake folder
`<files root>/.system/downloads/<space dir>/incoming/`, outside every space, so Files never shows
it and no app reads it. The worker here, once the file has stopped changing:

1. moves it into `held/` under a random id (so the browser cannot change it any more) and makes it
   not executable; a symbolic link is removed, never followed;
2. checks the name (a name Files would refuse, such as one with a control character, is replaced),
   the type by its first bytes and its extension (executables and archives are held, as the app
   gate holds them), and scans it with ClamAV as a separate process (`clamdscan`, configurable);
3. a clean file of an allowed type moves into the person's Home `Downloads/` folder (never over an
   existing file) and the person gets an Inbox item; anything else stays held and the owners get an
   alert in their Inbox (notify/catalogue.py `files.download.quarantined`).

A held file leaves quarantine only through `files.download.release`, an action an owner requests
(the alert's fix, or POST /v1/files/downloads/{id}/release) and an owner approves. Releasing an
infected file is a destructive-risk approval. A scanner that is missing or fails is never a clean
scan: the file is held. Nothing here opens or runs a downloaded file. Every move is an event, so it
is in the audit chain.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import stat as stat_mod
import subprocess
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from ..auth import Principal
from ..executors import ExecResult
from ..ledger import iso
from ..sections import config_section
from . import paths
from .access import Root
from .errors import FilesError, denied, not_found
from .service import SYSTEM_DIR, FilesService, _ensure_dir

log = logging.getLogger("onemind.files.downloads")

DOWNLOADS, INCOMING, HELD = "downloads", "incoming", "held"
DEST = "Downloads"                # the folder in the person's Home
RELEASE_ACTION = "files.download.release"
ID_RE = re.compile(r"^dl_[0-9a-f]{24}$")
VERDICTS = ("clean", "infected", "name", "executable", "archive", "unscanned")
PARTIAL = (".part", ".crdownload", ".download", ".partial", ".tmp")  # Firefox, Chromium, Safari, others
READ_CHUNK = 1024 * 1024

EXECUTABLE_EXT = frozenset({
    "exe", "dll", "msi", "msix", "com", "scr", "bat", "cmd", "ps1", "vbs", "vbe", "wsf", "hta", "lnk", "jar",
    "sh", "bash", "zsh", "run", "bin", "elf", "so", "appimage", "deb", "rpm", "apk", "snap", "flatpak",
    "app", "dmg", "pkg", "command", "desktop", "iso", "img",
})
ARCHIVE_EXT = frozenset({"zip", "tar", "gz", "tgz", "bz2", "tbz2", "xz", "txz", "7z", "rar", "zst", "cab", "lz", "lzma"})
# Office and e-book formats are zip containers; they pass when they carry their format's marker.
DOC_ZIP = {"docx": "[Content_Types].xml", "xlsx": "[Content_Types].xml", "pptx": "[Content_Types].xml",
           "odt": "mimetype", "ods": "mimetype", "odp": "mimetype", "epub": "mimetype"}
_EXEC_MAGIC = (b"\x7fELF", b"MZ", b"#!", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe",
               b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\x00asm")
_ARCHIVE_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08", b"\x1f\x8b", b"BZh", b"\xfd7zXZ\x00",
                  b"7z\xbc\xaf\x27\x1c", b"Rar!\x1a\x07", b"\x28\xb5\x2f\xfd", b"MSCF", b"LZIP")


@config_section("downloads")
@dataclass(frozen=True)
class DownloadSettings:
    worker: bool = True               # ONEMIND_DOWNLOADS_WORKER: run the quarantine worker thread
    poll_s: float = 10.0              # ONEMIND_DOWNLOADS_POLL_S: a clean file reaches Files well within a minute
    settle_s: float = 3.0             # ONEMIND_DOWNLOADS_SETTLE_S: unchanged this long = the download finished
    scanner: str = "clamdscan"        # ONEMIND_DOWNLOADS_SCANNER: clamdscan (clamd) or clamscan, by path or name
    scan_timeout_s: float = 300.0     # ONEMIND_DOWNLOADS_SCAN_TIMEOUT_S

    def validate(self) -> None:
        if self.poll_s <= 0 or self.settle_s < 0 or self.scan_timeout_s <= 0:
            raise ValueError("ONEMIND_DOWNLOADS_POLL_S and _SCAN_TIMEOUT_S must be positive, _SETTLE_S not negative")
        if not self.scanner.strip():
            raise ValueError("ONEMIND_DOWNLOADS_SCANNER must name the ClamAV scanner")


def type_problem(name: str, head: bytes, fd: int) -> str | None:
    """"executable" or "archive" when the type check holds the file, else None (by bytes, then name)."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name.strip(".") else ""
    if head.startswith(_EXEC_MAGIC) or ext in EXECUTABLE_EXT:
        return "executable"
    is_zip = head.startswith(_ARCHIVE_MAGIC[:3])
    if ext in DOC_ZIP and is_zip:
        try:
            with os.fdopen(os.dup(fd), "rb") as f, zipfile.ZipFile(f) as z:  # reads the directory only
                names = z.namelist()
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
            return "archive"
        bad = any(n.rsplit(".", 1)[-1].lower() in EXECUTABLE_EXT | ARCHIVE_EXT for n in names if "." in n)
        return None if DOC_ZIP[ext] in names and not bad else "archive"
    if head.startswith(_ARCHIVE_MAGIC) or head[257:262] == b"ustar" or ext in ARCHIVE_EXT:
        return "archive"
    return None


@dataclass(frozen=True)
class ScanResult:
    result: str      # clean | infected | unscanned
    detail: str = ""


def scan(scanner: str, path: Path, timeout_s: float, runner: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> ScanResult:
    """ClamAV in its own process. Exit 0 = clean, 1 = found (signature in stdout), anything else = not scanned."""
    args = [scanner, "--no-summary", *(["--fdpass"] if Path(scanner).name.startswith("clamdscan") else []), str(path)]
    try:
        cp = runner(args, capture_output=True, text=True, timeout=timeout_s, check=False)
    except FileNotFoundError:
        return ScanResult("unscanned", "The virus scanner (ClamAV) is not installed on this box, so the file was not scanned.")
    except (OSError, subprocess.SubprocessError) as exc:
        return ScanResult("unscanned", f"The virus scanner did not finish ({exc.__class__.__name__}).")
    if cp.returncode == 0:
        return ScanResult("clean")
    if cp.returncode == 1:
        m = re.search(r":\s*(\S+)\s+FOUND\s*$", cp.stdout or "", re.M)
        return ScanResult("infected", m.group(1)[:120] if m else "malware")
    return ScanResult("unscanned", "The virus scanner reported an error, so the file was not scanned.")


@dataclass
class Held:
    id: str
    person_id: str
    name: str
    size: int
    sha256: str
    verdict: str
    reason: str
    received_at: str

    def public(self, owner: bool) -> dict:
        out = {k: v for k, v in asdict(self).items() if k != "person_id" or owner}
        out["state"] = "waiting_for_space" if self.verdict == "clean" else "held"
        return out


def _reason(verdict: str, detail: str) -> str:
    return {
        "infected": f"ClamAV found {detail}.",
        "name": "The file name is not allowed in Files (a slash, control character or similar), so it was renamed.",
        "executable": "It is a program or installer, which OneMind never opens or runs from a download.",
        "archive": "It is an archive, whose contents a scan cannot fully vouch for.",
        "unscanned": detail,
    }.get(verdict, detail)


def _candidates(name: str) -> list[str]:
    stem, dot, ext = name.rpartition(".") if "." in name.strip(".") else (name, "", "")
    return [name] + [f"{stem} ({i}){dot}{ext}" for i in range(1, 1000)]


class Downloads:
    def __init__(self, files: FilesService, settings: DownloadSettings,
                 runner: Callable[..., subprocess.CompletedProcess] = subprocess.run):
        self.files, self.gw, self.cfg, self.runner = files, files.gw, settings, runner
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- the worker ----------------------------------------------------------------------------
    async def start(self) -> None:
        if self.cfg.worker:
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="downloads-quarantine", daemon=True)
            self._thread.start()

    async def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sweep()
            except Exception:
                log.exception("download quarantine pass failed")
            self._stop.wait(self.cfg.poll_s)

    def intake_dir(self, person_id: str) -> Path:
        """Create (as the gateway's user) and return a person's intake folder: where their browser saves."""
        name = self.files.space_dir_name(person_id)
        with self.files._system(DOWNLOADS, name) as fd:
            os.close(_ensure_dir(fd, INCOMING, 0o700))
            os.close(_ensure_dir(fd, HELD, 0o700))
        return self.files.settings.root / SYSTEM_DIR / DOWNLOADS / name / INCOMING

    def _people_dirs(self) -> list[tuple[str, str]]:
        spaces = self.files.repo.spaces()
        root = self.files.settings.root / SYSTEM_DIR / DOWNLOADS
        try:
            present = set(os.listdir(root))
        except OSError:
            return []
        return [(pid, d) for pid, d in spaces.items() if d in present]

    def sweep(self) -> int:
        """One pass over every person's intake folder; returns the files taken in or delivered."""
        done = 0
        for person_id, dir_name in self._people_dirs():
            with self._lock, self.files._system(DOWNLOADS, dir_name) as top:
                held = _ensure_dir(top, HELD, 0o700)
                try:
                    done += self._take_in(person_id, top, held)
                    for rec in self._records(held):  # clean files that waited for space in Files
                        if rec.verdict == "clean" and self._deliver(rec, held, via="scan", quiet=True):
                            done += 1
                finally:
                    os.close(held)
        return done

    def _take_in(self, person_id: str, top: int, held: int) -> int:
        try:
            inc = os.open(INCOMING, paths.O_DIR, dir_fd=top)
        except OSError:
            return 0
        n = 0
        try:
            names = os.listdir(inc)
            for name in names:
                if name.endswith(PARTIAL) or f"{name}.part" in names:
                    continue
                try:
                    st = os.stat(name, dir_fd=inc, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                if stat_mod.S_ISLNK(st.st_mode):  # never followed: removed, and the attempt is audited
                    os.unlink(name, dir_fd=inc)
                    self._event("download.refused", {"person_id": person_id, "reason": "symlink"}, "warning")
                    continue
                if not stat_mod.S_ISREG(st.st_mode) or time.time() - max(st.st_mtime, st.st_ctime) < self.cfg.settle_s:
                    continue
                self._process(person_id, inc, held, name)
                n += 1
        finally:
            os.close(inc)
        return n

    def _process(self, person_id: str, inc: int, held: int, name: str) -> None:
        did = "dl_" + secrets.token_hex(12)
        os.rename(name, did + ".bin", src_dir_fd=inc, dst_dir_fd=held)
        fd = os.open(did + ".bin", os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=held)
        try:
            os.fchmod(fd, 0o640)  # a download is never executable
            h, size, head = hashlib.sha256(), 0, b""
            while chunk := os.read(fd, READ_CHUNK):
                if len(head) < 512:
                    head += chunk[: 512 - len(head)]
                h.update(chunk)
                size += len(chunk)
            kind = type_problem(name, head, fd)
        finally:
            os.close(fd)
        try:
            safe = paths.validate_name(name)
        except FilesError:
            safe = None
        self._event("download.received", {"download_id": did, "person_id": person_id, "name": safe or "?",
                                          "size": size, "sha256": h.hexdigest()})
        result = scan(self.cfg.scanner, self._host_path(person_id, did), self.cfg.scan_timeout_s, self.runner)
        if result.result == "infected":
            verdict = "infected"
        elif safe is None:
            verdict = "name"
        elif kind is not None:
            verdict = kind
        else:
            verdict = result.result
        rec = Held(id=did, person_id=person_id, name=safe or f"download-{did[3:11]}", size=size, sha256=h.hexdigest(),
                   verdict=verdict, reason=_reason(verdict, result.detail), received_at=iso(self.files.clock()) or "")
        self._save(held, rec)
        if verdict == "clean":
            self._deliver(rec, held, via="scan")
            return
        severity = "critical" if verdict == "infected" else "warning"
        self._event("download.quarantined", {
            "download_id": did, "person_id": person_id, "name": rec.name, "size": size, "sha256": rec.sha256,
            "verdict": verdict, "reason": rec.reason, "scan": result.result, "severity": severity,
        }, severity)

    def _host_path(self, person_id: str, did: str) -> Path:
        name = self.files.space_dir_name(person_id)
        return self.files.settings.root / SYSTEM_DIR / DOWNLOADS / name / HELD / f"{did}.bin"

    # ---- records -------------------------------------------------------------------------------
    @staticmethod
    def _save(held: int, rec: Held) -> None:
        tmp = f".{rec.id}.{secrets.token_hex(4)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=held)
        with os.fdopen(fd, "w") as f:
            json.dump(asdict(rec), f)
        os.rename(tmp, f"{rec.id}.json", src_dir_fd=held, dst_dir_fd=held)

    @staticmethod
    def _records(held: int) -> list[Held]:
        out = []
        for name in sorted(os.listdir(held)):
            if not name.endswith(".json") or not ID_RE.match(name[:-5]):
                continue
            try:
                fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=held)
                with os.fdopen(fd) as f:
                    out.append(Held(**json.load(f)))
            except (OSError, ValueError, TypeError):
                log.warning("unreadable quarantine record %s", name)
        return out

    def _find(self, download_id: str) -> tuple[Held, str] | None:
        if not ID_RE.match(download_id or ""):
            return None
        for _pid, dir_name in self._people_dirs():
            with self.files._system(DOWNLOADS, dir_name) as top:
                held = _ensure_dir(top, HELD, 0o700)
                try:
                    hit = [r for r in self._records(held) if r.id == download_id]
                finally:
                    os.close(held)
            if hit:
                return hit[0], dir_name
        return None

    # ---- leaving quarantine --------------------------------------------------------------------
    def _deliver(self, rec: Held, held: int, *, via: str, action_id: str | None = None, quiet: bool = False) -> str | None:
        """Move the file into Home/Downloads (never over another file). Returns its path, or None
        when Files has no room (quiet: the record waits for the next pass)."""
        root = Root("home", rec.person_id)
        with self.files._lock:
            try:
                self.files.check_space(root, rec.size)
            except FilesError as exc:
                if not quiet and via == "approval":
                    raise
                if rec.reason != exc.message:
                    rec.reason = exc.message
                    self._save(held, rec)
                return None
            with self.files._space(root) as space:
                dest = _ensure_dir(space, DEST)
                try:
                    for final in _candidates(rec.name):
                        try:
                            os.link(f"{rec.id}.bin", final, src_dir_fd=held, dst_dir_fd=dest)
                            break
                        except FileExistsError:
                            continue
                    else:
                        raise FilesError(409, "conflict", "Downloads has too many files with this name", reason="exists")
                    os.unlink(f"{rec.id}.bin", dir_fd=held)
                    os.fsync(dest)
                finally:
                    os.close(dest)
        os.unlink(f"{rec.id}.json", dir_fd=held)
        path = paths.join((DEST, final))
        self.files.reindex(root, (DEST, final), depth=0, known_hash="sha256:" + rec.sha256)
        self._event("download.delivered", {
            "download_id": rec.id, "person_id": rec.person_id, "name": final, "root": root.id, "path": path,
            "size": rec.size, "sha256": rec.sha256, "via": via, "verdict": rec.verdict,
            **({"action_id": action_id} if action_id else {}),
        })
        return path

    def _event(self, name: str, payload: dict, severity: str = "info") -> None:
        self.gw.events.publish_event("files", name, payload, severity=severity,
                                     resource={"kind": "download", "id": payload.get("download_id") or "downloads"})

    # ---- API -----------------------------------------------------------------------------------
    def list(self, p: Principal) -> list[dict]:
        out = []
        for pid, dir_name in self._people_dirs():
            if not (p.is_owner or pid == p.id):
                continue
            with self.files._system(DOWNLOADS, dir_name) as top:
                held = _ensure_dir(top, HELD, 0o700)
                try:
                    out += [r.public(p.is_owner) for r in self._records(held)]
                finally:
                    os.close(held)
        return sorted(out, key=lambda r: r["received_at"])

    def get(self, p: Principal, download_id: str) -> Held:
        found = self._find(download_id)
        if found is None or not (p.is_owner or found[0].person_id == p.id):
            raise not_found("no such held download")
        return found[0]

    def discard(self, p: Principal, download_id: str) -> dict:
        """Delete a held file for good: its owner (the person who downloaded it) or an owner."""
        if p.kind != "person":
            raise denied("only a person discards a held download", "role")
        with self._lock:
            rec = self.get(p, download_id)
            with self.files._system(DOWNLOADS, self.files.space_dir_name(rec.person_id), HELD) as held:
                for suffix in (".bin", ".json"):
                    try:
                        os.unlink(rec.id + suffix, dir_fd=held)
                    except FileNotFoundError:
                        pass
        self.gw.events.publish_event("files", "download.discarded", {
            "download_id": rec.id, "person_id": rec.person_id, "name": rec.name, "sha256": rec.sha256,
            "verdict": rec.verdict}, principal=p.as_dict(), resource={"kind": "download", "id": rec.id})
        return {"id": rec.id, "state": "discarded"}

    # ---- files.download.release (owner-approved) -----------------------------------------------
    def check_release(self, action) -> str | None:
        found = self._find(str(action.params.get("download_id")))
        if found is None:
            return "the download was already released or discarded"
        if found[0].verdict != action.params.get("verdict"):
            return "the download's scan result changed; ask again"
        return None

    def run_release(self, action, finish: Callable[[ExecResult], None]) -> None:
        with self._lock:
            problem = self.check_release(action)
            if problem:
                finish(ExecResult("failed", problem))
                return
            rec, dir_name = self._find(action.params["download_id"])
            try:
                with self.files._system(DOWNLOADS, dir_name, HELD) as held:
                    path = self._deliver(rec, held, via="approval", action_id=action.id)
            except FilesError as exc:
                finish(ExecResult("failed", f"the file stays in quarantine: {exc.message}"))
                return
        finish(ExecResult("succeeded", f"moved to {path} in the person's Files"))
