// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func packed(t *testing.T) (string, string) {
	t.Helper()
	output := filepath.Join(t.TempDir(), "oci")
	digest, err := Pack(source(t), output)
	if err != nil {
		t.Fatal(err)
	}
	return output, digest
}
func TestOpenUsesExactDigestAndValidatesExtractedBundle(t *testing.T) {
	output, digest := packed(t)
	if err := os.WriteFile(filepath.Join(output, "index.json"), []byte("mutable index is ignored"), 0600); err != nil {
		t.Fatal(err)
	}
	b, err := Open(output, digest)
	if err != nil {
		t.Fatal(err)
	}
	if b.ID != "example" || b.Version != "0.1.0" || b.Digest != digest {
		t.Fatal("wrong artifact identity")
	}
	extracted := b.Directory
	if err = b.Close(); err != nil {
		t.Fatal(err)
	}
	if _, err = os.Stat(extracted); !os.IsNotExist(err) {
		t.Fatal("extracted files leaked after close")
	}
}
func TestOpenRejectsBlobTamperingTagsAndSymlinks(t *testing.T) {
	output, digest := packed(t)
	if _, err := Open(output, "latest"); err == nil {
		t.Fatal("mutable reference accepted")
	}
	m := manifest(t, output)
	config := filepath.Join(output, "blobs/sha256", strings.TrimPrefix(m.Config.Digest, "sha256:"))
	if err := os.WriteFile(config, []byte("tampered"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(output, digest); err == nil {
		t.Fatal("modified blob accepted")
	}
	output, digest = packed(t)
	blobDir := filepath.Join(output, "blobs")
	if err := os.Rename(blobDir, blobDir+"-original"); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(blobDir+"-original", blobDir); err != nil {
		t.Fatal(err)
	}
	if _, err := Open(output, digest); err == nil {
		t.Fatal("blob directory symlink accepted")
	}
}
func replaceUI(t *testing.T, output string, payload []byte) string {
	t.Helper()
	m := manifest(t, output)
	write := func(media string, data []byte) Descriptor {
		sum := sha256.Sum256(data)
		hash := hex.EncodeToString(sum[:])
		if err := os.WriteFile(filepath.Join(output, "blobs/sha256", hash), data, 0600); err != nil {
			t.Fatal(err)
		}
		return Descriptor{MediaType: media, Digest: "sha256:" + hash, Size: int64(len(data))}
	}
	m.Layers[0] = write(m.Layers[0].MediaType, payload)
	raw, err := json.Marshal(m)
	if err != nil {
		t.Fatal(err)
	}
	return write(ManifestType, raw).Digest
}
func archiveHeader(t *testing.T, h *tar.Header, duplicate, trailing bool) []byte {
	t.Helper()
	var buffer bytes.Buffer
	zip := gzip.NewWriter(&buffer)
	writer := tar.NewWriter(zip)
	if err := writer.WriteHeader(h); err != nil {
		t.Fatal(err)
	}
	if h.Size > 0 && h.Size < 1024 {
		if _, err := writer.Write(make([]byte, h.Size)); err != nil {
			t.Fatal(err)
		}
	}
	if duplicate {
		if err := writer.WriteHeader(h); err != nil {
			t.Fatal(err)
		}
	}
	if h.Size < 1024 {
		if err := writer.Close(); err != nil {
			t.Fatal(err)
		}
	}
	if trailing {
		if _, err := zip.Write([]byte("unapproved trailing bytes")); err != nil {
			t.Fatal(err)
		}
	}
	if err := zip.Close(); err != nil {
		t.Fatal(err)
	}
	return buffer.Bytes()
}
func TestOpenRejectsConsistentlyHashedHostileArchives(t *testing.T) {
	outside := filepath.Join(t.TempDir(), "escaped")
	cases := []struct {
		name                string
		h                   *tar.Header
		duplicate, trailing bool
	}{
		{"parent", &tar.Header{Name: "../escape", Mode: 0600}, false, false},
		{"absolute", &tar.Header{Name: outside, Mode: 0600}, false, false},
		{"backslash", &tar.Header{Name: `..\escape`, Mode: 0600}, false, false},
		{"symlink", &tar.Header{Name: "ui/link", Typeflag: tar.TypeSymlink, Linkname: outside}, false, false},
		{"hardlink", &tar.Header{Name: "ui/link", Typeflag: tar.TypeLink, Linkname: "../../escape"}, false, false},
		{"special", &tar.Header{Name: "ui/device", Typeflag: tar.TypeChar}, false, false},
		{"reserved", &tar.Header{Name: "onemind.app.yaml", Mode: 0600}, false, false},
		{"duplicate", &tar.Header{Name: "ui/repeat", Mode: 0600}, true, false},
		{"oversized", &tar.Header{Name: "ui/large", Size: 9 << 20, Mode: 0600}, false, false},
		{"trailing", &tar.Header{Name: "ui/small", Mode: 0600}, false, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			output, _ := packed(t)
			digest := replaceUI(t, output, archiveHeader(t, c.h, c.duplicate, c.trailing))
			if b, err := Open(output, digest); err == nil {
				b.Close()
				t.Fatal("hostile archive accepted")
			}
		})
	}
	if _, err := os.Stat(outside); !os.IsNotExist(err) {
		t.Fatal("archive escaped private extraction directory")
	}
}

func TestRoundTripPreservesDirectoriesAndLayerAliases(t *testing.T) {
	for _, mode := range []string{"empty", "shared-icon", "alias-icon"} {
		t.Run(mode, func(t *testing.T) {
			src := source(t)
			if err := os.MkdirAll(filepath.Join(src, "manifests/empty"), 0700); err != nil {
				t.Fatal(err)
			}
			raw, err := os.ReadFile(filepath.Join(src, "onemind.app.yaml"))
			if err != nil {
				t.Fatal(err)
			}
			var doc map[string]any
			if err = json.Unmarshal(raw, &doc); err != nil {
				t.Fatal(err)
			}
			doc["spec"].(map[string]any)["manifests"] = "manifests"
			icon := ""
			if mode == "shared-icon" {
				icon = "manifests/icon.svg"
			}
			if mode == "alias-icon" {
				icon = "ui/icon.svg"
			}
			if icon != "" {
				if err = os.MkdirAll(filepath.Dir(filepath.Join(src, icon)), 0700); err != nil {
					t.Fatal(err)
				}
				if err = os.WriteFile(filepath.Join(src, icon), []byte("<svg/>"), 0600); err != nil {
					t.Fatal(err)
				}
				doc["metadata"].(map[string]any)["icon"] = "./" + icon
			}
			raw, err = json.Marshal(doc)
			if err != nil {
				t.Fatal(err)
			}
			if err = os.WriteFile(filepath.Join(src, "onemind.app.yaml"), raw, 0600); err != nil {
				t.Fatal(err)
			}
			output := filepath.Join(t.TempDir(), "oci")
			digest, err := Pack(src, output)
			if err != nil {
				t.Fatal(err)
			}
			bundle, err := Open(output, digest)
			if err != nil {
				t.Fatal(err)
			}
			defer bundle.Close()
			if info, err := os.Stat(filepath.Join(bundle.Directory, "manifests/empty")); err != nil || !info.IsDir() {
				t.Fatal("empty directory lost")
			}
		})
	}
}
