#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Package the `onemind` CLI for laptops (#882): a .tar.gz per platform, a .deb for Linux, a Homebrew formula.

Artifacts only: this writes files into --out and publishes nothing (no tokens, no upload). The release
workflow signs and attaches them later (#882, founder item F-27).

  cli-packages.py --version 0.1.0 --bin-dir bin --completions comp --man man --out dist

--bin-dir holds one binary per target, named onemind-<os>-<arch> (linux-amd64, linux-arm64, darwin-arm64,
darwin-amd64). --completions holds onemind.bash, _onemind, onemind.fish; --man holds the gzipped man pages.
Output is reproducible: fixed timestamps (SOURCE_DATE_EPOCH, default 0), sorted entries, root ownership.
Pure standard library, so it runs on a Mac, in CI and in tests; the .deb is written without dpkg.
"""
import argparse
import gzip
import hashlib
import io
import os
import re
import sys
import tarfile

TARGETS = [("linux", "amd64"), ("linux", "arm64"), ("darwin", "arm64"), ("darwin", "amd64")]
DEB_ARCH = {"amd64": "amd64", "arm64": "arm64"}
HOMEPAGE = "https://github.com/onemindos/onemindos"
DESC = "Command-line tool for OneMind OS boxes"
LONG = ("onemind talks to the gateway of a OneMind box: nodes, apps, the approval queue, the audit log,\n"
        " updates and the MCP bridge for AI agents. Every change is a request that an owner approves.")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([-+~.][0-9A-Za-z.]+)?$")


def die(msg):
    sys.exit("cli-packages: " + msg)


def epoch():
    return int(os.environ.get("SOURCE_DATE_EPOCH", "0"))


def read(path):
    with open(path, "rb") as f:
        return f.read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def gz(data):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=epoch(), compresslevel=9) as g:
        g.write(data)
    return buf.getvalue()


def tar_bytes(entries, prefix=""):
    """entries: [(path, bytes, mode)] -> an uncompressed tar with root ownership and a fixed mtime."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        dirs = set()
        for path, _, _ in entries:
            parts = path.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        for d in sorted(dirs):
            ti = tarfile.TarInfo(prefix + d)
            ti.type, ti.mode, ti.mtime = tarfile.DIRTYPE, 0o755, epoch()
            t.addfile(ti)
        for path, data, mode in sorted(entries):
            ti = tarfile.TarInfo(prefix + path)
            ti.size, ti.mode, ti.mtime = len(data), mode, epoch()
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def payload(version, goos, binary, comp, man, licence, readme):
    """The files every package carries, as (path under the install root, bytes, mode)."""
    files = [("bin/onemind", binary, 0o755)]
    if goos == "linux":
        files += [("share/bash-completion/completions/onemind", comp["onemind.bash"], 0o644),
                  ("share/zsh/vendor-completions/_onemind", comp["_onemind"], 0o644),
                  ("share/fish/vendor_completions.d/onemind.fish", comp["onemind.fish"], 0o644)]
    else:  # Homebrew's own layout (the formula installs these with bash_completion.install and friends)
        files += [("share/bash-completion/completions/onemind", comp["onemind.bash"], 0o644),
                  ("share/zsh/site-functions/_onemind", comp["_onemind"], 0o644),
                  ("share/fish/vendor_completions.d/onemind.fish", comp["onemind.fish"], 0o644)]
    files += [("share/man/man1/" + n, d, 0o644) for n, d in sorted(man.items())]
    files += [("share/doc/onemind/LICENSE", licence, 0o644), ("share/doc/onemind/README", readme, 0o644)]
    return files


def archive(version, goos, arch, files):
    """onemind_<version>_<os>_<arch>.tar.gz: one top folder, the same tree a prefix install makes."""
    top = f"onemind_{version}_{goos}_{arch}/"
    return gz(tar_bytes(files, prefix=top))


def ar(members):
    out = b"!<arch>\n"
    for name, data in members:
        hdr = f"{name + '/':<16}{epoch():<12}{0:<6}{0:<6}{'100644':<8}{len(data):<10}`\n"
        assert len(hdr) == 60
        out += hdr.encode() + data + (b"\n" if len(data) % 2 else b"")
    return out


def deb(version, arch, files):
    """A .deb with the files under /usr. Version 0.1.0-dev becomes 0.1.0~dev so it sorts before 0.1.0."""
    dv = re.sub(r"-", "~", version, count=1)
    size_kib = (sum(len(d) for _, d, _ in files) + 1023) // 1024
    control = (f"Package: onemind\nVersion: {dv}\nSection: admin\nPriority: optional\nArchitecture: {DEB_ARCH[arch]}\n"
               f"Maintainer: OneMind OS contributors <noreply@users.noreply.github.com>\nInstalled-Size: {size_kib}\nHomepage: {HOMEPAGE}\n"
               f"Suggests: bash-completion, man-db\nDescription: {DESC}\n {LONG}\n")
    usr = [(p, d, m) for p, d, m in files]
    data = gz(tar_bytes(usr, prefix="./usr/"))
    md5s = "".join(f"{hashlib.md5(d).hexdigest()}  usr/{p}\n" for p, d, _ in sorted(files)).encode()
    ctl = gz(tar_bytes([("control", control.encode(), 0o644), ("md5sums", md5s, 0o644)], prefix="./"))
    return ar([("debian-binary", b"2.0\n"), ("control.tar.gz", ctl), ("data.tar.gz", data)])


def formula(version, base_url, sums):
    """A Homebrew formula (a tap file). sums: {(os, arch): sha256 of that tar.gz}."""
    def block(goos, arch):
        n = f"onemind_{version}_{goos}_{arch}.tar.gz"
        return f'    url "{base_url}/{n}"\n    sha256 "{sums[(goos, arch)]}"\n'
    lines = ['# SPDX-License-Identifier: Apache-2.0', 'class Onemind < Formula', f'  desc "{DESC}"', f'  homepage "{HOMEPAGE}"',
             f'  version "{version}"', '  license "Apache-2.0"', '']
    for goos, os_blk in (("darwin", "on_macos"), ("linux", "on_linux")):
        lines.append(f"  {os_blk} do")
        archs = [a for o, a in TARGETS if o == goos]
        for i, arch in enumerate(archs):
            cond = "Hardware::CPU.arm?" if arch == "arm64" else "Hardware::CPU.intel?"
            lines.append(f"    if {cond}")
            lines += ["  " + l if l else l for l in block(goos, arch).rstrip("\n").split("\n")]
            lines.append("    end")
        lines += ["  end", ""]
    lines += ['  def install', '    bin.install "bin/onemind"',
              '    bash_completion.install "share/bash-completion/completions/onemind"',
              '    zsh_completion.install "share/zsh/site-functions/_onemind"',
              '    fish_completion.install "share/fish/vendor_completions.d/onemind.fish"',
              '    man1.install Dir["share/man/man1/*.1.gz"]', '  end', '',
              '  test do', '    assert_match version.to_s, shell_output("#{bin}/onemind version")', '  end', 'end', '']
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--bin-dir", required=True)
    ap.add_argument("--completions", required=True)
    ap.add_argument("--man", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--licence", default="LICENSE")
    ap.add_argument("--readme", default="cmd/onemind/README.md")
    ap.add_argument("--url-base", default=None, help="where the archives will be published (formula urls)")
    a = ap.parse_args(argv)
    if not VERSION_RE.match(a.version):
        die(f"version {a.version!r} is not like 0.1.0 or 0.1.0-dev")
    base = a.url_base or f"{HOMEPAGE}/releases/download/v{a.version}"
    comp = {n: read(os.path.join(a.completions, n)) for n in ("onemind.bash", "_onemind", "onemind.fish")}
    man = {n: read(os.path.join(a.man, n)) for n in sorted(os.listdir(a.man)) if n.endswith(".1.gz")}
    if "onemind.1.gz" not in man:
        die(f"no onemind.1.gz in {a.man}")
    for n, d in comp.items():
        if not d:
            die(f"{n} is empty")
    licence, readme = read(a.licence), read(a.readme)
    os.makedirs(a.out, exist_ok=True)
    sums, written = {}, []
    for goos, arch in TARGETS:
        bp = os.path.join(a.bin_dir, f"onemind-{goos}-{arch}")
        if not os.path.isfile(bp):
            die(f"missing binary {bp}")
        binary = read(bp)
        files = payload(a.version, goos, binary, comp, man, licence, readme)
        name = f"onemind_{a.version}_{goos}_{arch}.tar.gz"
        data = archive(a.version, goos, arch, files)
        sums[(goos, arch)] = sha256(data)
        outs = [(name, data)]
        if goos == "linux":
            outs.append((f"onemind_{a.version}_{arch}.deb", deb(a.version, arch, files)))
        for fn, d in outs:
            with open(os.path.join(a.out, fn), "wb") as f:
                f.write(d)
            written.append((fn, d))
    fm = formula(a.version, base, sums).encode()
    with open(os.path.join(a.out, "onemind.rb"), "wb") as f:
        f.write(fm)
    written.append(("onemind.rb", fm))
    with open(os.path.join(a.out, "SHA256SUMS"), "w") as f:
        for fn, d in sorted(written):
            f.write(f"{sha256(d)}  {fn}\n")
    for fn, _ in sorted(written):
        print(fn)


if __name__ == "__main__":
    main()
