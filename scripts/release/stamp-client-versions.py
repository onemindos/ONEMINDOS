#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""One version for every OneMind client app (desktop and mobile), from the OS release version.

  stamp-client-versions.py --version 0.2.0 [--build 17] [--root DIR] [--check]

Writes the same X.Y.Z into desktop (tauri.conf.json, package.json and lock, Cargo.toml and lock) and
mobile (app.json version, package.json and lock), plus the two store build counters the stores demand:
Android versionCode and iOS buildNumber. With --check it changes nothing and exits 1 if any file differs.

Why only X.Y.Z: the App Store, Google Play and the Windows MSI installer reject or mangle a pre-release
suffix like "-dev.7", so a "0.2.0-dev.7" OS version becomes client version 0.2.0 and the suffix is
carried by the build counter. The build counter is the CI run number (0-9999), and must go up for every
upload of the same version. Android versionCode = MAJOR*100_000_000 + MINOR*1_000_000 + PATCH*10_000 + build,
so it also goes up with every new version (Google Play needs a strictly rising integer, max 2.1 billion, so major <= 20).
GITHUB_RUN_NUMBER never resets, so past run 9999 the release gate refuses with a clear message (exit 2) before anything is published.
Exit 2 on bad input. This script never touches the bundle identifiers (see the PR body).
"""
import argparse, json, os, re, sys

SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")


def core_version(v):
    m = SEMVER.match(v or "")
    if not m:
        raise ValueError(f"'{v}' is not a version like 1.2.3 or 1.2.3-dev.7")
    major, minor, patch = (int(x) for x in m.groups())
    if major > 20 or minor > 99 or patch > 99:
        raise ValueError("version out of range for the Android versionCode (major<=20, minor<=99, patch<=99)")
    return major, minor, patch


def version_code(version, build):
    major, minor, patch = core_version(version)
    if not 0 <= build <= 9999:
        raise ValueError(f"build counter {build} is outside 0-9999 (the CI run number no longer fits the Android versionCode; "
                         "pass a per-version counter with --build)")
    return major * 100_000_000 + minor * 1_000_000 + patch * 10_000 + build


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def _json(text, edit):
    d = json.loads(text)
    edit(d)
    return json.dumps(d, indent=2, ensure_ascii=False) + "\n"


def _sub_first(pattern, repl, text, what):
    new, n = re.subn(pattern, repl, text, count=1, flags=re.M)
    if n != 1:
        raise ValueError(f"cannot find {what}")
    return new


def plan(root, ver, build):
    """{relative path: new text} for every stamped file."""
    code = version_code(ver, build)
    core = "{}.{}.{}".format(*core_version(ver))
    out = {}

    def pkg(d):
        d["version"] = core

    def lock(d):
        d["version"] = core
        d["packages"][""]["version"] = core

    def app(d):
        d["expo"]["version"] = core
        d["expo"]["android"]["versionCode"] = code
        d["expo"]["ios"]["buildNumber"] = str(build)

    for rel, edit in (("desktop/package.json", pkg), ("desktop/package-lock.json", lock),
                      ("mobile/package.json", pkg), ("mobile/package-lock.json", lock),
                      ("mobile/app.json", app)):
        out[rel] = _json(_read(os.path.join(root, rel)), edit)
    rel = "desktop/src-tauri/tauri.conf.json"
    out[rel] = _sub_first(r'^(\s*"version":\s*)"[^"]*"', rf'\g<1>"{core}"', _read(os.path.join(root, rel)), rel)
    rel = "desktop/src-tauri/Cargo.toml"
    out[rel] = _sub_first(r'^version = "[^"]*"', f'version = "{core}"', _read(os.path.join(root, rel)), rel)
    rel = "desktop/src-tauri/Cargo.lock"   # keep `cargo build --locked` happy: only our own crate's entry
    out[rel] = _sub_first(r'^(name = "onemind-desktop"\nversion = )"[^"]*"', rf'\g<1>"{core}"',
                          _read(os.path.join(root, rel)), rel)
    return out


def read_versions(root):
    """What the committed files say now (used by the drift test)."""
    def j(rel):
        return json.loads(_read(os.path.join(root, rel)))
    app = j("mobile/app.json")["expo"]
    toml = re.search(r'^version = "([^"]*)"', _read(os.path.join(root, "desktop/src-tauri/Cargo.toml")), re.M)
    lockm = re.search(r'^name = "onemind-desktop"\nversion = "([^"]*)"',
                      _read(os.path.join(root, "desktop/src-tauri/Cargo.lock")), re.M)
    return {
        "desktop/src-tauri/tauri.conf.json": j("desktop/src-tauri/tauri.conf.json")["version"],
        "desktop/package.json": j("desktop/package.json")["version"],
        "desktop/package-lock.json": j("desktop/package-lock.json")["version"],
        "desktop/package-lock.json packages": j("desktop/package-lock.json")["packages"][""]["version"],
        "desktop/src-tauri/Cargo.toml": toml.group(1) if toml else None,
        "desktop/src-tauri/Cargo.lock": lockm.group(1) if lockm else None,
        "mobile/app.json": app["version"],
        "mobile/package.json": j("mobile/package.json")["version"],
        "mobile/package-lock.json": j("mobile/package-lock.json")["version"],
        "mobile/package-lock.json packages": j("mobile/package-lock.json")["packages"][""]["version"],
    }, app["android"].get("versionCode"), app["ios"].get("buildNumber")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--version", required=True, help="OS release version, e.g. 0.2.0 or 0.2.0-dev.7")
    ap.add_argument("--build", type=int, default=1, help="store build counter (CI run number, 0-9999)")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    ap.add_argument("--check", action="store_true", help="change nothing; exit 1 if files differ")
    a = ap.parse_args(argv)
    try:
        new = plan(a.root, a.version, a.build)
    except (ValueError, KeyError, OSError) as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2
    stale = [r for r, t in new.items() if _read(os.path.join(a.root, r)) != t]
    if a.check:
        for r in stale:
            print(f"DIFFERS: {r}", file=sys.stderr)
        print("client versions: " + ("DRIFT" if stale else "ok"))
        return 1 if stale else 0
    for r in stale:
        with open(os.path.join(a.root, r), "w", encoding="utf-8") as f:
            f.write(new[r])
        print(f"stamped {r}")
    core = "{}.{}.{}".format(*core_version(a.version))
    print(f"client version {core}, android versionCode {version_code(a.version, a.build)}, ios buildNumber {a.build}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
