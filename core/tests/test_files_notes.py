# SPDX-License-Identifier: Apache-2.0
"""The Notes vault uses real Files storage and the principal's own home."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import UUID

import pytest

from onemind_core.auth import Principal
from onemind_core.files import notes
from onemind_core.files.errors import FilesError
from onemind_core.files.notes import MAX_NOTE_BYTES, NotesVault
from onemind_core.files.notes_index import NotesIndex, wikilinks

from files_support import fc, files_root, files_settings  # noqa: F401 (pytest fixtures)

PERSON = Principal("notes-person", "person", "owner")
OTHER = Principal("other-person", "person", "adult")


@pytest.fixture
def vault(fc):
    return NotesVault(fc.app.state.files_service)


def test_two_devices_keep_original_and_reuse_conflict_copy(vault):
    base = vault.save(PERSON, "Plans.md", "first\n", revision=None).note
    with ThreadPoolExecutor(max_workers=2) as pool:
        writes = [pool.submit(vault.save, PERSON, base.path, text, revision=base.revision)
                  for text in ("phone edit\n", "desktop edit\n")]
        original, copy = sorted((write.result() for write in writes), key=lambda result: result.conflict)
    assert not original.conflict and copy.conflict
    assert {result.note.markdown for result in (original, copy)} == {"phone edit\n", "desktop edit\n"}
    assert vault.get(PERSON, base.path) == original.note
    assert vault.get(PERSON, copy.note.path) == copy.note
    assert vault.save(PERSON, base.path, copy.note.markdown, revision=base.revision) == copy


def test_external_edit_becomes_original_and_obsidian_config_survives(vault, files_root):
    note = vault.save(PERSON, "Ideas.md", "# Ideas\n", revision=None).note
    directory = files_root / vault.files.share_folder("home", PERSON.id) / "Notes"
    (directory / ".obsidian").mkdir()
    config = directory / ".obsidian" / "app.json"
    config.write_text('{"showLineNumber":true}')
    (directory / "Ideas.md").write_text("# Edited in Obsidian\n")
    saved = vault.save(PERSON, note.path, "# Edited offline\n", revision=note.revision)
    assert saved.conflict
    assert (directory / "Ideas.md").read_text() == "# Edited in Obsidian\n"
    assert config.read_text() == '{"showLineNumber":true}'
    with pytest.raises(FilesError) as exc:
        vault.save(PERSON, ".obsidian/hidden.md", "must not write", revision=None)
    assert exc.value.reason == "invalid_path"
    assert {entry.name for entry in config.parent.iterdir()} == {"app.json"}


def test_symlinks_are_not_read_or_written(vault, files_root, tmp_path):
    vault.daily(PERSON, date(2026, 1, 2))
    directory = files_root / vault.files.share_folder("home", PERSON.id) / "Notes"
    outside = tmp_path / "outside.md"
    outside.write_text("leave intact")
    (directory / "external.md").symlink_to(outside)
    (directory / "external-folder").symlink_to(tmp_path)
    for path in ("external.md", "external-folder/outside.md"):
        with pytest.raises(FilesError) as read:
            vault.get(PERSON, path)
        with pytest.raises(FilesError) as write:
            vault.save(PERSON, path, "overwrite", revision=None)
        assert read.value.reason == write.value.reason == "symlink"
    assert outside.read_text() == "leave intact"


def test_home_is_private_and_agents_cannot_save(vault):
    first = vault.save(PERSON, "Only Mine.md", "one", revision=None).note
    with pytest.raises(FilesError) as exc:
        vault.get(OTHER, first.path)
    assert exc.value.status == 404
    other = vault.save(OTHER, first.path, "another", revision=None)
    assert other.note.markdown == "another" and not other.conflict
    assert vault.get(PERSON, first.path) == first
    for kind, role in (("agent", "owner"), ("person", "guest"), ("app", "owner")):
        with pytest.raises(FilesError) as exc:
            vault.save(Principal(PERSON.id, kind, role), first.path, "overwrite", revision=first.revision)
        assert exc.value.status == 403


def test_daily_is_create_only_and_notes_enforce_limits(vault):
    day = date(2026, 1, 2)
    daily = vault.daily(PERSON, day)
    assert (daily.path, daily.markdown) == ("/2026-01-02.md", "# 2026-01-02\n")
    edited = vault.save(PERSON, daily.path, "Some work", revision=daily.revision).note
    assert vault.daily(PERSON, day) == edited
    with pytest.raises(FilesError) as exc:
        vault.save(PERSON, "large.md", "x" * (MAX_NOTE_BYTES + 1), revision=None)
    assert exc.value.reason == "note_too_large"
    with pytest.raises(FilesError) as exc:
        vault.save(PERSON, "../away.md", "x", revision=None)
    assert exc.value.reason == "invalid_path"


def test_index_rebuild_reloads_markdown_and_tracks_external_edits(vault, files_root):
    vault.save(PERSON, "Plans.md", "[[Agenda|today]] and [[Topics/New#Summary]]\n", revision=None)
    vault.save(PERSON, "Agenda.md", "Public agenda\n", revision=None)
    directory = files_root / vault.files.share_folder("home", PERSON.id) / "Notes"
    (directory / "Topics").mkdir()
    (directory / "Topics" / "New.md").write_text("[[../Agenda]]\nA topic for tomorrow\n")
    (directory / ".obsidian").mkdir()
    (directory / ".obsidian" / "hidden.md").write_text("[[Agenda]]")
    (directory / "loop").symlink_to(directory)
    index = NotesIndex(vault)
    links = {"/Agenda.md": ["/Plans.md", "/Topics/New.md"], "/Topics/New.md": ["/Plans.md"]}
    assert index.rebuild(PERSON) == links
    home = vault.files.space_dir_name(PERSON.id)
    sidecar = files_root / ".system" / "notes" / home / "links-v1.json"
    assert sidecar.is_file() and "tomorrow" not in sidecar.read_text()
    sidecar.unlink()
    assert index.backlinks(PERSON, "Agenda.md") == links["/Agenda.md"]
    assert sidecar.is_file()
    (directory / "Plans.md").write_text("no links here\n")
    assert index.backlinks(PERSON, "Agenda.md") == ["/Topics/New.md"]
    assert index.search(PERSON, "TOMORROW") == ["/Topics/New.md"]
    assert index.search(OTHER, "tomorrow") == []


def test_wikilinks_ignore_code_and_collect_aliases_once():
    markdown = """[[Agenda]] ![[Agenda|alias]] [[Plans#Today]] [[#here]]
`[[inline]]` \\[[escaped]]
````md
```
[[in a longer fence]]
````
~~~
[[in a tilde fence]]
~~~
 [[Folder/Topic#heading|shown]]
"""
    assert wikilinks(markdown) == ["Agenda", "Folder/Topic", "Plans"]


def test_capture_retry_cannot_replace_an_existing_capture(vault):
    key = UUID(int=42)
    note = vault.capture(PERSON, key, "A thought\n")
    assert vault.capture(PERSON, key, note.markdown) == note
    with pytest.raises(FilesError) as exc:
        vault.capture(PERSON, key, "something else")
    assert exc.value.reason == "exists"
    assert vault.get(PERSON, note.path) == note


def test_external_change_during_staging_is_saved_as_conflict(vault, files_root, monkeypatch):
    note = vault.save(PERSON, "Race.md", "original", revision=None).note
    file = files_root / vault.files.share_folder("home", PERSON.id) / "Notes" / "Race.md"
    write_temp = notes._write_temp

    def external_edit(dir_fd, data):
        name = write_temp(dir_fd, data)
        file.write_text("external edit")
        return name

    monkeypatch.setattr(notes, "_write_temp", external_edit)
    saved = vault.save(PERSON, note.path, "gateway edit", revision=note.revision)
    assert saved.conflict and saved.note.markdown == "gateway edit"
    assert vault.get(PERSON, note.path).markdown == "external edit"
