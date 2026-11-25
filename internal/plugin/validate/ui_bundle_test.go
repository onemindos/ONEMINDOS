// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"golang.org/x/sys/unix"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func uiBundle(t *testing.T) string {
	t.Helper()
	root := bundle(t)
	must(t, os.WriteFile(filepath.Join(root, "onemind.app.yaml"), uiManifest(t, uiDeclarations, false), 0600))
	must(t, os.MkdirAll(filepath.Join(root, "ui", "assets"), 0700))
	for name, content := range map[string]string{
		"ui/index.html":        `<html><body><script src="assets/app.js"></script></body></html>`,
		"ui/assets/app.js":     `console.log("local UI");`,
		"ui/icon.svg":          `<svg/>`,
		"settings.schema.json": `{"type":"object","properties":{"greeting":{"type":"string"}},"additionalProperties":false}`,
	} {
		must(t, os.WriteFile(filepath.Join(root, name), []byte(content), 0600))
	}
	return root
}

func TestUIBundle(t *testing.T) {
	if err := Directory(uiBundle(t)); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name   string
		change func(*testing.T, string)
	}{
		{"missing entry", func(t *testing.T, r string) { must(t, os.Remove(filepath.Join(r, "ui/index.html"))) }},
		{"entry symlink", func(t *testing.T, r string) {
			p := filepath.Join(r, "ui/index.html")
			must(t, os.Remove(p))
			must(t, os.Symlink("assets/app.js", p))
		}},
		{"UI root symlink", func(t *testing.T, r string) {
			p := filepath.Join(r, "ui")
			must(t, os.Rename(p, p+".real"))
			must(t, os.Symlink(p+".real", p))
		}},
		{"unreferenced FIFO", func(t *testing.T, r string) { must(t, unix.Mkfifo(filepath.Join(r, "ui/pipe"), 0600)) }},
		{"unreferenced symlink", func(t *testing.T, r string) { must(t, os.Symlink(t.TempDir(), filepath.Join(r, "ui/unreferenced"))) }},
		{"missing settings", func(t *testing.T, r string) { must(t, os.Remove(filepath.Join(r, "settings.schema.json"))) }},
		{"settings symlink", func(t *testing.T, r string) {
			p := filepath.Join(r, "settings.schema.json")
			must(t, os.Rename(p, p+".real"))
			must(t, os.Symlink(p+".real", p))
		}},
		{"invalid settings schema", func(t *testing.T, r string) { writeUI(t, r, "settings.schema.json", `{"type":"imaginary"}`) }},
		{"remote settings reference", func(t *testing.T, r string) {
			writeUI(t, r, "settings.schema.json", `{"$ref":"https://example.com/schema"}`)
		}},
		{"local file settings reference", func(t *testing.T, r string) { writeUI(t, r, "settings.schema.json", `{"$ref":"file:///tmp/schema"}`) }},
		{"oversized settings", func(t *testing.T, r string) {
			writeUI(t, r, "settings.schema.json", strings.Repeat(" ", MaxManifestBytes+1))
		}},
		{"missing tile icon", func(t *testing.T, r string) { must(t, os.Remove(filepath.Join(r, "ui/icon.svg"))) }},
		{"script symlink", func(t *testing.T, r string) {
			p := filepath.Join(r, "ui/assets/app.js")
			must(t, os.Remove(p))
			must(t, os.Symlink(filepath.Join(r, "icon.svg"), p))
		}},
		{"missing local script", func(t *testing.T, r string) { must(t, os.Remove(filepath.Join(r, "ui/assets/app.js"))) }},
		{"unreferenced hostile HTML", func(t *testing.T, r string) { writeUI(t, r, "ui/unused.HTML", `<button onclick="run()">Hi</button>`) }},
		{"unreferenced hostile SVG", func(t *testing.T, r string) { writeUI(t, r, "ui/unused.svg", `<svg onload="run()"/>`) }},
		{"oversized UI file", func(t *testing.T, r string) { writeUI(t, r, "ui/large.js", strings.Repeat("x", maxUIFileBytes+1)) }},
		{"entry without HTML suffix", func(t *testing.T, r string) {
			rewrite(t, r, "entry: ui/index.html", "entry: ui/widget.txt")
			writeUI(t, r, "ui/widget.txt", `<script src="https://evil.example/x.js"></script>`)
		}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := uiBundle(t)
			c.change(t, r)
			if err := Directory(r); err == nil {
				t.Fatal("accepted unsafe UI bundle")
			}
		})
	}
}

func TestUIMarkup(t *testing.T) {
	tests := []struct {
		name, markup string
		valid        bool
	}{
		{"UTF-16 markup", "\xff\xfe<\x00s\x00c\x00r\x00i\x00p\x00t\x00>", false},
		{"local script", `<script src="assets/app.js"></script>`, true},
		{"local script case", `<SCRIPT SRC="assets/app.js"></SCRIPT>`, true},
		{"comments", `<!-- <script src="https://example.com/x.js"></script> -->`, true},
		{"plain markup", `<button data-action="show">Hello</button>`, true},
		{"SVG href scripts refused", `<svg><script xlink:href="assets/app.js"/></svg>`, false},
		{"remote HTTPS", `<script src="https://example.com/x.js"></script>`, false},
		{"protocol relative", `<script src="//example.com/x.js"></script>`, false},
		{"entity remote", `<script src="&#x2f;&#x2f;example.com/x.js"></script>`, false},
		{"data URL", `<script src="data:text/javascript,run()"></script>`, false},
		{"javascript URL", `<script src="javascript:run()"></script>`, false},
		{"root relative", `<script src="/assets/app.js"></script>`, false},
		{"traversal", `<script src="../icon.svg"></script>`, false},
		{"encoded traversal", `<script src="%2e%2e/icon.svg"></script>`, false},
		{"backslash", `<script src="assets\app.js"></script>`, false},
		{"query", `<script src="assets/app.js?version=1"></script>`, false},
		{"fragment", `<script src="assets/app.js#x"></script>`, false},
		{"src does not excuse inline content", `<script src="assets/app.js">run()</script>`, false},
		{"SVG src with inline content", `<svg><script src="assets/app.js">run()</script></svg>`, false},
		{"inline script", `<script>run()</script>`, false},
		{"empty script src", `<script src=""></script>`, false},
		{"inline handler", `<button onClick="run()">Hello</button>`, false},
		{"SVG handler", `<svg><a onload="run()"/></svg>`, false},
		{"SVG remote script", `<svg><script xlink:href="https://example.com/x.js"/></svg>`, false},
		{"XML prefix remote script", `<svg:script xlink:href="https://example.com/x.js"/>`, false},
		{"base URL", `<base href="https://example.com/"><script src="assets/app.js"></script>`, false},
		{"srcdoc", `<iframe srcdoc="&lt;script&gt;run()&lt;/script&gt;"></iframe>`, false},
		{"duplicate src uses first like HTML", `<script src="assets/app.js" src="https://example.com/x.js"></script>`, true},
		{"duplicate src remote first", `<script src="https://example.com/x.js" src="assets/app.js"></script>`, false},
	}
	root := uiBundle(t)
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := scanUIMarkup(root, "ui/index.html", []byte(tt.markup))
			if (err == nil) != tt.valid {
				t.Fatalf("valid=%v: %v", tt.valid, err)
			}
		})
	}
}

func writeUI(t *testing.T, root, name, content string) {
	t.Helper()
	must(t, os.WriteFile(filepath.Join(root, name), []byte(content), 0600))
}

func TestUIBundleNoDeclaredUIStillScanned(t *testing.T) {
	root := bundle(t)
	must(t, os.Mkdir(filepath.Join(root, "ui"), 0700))
	writeUI(t, root, "ui/unused.htm", `<script src="https://example.com/x.js"></script>`)
	if err := Directory(root); err == nil {
		t.Fatal("unreferenced UI directory escaped scanning")
	}
}

func TestUISettingsSelfContainedSchema(t *testing.T) {
	root := uiBundle(t)
	writeUI(t, root, "settings.schema.json", `{"type":"object","properties":{"name":{"$ref":"#/$defs/name"}},"$defs":{"name":{"type":"string"}}}`)
	if err := Directory(root); err != nil {
		t.Fatal(err)
	}
	// Strip all UI declarations except settings to prove no ui/ tree is required.
	data, err := os.ReadFile(filepath.Join(root, "onemind.app.yaml"))
	must(t, err)
	var value map[string]any
	must(t, yaml.Unmarshal(data, &value))
	ext := value["spec"].(map[string]any)["extensions"].(map[string]any)
	delete(ext, "widgets")
	delete(ext, "tiles")
	delete(ext, "alerts")
	data, err = yaml.Marshal(value)
	must(t, err)
	must(t, os.WriteFile(filepath.Join(root, "onemind.app.yaml"), data, 0600))
	must(t, os.Rename(filepath.Join(root, "ui"), filepath.Join(root, "unused-ui")))
	if err := Directory(root); err != nil {
		t.Fatal(err)
	}
}

func TestUIBundleTotalSizeLimit(t *testing.T) {
	root := uiBundle(t)
	for i := 0; i < 9; i++ {
		f, err := os.Create(filepath.Join(root, "ui", fmt.Sprintf("large-%d.bin", i)))
		must(t, err)
		must(t, f.Truncate(maxUIFileBytes))
		must(t, f.Close())
	}
	if err := Directory(root); err == nil || !strings.Contains(err.Error(), "UI tree exceeds") {
		t.Fatalf("expected total size limit: %v", err)
	}
}

func TestRootMarkupIcons(t *testing.T) {
	for _, markup := range []string{`<svg onload="run()"/>`, `<svg><script xlink:href="https://example.com/x.js"/></svg>`} {
		root := bundle(t)
		writeUI(t, root, "icon.svg", markup)
		if err := Directory(root); err == nil {
			t.Fatal("root metadata SVG escaped scanning")
		}
	}
	root := uiBundle(t)
	rewrite(t, root, "icon: ui/icon.svg", "icon: tile.svg")
	writeUI(t, root, "tile.svg", `<svg onclick="run()"/>`)
	if err := Directory(root); err == nil {
		t.Fatal("root tile SVG escaped scanning")
	}
	writeUI(t, root, "tile.svg", `<svg/>`)
	if err := Directory(root); err != nil {
		t.Fatal(err)
	}
}

func TestUIBundleEntryLimit(t *testing.T) {
	root := uiBundle(t)
	for i := 0; i < maxUIEntries; i++ {
		must(t, os.Mkdir(filepath.Join(root, "ui", fmt.Sprintf("entry-%04d", i)), 0700))
	}
	if err := Directory(root); err == nil || !strings.Contains(err.Error(), "entries") {
		t.Fatalf("expected entry limit: %v", err)
	}
}
