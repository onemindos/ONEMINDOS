// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"bytes"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path"
	"path/filepath"
	"strings"
	"unicode/utf8"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"golang.org/x/net/html"
)

const (
	maxUIFileBytes   = 4 << 20
	maxUIBundleBytes = 32 << 20
	maxUIEntries     = 4096
)

// validateUIBundle checks a quiescent unpacked tree after Manifest validation.
// It parses markup, not JavaScript: runtime CSP, sandboxing and scans still apply.
func validateUIBundle(root string, metadata, spec map[string]any) error {
	ext := spec["extensions"].(map[string]any)
	markup := map[string]bool{}
	if widgets, ok := ext["widgets"].([]any); ok {
		for _, raw := range widgets {
			widget := raw.(map[string]any)
			if widget["render"] != "iframe" {
				continue
			}
			entry := widget["entry"].(string)
			if !strings.HasPrefix(entry, "ui/") {
				return fmt.Errorf("iframe entry must be below ui/")
			}
			if _, err := bundlePath(root, entry, false); err != nil {
				return fmt.Errorf("iframe entry: %w", err)
			}
			markup[entry] = true // Parse entries regardless of their filename extension.
		}
	}
	entries, total := 0, int64(0)
	checked := map[string]bool{}
	checkFile := func(relative string) error {
		if checked[relative] {
			return nil
		}
		checked[relative] = true
		filename, err := bundlePath(root, relative, false)
		if err != nil {
			return err
		}
		info, err := os.Lstat(filename)
		if err != nil {
			return err
		}
		entries++
		if entries > maxUIEntries {
			return fmt.Errorf("UI layer exceeds %d entries", maxUIEntries)
		}
		if info.Size() > maxUIFileBytes {
			return fmt.Errorf("UI file exceeds %d bytes", maxUIFileBytes)
		}
		total += info.Size()
		if total > maxUIBundleBytes {
			return fmt.Errorf("UI tree exceeds %d bytes", maxUIBundleBytes)
		}
		suffix := strings.ToLower(filepath.Ext(filename))
		if !markup[relative] && suffix != ".html" && suffix != ".htm" && suffix != ".svg" && suffix != ".xhtml" {
			return nil
		}
		data, err := readUIFile(filename, maxUIFileBytes)
		if err != nil {
			return err
		}
		if err := scanUIMarkup(root, relative, data); err != nil {
			return fmt.Errorf("%s: %w", relative, err)
		}
		return nil
	}
	if err := checkFile(metadata["icon"].(string)); err != nil {
		return fmt.Errorf("metadata.icon: %w", err)
	}

	if settings, ok := ext["settings"].(map[string]any); ok {
		schemaRelative := settings["schema"].(string)
		if err := checkFile(schemaRelative); err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
		schemaPath, err := bundlePath(root, schemaRelative, false)
		if err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
		data, err := readUIFile(schemaPath, MaxManifestBytes)
		if err != nil {
			return err
		}
		doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
		if err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
		c := compiler()
		const location = "https://onemind.invalid/settings"
		if err := c.AddResource(location, doc); err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
		if _, err := c.Compile(location); err != nil {
			return fmt.Errorf("settings.schema: %w", err)
		}
	}
	if tiles, ok := ext["tiles"].([]any); ok {
		for _, raw := range tiles {
			tile := raw.(map[string]any)
			if icon, ok := tile["icon"].(string); ok {
				if err := checkFile(icon); err != nil {
					return fmt.Errorf("tile icon: %w", err)
				}
			}
		}
	}
	if _, err := os.Lstat(filepath.Join(root, "ui")); os.IsNotExist(err) {
		return nil
	} else if err != nil {
		return err
	}
	ui, err := bundlePath(root, "ui", true)
	if err != nil {
		return fmt.Errorf("UI root: %w", err)
	}
	return filepath.WalkDir(ui, func(filename string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}

		info, err := entry.Info()
		if err != nil {
			return err
		}
		if info.IsDir() {
			entries++
			if entries > maxUIEntries {
				return fmt.Errorf("UI layer exceeds %d entries", maxUIEntries)
			}
			return nil
		}
		if !info.Mode().IsRegular() {
			return fmt.Errorf("UI tree contains symlink or special file: %s", entry.Name())
		}

		relative, err := filepath.Rel(root, filename)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		return checkFile(relative)
	})
}

func readUIFile(filename string, limit int64) ([]byte, error) {
	f, err := os.Open(filename)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, limit+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > limit {
		return nil, fmt.Errorf("UI document exceeds %d bytes", limit)
	}
	return data, nil
}

func scanUIMarkup(root, relative string, data []byte) error {
	if !utf8.Valid(data) || bytes.IndexByte(data, 0) >= 0 {
		return fmt.Errorf("UI markup must be UTF-8 without NUL bytes")
	}
	tokenizer := html.NewTokenizer(bytes.NewReader(data))
	tokenizer.SetMaxBuf(maxUIFileBytes)
	inScript := false
	for {
		kind := tokenizer.Next()
		if kind == html.ErrorToken {
			if err := tokenizer.Err(); err != io.EOF {
				return err
			}
			return nil
		}
		if kind == html.TextToken && inScript && len(bytes.TrimSpace(tokenizer.Text())) != 0 {
			return fmt.Errorf("inline script content is forbidden")
		}
		if kind == html.EndTagToken && localMarkupName(tokenizer.Token().Data) == "script" {
			inScript = false
		}
		if kind != html.StartTagToken && kind != html.SelfClosingTagToken {
			continue
		}
		token := tokenizer.Token()
		tag := localMarkupName(token.Data)
		if tag == "base" {
			return fmt.Errorf("base elements are forbidden")
		}
		if tag == "script" && strings.Contains(token.Data, ":") {
			return fmt.Errorf("namespaced script elements are forbidden")
		}
		scriptSource := false
		for _, attr := range token.Attr {
			key := localMarkupName(attr.Key)
			if key == "srcdoc" {
				return fmt.Errorf("embedded srcdoc markup is forbidden")
			}
			if strings.HasPrefix(key, "on") {
				return fmt.Errorf("inline event handler %q is forbidden", key)
			}
			if tag != "script" || (key != "src" && key != "href") {
				continue
			}
			if key == "href" {
				return fmt.Errorf("SVG/href script elements are forbidden; use an HTML local src script")
			}
			scriptSource = true
			// Tokenizer decodes HTML entities first. Allow only literal relative paths;
			// URLs, absolute paths, queries and encoded traversal cannot reach the host.
			if err := uiPath(attr.Val); err != nil {
				return fmt.Errorf("script source: %w", err)
			}
			resolved := path.Join(path.Dir(relative), attr.Val)
			if !strings.HasPrefix(resolved, "ui/") {
				return fmt.Errorf("script source escapes ui/")
			}
			if _, err := bundlePath(root, resolved, false); err != nil {
				return fmt.Errorf("script source: %w", err)
			}
		}
		if tag == "script" {
			inScript = true
		}
		if tag == "script" && !scriptSource {
			return fmt.Errorf("inline scripts are forbidden; use a local UI script file")
		}
	}
}

func localMarkupName(name string) string {
	name = strings.ToLower(name)
	if colon := strings.LastIndexByte(name, ':'); colon >= 0 {
		return name[colon+1:]
	}
	return name
}
