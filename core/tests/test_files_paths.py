# SPDX-License-Identifier: Apache-2.0
"""FILES path confinement: text validation and a fuzz run of the descriptor walk (no escapes)."""

from __future__ import annotations

import fcntl
import os
import random
import sys
from pathlib import Path

import pytest

from onemind_core.files import paths
from onemind_core.files.errors import FilesError


def fd_path(fd: int) -> Path:
    if sys.platform == "darwin":
        raw = fcntl.fcntl(fd, 50, b"\0" * 1024)  # F_GETPATH
        return Path(raw.split(b"\0", 1)[0].decode())
    return Path(os.readlink(f"/proc/self/fd/{fd}"))


@pytest.mark.parametrize("bad", ["..", "a/../b", "./a", "a/.", "a\\b", "a\x00", "a/\x01", "x" * 256,
                                 "/".join(["a"] * 2100), "\udcff", "a/ /b"])
def test_split_path_refuses(bad):
    with pytest.raises(paths.PathRefused):
        paths.split_path(bad)


def test_split_path_accepts_and_normalises():
    assert paths.split_path("") == ()
    assert paths.split_path("/") == ()
    assert paths.split_path("//a///b/") == ("a", "b")
    assert paths.split_path("Fotos/Été 2026/IMG 1.jpg") == ("Fotos", "Été 2026", "IMG 1.jpg")
    assert paths.join(("a", "b")) == "/a/b"
    assert paths.is_within(("a", "b", "c"), ("a", "b")) and not paths.is_within(("a", "bc"), ("a", "b"))


def test_fuzzed_paths_never_leave_the_base(tmp_path):
    base = (tmp_path / "space").resolve()
    outside = (tmp_path / "outside").resolve()
    (base / "a" / "b").mkdir(parents=True)
    outside.mkdir()
    (base / "a" / "up").symlink_to("../..")
    (base / "a" / "b" / "abs").symlink_to(outside)
    (base / "rel").symlink_to("../outside")
    (base / "a" / "file").write_text("x")
    tokens = ["a", "b", "up", "abs", "rel", "file", "..", ".", "", "%2e%2e", "a\\..", "..\x00", "outside", "~"]
    rng = random.Random(20261112)
    base_fd = os.open(base, paths.O_DIR)
    opened = refused = 0
    try:
        for _ in range(4000):
            candidate = "/".join(rng.choice(tokens) for _ in range(rng.randint(0, 6)))
            try:
                fd = paths.open_dir(base_fd, paths.split_path(candidate))
            except FilesError:
                refused += 1
                continue
            try:
                where = fd_path(fd).resolve()
                assert where == base or base in where.parents, (candidate, where)
                opened += 1
            finally:
                os.close(fd)
    finally:
        os.close(base_fd)
    assert opened > 100 and refused > 100  # both branches were exercised


def test_tree_size_ignores_symlinks(tmp_path):
    (tmp_path / "d").mkdir()
    (tmp_path / "d" / "f").write_bytes(b"12345")
    big = tmp_path / "big"
    big.write_bytes(b"x" * 1000)
    (tmp_path / "d" / "link").symlink_to(big)
    fd = os.open(tmp_path, paths.O_DIR)
    try:
        assert paths.tree_size(fd, "d") == 5
    finally:
        os.close(fd)
