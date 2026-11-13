# SPDX-License-Identifier: Apache-2.0
"""Preview metadata without running a media parser: type from the name and magic bytes, image
size from fixed header fields, and a text excerpt. Thumbnails are FILES-3 (sandboxed vips and
FFmpeg, docs/umbrel2/files-backups.md §4.6), not this module."""

from __future__ import annotations

import mimetypes
import struct

# Types a browser may show inline from a download URL. Everything else is sent as an
# attachment. SVG and HTML are never inline: they can run script.
INLINE_SAFE = frozenset({
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif",
    "application/pdf", "text/plain", "audio/mpeg", "audio/ogg", "audio/wav", "audio/flac",
    "video/mp4", "video/webm",
})
TEXT_TYPES = frozenset({"application/json", "application/xml", "application/yaml", "application/x-yaml",
                        "application/toml", "application/javascript", "image/svg+xml"})

_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"%PDF-", "application/pdf"),
    (b"PK\x03\x04", "application/zip"),
    (b"\x1f\x8b", "application/gzip"),
)


def guess_mime(name: str, head: bytes = b"") -> str:
    for magic, mime in _MAGIC:
        if head.startswith(magic):
            return mime
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    guessed, _ = mimetypes.guess_type(name, strict=False)
    return guessed or "application/octet-stream"


def kind_of_mime(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    if mime == "application/pdf":
        return "pdf"
    if mime.startswith("text/") or mime in TEXT_TYPES:
        return "text"
    return "other"


def image_size(head: bytes) -> tuple[int, int] | None:
    """(width, height) from PNG, GIF, WebP or JPEG headers; None if unknown or malformed."""
    try:
        if head.startswith(b"\x89PNG\r\n\x1a\n") and head[12:16] == b"IHDR":
            return struct.unpack(">II", head[16:24])
        if head[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", head[6:10])
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            chunk = head[12:16]
            if chunk == b"VP8X":
                w = int.from_bytes(head[24:27], "little") + 1
                h = int.from_bytes(head[27:30], "little") + 1
                return w, h
            if chunk == b"VP8L" and head[20] == 0x2F:
                bits = int.from_bytes(head[21:25], "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if chunk == b"VP8 " and head[23:26] == b"\x9d\x01\x2a":
                w, h = struct.unpack("<HH", head[26:30])
                return w & 0x3FFF, h & 0x3FFF
        if head.startswith(b"\xff\xd8"):
            i = 2
            while i + 9 < len(head):
                if head[i] != 0xFF:
                    return None
                marker = head[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                (seg_len,) = struct.unpack(">H", head[i + 2:i + 4])
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", head[i + 5:i + 9])
                    return w, h
                if seg_len < 2:
                    return None
                i += 2 + seg_len
    except (struct.error, IndexError):
        return None
    return None


def describe(name: str, head: bytes, size: int, text_limit: int) -> dict:
    mime = guess_mime(name, head)
    kind = kind_of_mime(mime)
    out: dict = {"mime": mime, "kind": kind, "size": size, "inline_safe": mime in INLINE_SAFE}
    if kind == "image":
        dims = image_size(head)
        out["image"] = {"width": dims[0], "height": dims[1]} if dims else None
    if kind == "text" or (kind == "other" and b"\x00" not in head[:8192] and size <= text_limit and head):
        excerpt = head[:text_limit]
        try:
            text = excerpt.decode("utf-8")
        except UnicodeDecodeError as exc:
            # A multi-byte character cut at the limit is fine; anything else is not text.
            if exc.start < len(excerpt) - 3:
                return out
            text = excerpt[: exc.start].decode("utf-8")
        if kind == "other":
            out["kind"] = "text"
        out["text"] = {"excerpt": text, "truncated": size > len(excerpt)}
    return out
