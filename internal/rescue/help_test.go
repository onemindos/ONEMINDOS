// SPDX-License-Identifier: Apache-2.0

package rescue

import (
	"io/fs"
	"math"
	"net/http/httptest"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

// shippedPack is the pack the image installs at DefaultHelpDir.
var shippedPack = filepath.Join("..", "..", "os", "rootfs", "layers", "onemind", "usr", "share", "onemind", "help")

func writePack(t *testing.T, files map[string]string) string {
	t.Helper()
	dir := t.TempDir()
	for name, body := range files {
		p := filepath.Join(dir, filepath.FromSlash(name))
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	return dir
}

func helpServer(t *testing.T, dir string) (*Server, *fakeRunner) {
	t.Helper()
	f := &fakeRunner{}
	return New(Config{TokensFile: tokensFile(t, hashedOwner()), Runner: f, HelpDir: dir}), f
}

// #504: the rescue console serves the offline pack, so the owner can read it with the gateway and k3s down.
// The console never talks to the gateway for these pages, and reading help runs no host command.
func TestOwnerReadsTheHelpPackFromTheRescueConsole(t *testing.T) {
	dir := writePack(t, map[string]string{
		"index.html":        "<h1>Pack home</h1>",
		"style.css":         "body{}",
		"guides/index.html": "<h1>Guides</h1>",
	})
	s, f := helpServer(t, dir)

	if page := do(s, "GET", "/", ownerToken, nil); page.Code != 200 || !strings.Contains(page.Body.String(), `<a href="help/">`) {
		t.Fatalf("console page should link to the pack: %d %s", page.Code, page.Body)
	}
	f.calls = nil
	for p, want := range map[string]struct{ body, ctype string }{
		"/help/":          {"Pack home", "text/html; charset=utf-8"},
		"/help/style.css": {"body{}", "text/css; charset=utf-8"},
		"/help/guides/":   {"Guides", "text/html; charset=utf-8"},
	} {
		w := do(s, "GET", p, ownerToken, nil)
		if w.Code != 200 || !strings.Contains(w.Body.String(), want.body) || w.Header().Get("Content-Type") != want.ctype {
			t.Fatalf("%s = %d %q %q", p, w.Code, w.Header().Get("Content-Type"), w.Body)
		}
		csp := w.Header().Get("Content-Security-Policy")
		if csp != helpCSP || strings.Contains(csp, "script") || !strings.Contains(csp, "default-src 'none'") {
			t.Fatalf("%s: pack pages must forbid script, got CSP %q", p, csp)
		}
	}
	if len(f.calls) != 0 {
		t.Fatalf("reading help ran host commands: %v", f.calls)
	}
}

// The pack sits behind the console's own guard: LAN clients with the owner credential only.
func TestHelpNeedsTheOwnerOnTheLAN(t *testing.T) {
	s, _ := helpServer(t, writePack(t, map[string]string{"index.html": "secret-free help"}))
	for name, tok := range map[string]string{"no credential": "", "wrong": "wrong", "agent hash": strings.Repeat("ab", 32)} {
		if w := do(s, "GET", "/help/", tok, nil); w.Code != 401 {
			t.Errorf("%s: code %d", name, w.Code)
		}
	}
	for _, addr := range []string{"198.51.100.7:1", "[fd7a:115c:a1e0::5]:1"} {
		r := httptest.NewRequest("GET", "/help/", nil)
		r.RemoteAddr = addr
		r.SetBasicAuth("owner", ownerToken)
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != 403 {
			t.Errorf("%s: code %d, want 403", addr, w.Code)
		}
	}
}

// Only pack files of the allowed kinds, inside the pack, are ever served: no listing, no script file, no
// escape through "..", an absolute path or a symlink, nothing oversized.
func TestHelpServesOnlyPackFiles(t *testing.T) {
	outside := writePack(t, map[string]string{"tokens.yaml": "owner-secret"})
	dir := writePack(t, map[string]string{
		"index.html":       "home",
		"app.js":           "alert(1)",
		"empty/readme.txt": "no index here",
	})
	if err := os.Symlink(filepath.Join(outside, "tokens.yaml"), filepath.Join(dir, "leak.txt")); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, filepath.Join(dir, "out")); err != nil {
		t.Fatal(err)
	}
	big, err := os.Create(filepath.Join(dir, "big.txt"))
	if err != nil {
		t.Fatal(err)
	}
	if err := big.Truncate(MaxHelpFileBytes + 1); err != nil {
		t.Fatal(err)
	}
	_ = big.Close()
	s, _ := helpServer(t, dir)

	for _, p := range []string{"/help/app.js", "/help/empty/", "/help/empty", "/help/leak.txt", "/help/out/tokens.yaml",
		"/help/big.txt", "/help/missing.html", "/help/%2e%2e/" + filepath.Base(outside) + "/tokens.yaml"} {
		w := do(s, "GET", p, ownerToken, nil)
		if w.Code == 200 || strings.Contains(w.Body.String(), "owner-secret") || strings.Contains(w.Body.String(), "alert") {
			t.Errorf("%s served: %d %q", p, w.Code, w.Body)
		}
	}
	for _, rel := range []string{"../tokens.yaml", "/etc/passwd", filepath.Join(outside, "tokens.yaml")} {
		if f, _, ok := s.helpFile(rel); ok {
			_ = f.Close()
			t.Errorf("helpFile(%q) opened a file outside the pack", rel)
		}
	}
}

func TestNoPackNoLink(t *testing.T) {
	for name, dir := range map[string]string{"unset": "", "missing": filepath.Join(t.TempDir(), "none")} {
		s, _ := helpServer(t, dir)
		if page := do(s, "GET", "/", ownerToken, nil); page.Code != 200 || strings.Contains(page.Body.String(), `href="help/"`) {
			t.Errorf("%s: console links to a pack that is not there: %d", name, page.Code)
		}
		if w := do(s, "GET", "/help/", ownerToken, nil); w.Code != 404 || !strings.Contains(w.Body.String(), "no offline help pack") {
			t.Errorf("%s: /help/ = %d %q", name, w.Code, w.Body)
		}
	}
}

var (
	scriptRe = regexp.MustCompile(`(?i)<script|javascript:|\son[a-z]+\s*=`)
	refRe    = regexp.MustCompile(`(?i)\s(?:href|src)\s*=\s*"([^"]*)"`)
	cssURLRe = regexp.MustCompile(`(?i)url\(|@import`)
)

// The pack the image ships must open offline with no JavaScript: allowed file kinds only, no script in any
// page, no link off the box, every link landing on a file in the pack. The console then serves every page.
func TestShippedHelpPackIsOfflineAndScriptFree(t *testing.T) {
	files := map[string]bool{}
	err := filepath.WalkDir(shippedPack, func(p string, d fs.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return err
		}
		rel, _ := filepath.Rel(shippedPack, p)
		files[filepath.ToSlash(rel)] = true
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if !files["index.html"] {
		t.Fatal("the pack has no index.html")
	}
	s, _ := helpServer(t, shippedPack)
	for rel := range files {
		ext := strings.ToLower(path.Ext(rel))
		if _, ok := helpTypes[ext]; !ok {
			t.Errorf("%s: %q files are not served by the console", rel, ext)
			continue
		}
		b, err := os.ReadFile(filepath.Join(shippedPack, filepath.FromSlash(rel)))
		if err != nil {
			t.Fatal(err)
		}
		body := string(b)
		if scriptRe.MatchString(body) {
			t.Errorf("%s carries script: the pack must work with JavaScript off", rel)
		}
		if ext == ".css" && cssURLRe.MatchString(body) {
			t.Errorf("%s loads another resource: keep the stylesheet self-contained", rel)
		}
		for _, m := range refRe.FindAllStringSubmatch(body, -1) {
			ref := m[1]
			if strings.Contains(ref, ":") || strings.HasPrefix(ref, "/") {
				t.Errorf("%s links off the pack (%q): it must open with the network off", rel, ref)
				continue
			}
			target := path.Join(path.Dir(rel), strings.SplitN(ref, "#", 2)[0])
			if !files[target] {
				t.Errorf("%s links to %q, which is not in the pack", rel, ref)
			}
		}
		if w := do(s, "GET", "/help/"+rel, ownerToken, nil); w.Code != 200 {
			t.Errorf("console does not serve %s: %d", rel, w.Code)
		}
	}
}

var cssVarRe = regexp.MustCompile(`--(bg|fg|accent):\s*(#[0-9a-fA-F]{6})`)

// luminance is the WCAG 2.x relative luminance of a #rrggbb colour.
func luminance(t *testing.T, hex string) float64 {
	t.Helper()
	var ch [3]float64
	for i := range ch {
		v, err := strconv.ParseUint(hex[1+2*i:3+2*i], 16, 8)
		if err != nil {
			t.Fatalf("bad colour %q: %v", hex, err)
		}
		c := float64(v) / 255
		if c <= 0.04045 {
			ch[i] = c / 12.92
		} else {
			ch[i] = math.Pow((c+0.055)/1.055, 2.4)
		}
	}
	return 0.2126*ch[0] + 0.7152*ch[1] + 0.0722*ch[2]
}

func contrast(t *testing.T, a, b string) float64 {
	la, lb := luminance(t, a), luminance(t, b)
	if la < lb {
		la, lb = lb, la
	}
	return (la + 0.05) / (lb + 0.05)
}

// Link and body text in the shipped pack must meet WCAG AA (1.4.3, 4.5:1) in both the light and dark
// schemes, against the page colour the stylesheet pins, using the D-016 teal accent.
func TestShippedHelpStyleMeetsContrastInBothSchemes(t *testing.T) {
	b, err := os.ReadFile(filepath.Join(shippedPack, "style.css"))
	if err != nil {
		t.Fatal(err)
	}
	css := string(b)
	i := strings.Index(css, "@media (prefers-color-scheme: dark)")
	if i < 0 {
		t.Fatal("style.css has no dark-scheme block: one accent cannot pass on both a light and a dark page")
	}
	want := map[string]string{"light": "#1f6a66", "dark": "#6db8b0"}
	for scheme, part := range map[string]string{"light": css[:i], "dark": css[i:]} {
		vars := map[string]string{}
		for _, m := range cssVarRe.FindAllStringSubmatch(part, -1) {
			vars[m[1]] = strings.ToLower(m[2])
		}
		for _, k := range []string{"bg", "fg", "accent"} {
			if vars[k] == "" {
				t.Fatalf("%s scheme does not set --%s", scheme, k)
			}
		}
		if vars["accent"] != want[scheme] {
			t.Errorf("%s accent = %s, want the D-016 teal %s", scheme, vars["accent"], want[scheme])
		}
		for _, k := range []string{"fg", "accent"} {
			if r := contrast(t, vars[k], vars["bg"]); r < 4.5 {
				t.Errorf("%s --%s %s on %s is %.2f:1, below WCAG AA 4.5:1", scheme, k, vars[k], vars["bg"], r)
			}
		}
	}
}
