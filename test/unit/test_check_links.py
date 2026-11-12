# SPDX-License-Identifier: Apache-2.0
"""scripts/check-links.py on a small built site: files, directories, fragments, base path, repo links."""
import contextlib
import importlib.machinery
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_loader = importlib.machinery.SourceFileLoader("check_links", str(ROOT / "scripts" / "check-links.py"))
_spec = importlib.util.spec_from_loader(_loader.name, _loader)
cl = importlib.util.module_from_spec(_spec)
_loader.exec_module(cl)

REPO = "https://github.com/example/repo"


def site(files: dict[str, str]) -> Path:
    d = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    return d


def run(dist: Path, *args: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        rc = cl.main([str(dist), *args])
    return rc, out.getvalue()


GOOD = {
    "index.html": '<html><body id="_top"><a href="#_top">top</a><a href="docs/">docs</a>'
                  '<a href="/docs/install/#step-2">install</a><link rel="stylesheet" href="/_astro/a.css">'
                  '<img src="/img/logo.svg" srcset="/img/logo.svg 1x, /img/logo@2x.png 2x">'
                  '<a href="mailto:x@example.invalid">m</a><a href="https://example.org/x">ext</a>'
                  '<link rel="preconnect" href="https://fonts.invalid"></body></html>',
    "docs/index.html": '<a href="../">home</a><a href="install/">install</a><a href="./install/index.html">idx</a>',
    "docs/install/index.html": '<h2 id="step-2">Step 2</h2><a name="old-anchor"></a><a href="#old-anchor">x</a>',
    "_astro/a.css": "body{}",
    "img/logo.svg": "<svg/>",
    "img/logo@2x.png": "png",
}


class LinkCheck(unittest.TestCase):
    def test_clean_site(self):
        rc, out = run(site(GOOD))
        self.assertEqual(rc, 0, out)
        self.assertIn("ok: 3 pages", out)
        self.assertIn("1 external links not fetched", out)  # preconnect hints are not links

    def test_broken_links(self):
        files = dict(GOOD)
        files["docs/index.html"] = ('<a href="missing/">a</a><a href="/docs/install/#nope">b</a>'
                                    '<img src="/img/gone.png"><a href="#also-missing">c</a>'
                                    '<a href="../../../etc/passwd">d</a>')
        rc, out = run(site(files))
        self.assertEqual(rc, 1)
        self.assertIn("docs/index.html: missing/ (no such file in the build)", out)
        self.assertIn("no id 'nope' on docs/install/index.html", out)
        self.assertIn("/img/gone.png (no such file in the build)", out)
        self.assertIn("#also-missing (no id 'also-missing' on docs/index.html)", out)
        self.assertIn("../../../etc/passwd (no such file in the build)", out)
        self.assertIn("5 broken", out)

    def test_base_path(self):
        d = site({"index.html": '<a href="/onemind/docs/">ok</a><a href="/docs/">outside</a>', "docs/index.html": ""})
        rc, out = run(d, "--base", "/onemind/")
        self.assertEqual(rc, 1)
        self.assertIn("/docs/ (outside the site base /onemind/)", out)
        self.assertNotIn("/onemind/docs/ (", out)

    def test_repository_links(self):
        repo = Path(tempfile.mkdtemp())
        (repo / "docs").mkdir()
        (repo / "docs" / "a.md").write_text("x")
        d = site({"index.html":
                  f'<a href="{REPO}/blob/main/docs/a.md#intro">ok</a><a href="{REPO}/tree/main/docs/">dir</a>'
                  f'<a href="{REPO}/edit/main/docs/gone.md">gone</a><a href="{REPO}/blob/main/../secret">esc</a>'
                  f'<a href="{REPO}/blob/v1.0/docs/old.md">other ref</a><a href="{REPO}/issues">issues</a>'})
        rc, out = run(d, "--repo-url", REPO, "--repo-root", str(repo))
        self.assertEqual(rc, 1)
        self.assertIn("no 'docs/gone.md' in the repository", out)
        self.assertIn("repository path escapes the checkout", out)
        self.assertIn("2 broken, 4 repository links checked, 2 external links not fetched", out)

    def test_bad_input(self):
        self.assertEqual(run(Path(tempfile.mkdtemp()))[0], 2)
        self.assertEqual(run(site(GOOD), "--repo-url", REPO)[0], 2)


if __name__ == "__main__":
    unittest.main()
