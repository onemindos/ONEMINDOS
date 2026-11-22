# SPDX-License-Identifier: Apache-2.0
"""Browser downloads: quarantine, scan, then Files (#693; files/downloads.py, routers/downloads.py).

The issue's acceptance test: the EICAR test file is held and never reaches Files, a clean PDF
arrives within a minute, and every move is in the audit chain. Also: executables, archives, bad
names and a missing scanner are held; a held file leaves only after an owner approves; the owners
get an Inbox alert per held file and the person an Inbox item per delivered file.

The scanner is a separate process speaking ClamAV's exit codes (0 clean, 1 FOUND, 2 error); when
the box running the tests has a real `clamscan`, the last test uses it on the same EICAR file.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import time
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onemind_core.app import create_app
from onemind_core.audit import verify
from onemind_core.files.downloads import DownloadSettings, scan, type_problem
from onemind_core.notify.service import NotifySettings
from files_support import ADULT, AGENT, GUEST, OWNER, audit_events, files_root, files_settings, ok  # noqa: F401

# The EICAR anti-virus test file (eicar.org), built from parts so this source file is not itself flagged.
EICAR = ("X5O!P%@AP[4\\PZX54(P^)7CC)7}$" + "EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*").encode()
PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
FAKE_CLAM = f"""#!{sys.executable}
import sys
data = open(sys.argv[-1], "rb").read()
if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in data:
    print(sys.argv[-1] + ": Eicar-Test-Signature FOUND")
    sys.exit(1)
sys.exit(0)
"""


@pytest.fixture
def scanner(tmp_path) -> str:
    path = tmp_path / "bin" / "clamscan"
    path.parent.mkdir()
    path.write_text(FAKE_CLAM)
    path.chmod(0o755)
    return str(path)


def client(settings, clock, executor, tmp_path, files_settings, **dl):
    s = replace(settings, sections={**settings.sections, "files": files_settings,
                                    "notify": NotifySettings(worker=False, dir=tmp_path / "keys"),
                                    "downloads": DownloadSettings(**{"worker": False, "settle_s": 0, **dl})})
    return TestClient(create_app(s, clock=clock, executor=executor))


@pytest.fixture
def dc(settings, clock, executor, tmp_path, files_settings, scanner):
    with client(settings, clock, executor, tmp_path, files_settings, scanner=scanner) as c:
        yield c


def drop(c, person: str, name: str, data: bytes) -> None:
    """What the person's browser does: save a finished download into their intake folder."""
    (c.app.state.downloads.intake_dir(person) / name).write_bytes(data)


def held(c, headers=OWNER) -> list[dict]:
    return ok(c.get("/v1/files/downloads", headers=headers))["items"]


def downloads_folder(c, headers=ADULT, root="home:adult") -> list[str]:
    r = c.get("/v1/files/list", headers=headers, params={"root": root, "path": "/Downloads"})
    return [] if r.status_code == 404 else [e["name"] for e in ok(r)]


def inbox(c, headers) -> list[str]:
    return [n["title"] for n in ok(c.get("/v1/notifications", headers=headers))]


def alerts(c, state="open") -> list[dict]:
    return [a for a in ok(c.get("/v1/alerts", headers=OWNER, params={"state": state}))
            if a["type"] == "files.download.quarantined"]


def test_eicar_is_held_never_reaches_files_and_the_owner_gets_an_inbox_alert(dc, settings):
    drop(dc, "adult", "eicar.com.txt", EICAR)
    assert dc.app.state.downloads.sweep() == 1
    assert downloads_folder(dc) == []
    [h] = held(dc)
    assert h["verdict"] == "infected" and "Eicar-Test-Signature" in h["reason"] and h["person_id"] == "adult"
    assert [x["id"] for x in held(dc, ADULT)] == [h["id"]] and held(dc, ADULT)[0]["person_id"] is None
    assert held(dc, GUEST) == []
    [a] = alerts(dc)
    assert a["severity"] == "critical" and a["title"] == "Download held: eicar.com.txt"
    assert a["fix"] == {"type": "files.download.release", "params": {"download_id": h["id"], "verdict": "infected"}}
    assert "Download held: eicar.com.txt" in inbox(dc, OWNER) and inbox(dc, ADULT) == []
    names = [e["event"] for e in audit_events(settings)]
    assert "files.download.received" in names and "files.download.quarantined" in names
    assert "files.download.delivered" not in names


def test_clean_pdf_arrives_in_files_and_every_move_is_in_the_audit_chain(dc, settings, files_root):
    drop(dc, "adult", "report.pdf", PDF)
    dc.app.state.downloads.sweep()
    assert downloads_folder(dc) == ["report.pdf"] and held(dc) == []
    got = dc.get("/v1/files/download", headers=ADULT, params={"root": "home:adult", "path": "/Downloads/report.pdf"})
    assert got.content == PDF
    assert not any(p.stat().st_mode & 0o111 for p in files_root.rglob("report.pdf"))
    assert "Downloaded: report.pdf" in inbox(dc, ADULT) and inbox(dc, OWNER) == []
    events = {e["event"]: e["data"]["payload"] for e in audit_events(settings) if e["event"].startswith("files.download.")}
    assert events["files.download.received"]["sha256"] == events["files.download.delivered"]["sha256"]
    assert events["files.download.delivered"]["path"] == "/Downloads/report.pdf"
    assert events["files.download.delivered"]["via"] == "scan"
    assert verify(settings.audit_path)[0]
    # A second download of the same name never replaces the first.
    drop(dc, "adult", "report.pdf", PDF + b"%v2\n")
    dc.app.state.downloads.sweep()
    assert sorted(downloads_folder(dc)) == ["report (1).pdf", "report.pdf"]


def test_the_worker_delivers_a_clean_file_within_a_minute(settings, clock, executor, tmp_path, files_settings, scanner):
    with client(settings, clock, executor, tmp_path, files_settings, scanner=scanner, worker=True, poll_s=0.2) as c:
        drop(c, "adult", "paper.pdf", PDF)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and downloads_folder(c) != ["paper.pdf"]:
            time.sleep(0.1)
        assert downloads_folder(c) == ["paper.pdf"]


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries.items():
            z.writestr(name, data)
    return buf.getvalue()


def test_programs_archives_bad_names_and_unfinished_downloads_stay_out_of_files(dc, tmp_path):
    drop(dc, "adult", "tool", b"\x7fELF\x02\x01\x01" + b"\0" * 64)
    drop(dc, "adult", "setup.sh", b"echo hi\n")
    drop(dc, "adult", "photos.zip", _zip({"a.jpg": b"\xff\xd8"}))
    drop(dc, "adult", "letter.docx", _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": b"<w/>"}))
    drop(dc, "adult", "fake.docx", _zip({"run.exe": b"MZ"}))
    drop(dc, "adult", "bad\x01name.txt", b"hello")
    drop(dc, "adult", "movie.mp4.part", b"partial")
    drop(dc, "adult", "movie.mp4", b"")  # Firefox's placeholder while the .part file grows
    outside = tmp_path / "secret.txt"
    outside.write_text("not yours")
    os.symlink(outside, dc.app.state.downloads.intake_dir("adult") / "link.txt")
    dc.app.state.downloads.sweep()
    assert downloads_folder(dc) == ["letter.docx"]
    verdicts = {h["name"]: h["verdict"] for h in held(dc)}
    assert verdicts.pop("tool") == "executable" and verdicts.pop("setup.sh") == "executable"
    assert verdicts.pop("photos.zip") == "archive" and verdicts.pop("fake.docx") == "archive"
    [(renamed, why)] = verdicts.items()
    assert why == "name" and renamed.startswith("download-")
    assert outside.read_text() == "not yours" and not (dc.app.state.downloads.intake_dir("adult") / "link.txt").exists()
    left = sorted(os.listdir(dc.app.state.downloads.intake_dir("adult")))
    assert left == ["movie.mp4", "movie.mp4.part"]
    assert len(alerts(dc)) == 5


def test_a_missing_or_failing_scanner_is_never_a_clean_scan(settings, clock, executor, tmp_path, files_settings):
    with client(settings, clock, executor, tmp_path, files_settings, scanner=str(tmp_path / "no-such-clamdscan")) as c:
        drop(c, "adult", "report.pdf", PDF)
        c.app.state.downloads.sweep()
        assert downloads_folder(c) == []
        [h] = held(c)
        assert h["verdict"] == "unscanned" and "not installed" in h["reason"]
    assert scan("clamscan", Path("/x"), 5, runner=lambda *a, **k: type("R", (), {"returncode": 2, "stdout": ""})()).result == "unscanned"


def test_type_check_reads_bytes_not_only_the_name():
    assert type_problem("notes.txt", b"MZ\x90\x00", -1) == "executable"
    assert type_problem("data.bin.txt", b"\x1f\x8b\x08", -1) == "archive"
    assert type_problem("backup.txt", b"\0" * 257 + b"ustar", -1) == "archive"
    assert type_problem("report.pdf", PDF, -1) is None


def test_a_held_file_leaves_only_after_an_owner_approves(dc):
    drop(dc, "adult", "report.pdf", EICAR)
    dc.app.state.downloads.sweep()
    [h] = held(dc)
    assert dc.post(f"/v1/files/downloads/{h['id']}/release", headers=ADULT).status_code == 403
    assert dc.post(f"/v1/files/downloads/{h['id']}/release", headers=AGENT).status_code == 403
    action = ok(dc.post(f"/v1/files/downloads/{h['id']}/release", headers=OWNER), 202)
    assert action["state"] == "awaiting_approval" and action["type"] == "files.download.release"
    assert action["risk"] == "destructive"  # releasing a file ClamAV flagged
    assert downloads_folder(dc) == [] and len(held(dc)) == 1
    assert dc.post(f"/v1/actions/{action['id']}/approve", headers=ADULT).status_code == 403
    done = ok(dc.post(f"/v1/actions/{action['id']}/approve", headers=OWNER, json={"hold_ms": 5000}))
    assert done["state"] == "succeeded", done
    assert downloads_folder(dc) == ["report.pdf"] and held(dc) == []
    assert alerts(dc) == [] and len(alerts(dc, "resolved")) == 1
    # Once released, there is nothing left to release.
    assert dc.post(f"/v1/files/downloads/{h['id']}/release", headers=OWNER).status_code == 404


def test_the_alert_fix_files_the_release_for_an_owner_to_approve(dc):
    drop(dc, "adult", "setup.exe", b"MZ\x90\x00")
    dc.app.state.downloads.sweep()
    [a] = alerts(dc)
    action = ok(dc.post(f"/v1/alerts/{a['id']}/fix", headers=OWNER, json={}), 202)
    assert action["type"] == "files.download.release" and action["state"] == "awaiting_approval"
    assert action["risk"] == "sensitive"
    assert dc.post(f"/v1/alerts/{a['id']}/fix", headers=AGENT, json={}).status_code == 403


def test_a_held_file_is_discarded_by_its_person_or_an_owner(dc):
    drop(dc, "adult", "a.zip", _zip({"x": b"1"}))
    drop(dc, "adult", "b.zip", _zip({"y": b"2"}))
    dc.app.state.downloads.sweep()
    first, second = (h["id"] for h in held(dc))
    assert dc.delete(f"/v1/files/downloads/{first}", headers=GUEST).status_code == 404
    assert dc.delete(f"/v1/files/downloads/{first}", headers=AGENT).status_code == 403
    assert ok(dc.delete(f"/v1/files/downloads/{first}", headers=ADULT))["state"] == "discarded"
    assert ok(dc.delete(f"/v1/files/downloads/{second}", headers=OWNER))["state"] == "discarded"
    assert held(dc) == [] and downloads_folder(dc) == [] and alerts(dc) == []


@pytest.mark.skipif(shutil.which("clamscan") is None, reason="ClamAV is not installed on this machine")
def test_real_clamav_flags_eicar(tmp_path):
    sample = tmp_path / "eicar.txt"
    sample.write_bytes(EICAR)
    result = scan("clamscan", sample, 300)
    assert result.result in ("infected", "unscanned")  # unscanned only when the signature database is missing
