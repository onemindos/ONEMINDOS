// SPDX-License-Identifier: Apache-2.0

package artifact

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/google/go-containerregistry/pkg/v1/layout"
	"github.com/onemindos/onemindos/internal/plugin/scaffold"
	"gopkg.in/yaml.v3"
)

func source(t *testing.T) string {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "example")
	if err := scaffold.Create(dir, "example", "settings", "https://example.invalid/source"); err != nil {
		t.Fatal(err)
	}
	return dir
}
func blob(t *testing.T, dir string, d Descriptor) []byte {
	t.Helper()
	data, err := os.ReadFile(filepath.Join(dir, "blobs/sha256", strings.TrimPrefix(d.Digest, "sha256:")))
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(data)
	if d.Size != int64(len(data)) || d.Digest != "sha256:"+hex.EncodeToString(sum[:]) {
		t.Fatal("OCI descriptor does not match bytes")
	}
	return data
}
func manifest(t *testing.T, dir string) Manifest {
	t.Helper()
	var index Index
	indexBytes, err := os.ReadFile(filepath.Join(dir, "index.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(indexBytes, &index); err != nil {
		t.Fatal(err)
	}
	if index.SchemaVersion != 2 || len(index.Manifests) != 1 || index.Manifests[0].Annotations["org.opencontainers.image.ref.name"] != "example" {
		t.Fatal("invalid OCI index")
	}
	var m Manifest
	if err = json.Unmarshal(blob(t, dir, index.Manifests[0]), &m); err != nil {
		t.Fatal(err)
	}
	if m.ArtifactType != Type || m.MediaType != ManifestType || m.SchemaVersion != 2 {
		t.Fatal("invalid plugin artifact manifest")
	}
	return m
}
func TestPackProducesDeterministicContentAddressedLayout(t *testing.T) {
	src := source(t)
	one, two := filepath.Join(t.TempDir(), "one"), filepath.Join(t.TempDir(), "two")
	first, err := Pack(src, one)
	if err != nil {
		t.Fatal(err)
	}
	second, err := Pack(src, two)
	if err != nil {
		t.Fatal(err)
	}
	if first != second {
		t.Fatal("packing identical input changed digest")
	}
	m := manifest(t, one)
	if m.Config.MediaType != "application/vnd.onemind.app.manifest.v1+yaml" || len(m.Layers) != 2 {
		t.Fatal("wrong plugin config/layers")
	}
	data, err := os.ReadFile(filepath.Join(src, "onemind.app.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(blob(t, one, m.Config), data) {
		t.Fatal("configuration bytes changed")
	}
	for _, layer := range m.Layers {
		blob(t, one, layer)
	}
	if err = os.WriteFile(filepath.Join(src, "settings.schema.json"), []byte(`{"type":"object","description":"changed"}`), 0600); err != nil {
		t.Fatal(err)
	}
	third, err := Pack(src, filepath.Join(t.TempDir(), "three"))
	if err != nil {
		t.Fatal(err)
	}
	if first == third {
		t.Fatal("payload change did not alter digest")
	}
}
func TestPackExcludesUnreferencedRootDataAndNormalizesArchiveMetadata(t *testing.T) {
	src := source(t)
	if err := os.WriteFile(filepath.Join(src, "private.env"), []byte("local data not for publication"), 0600); err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "oci")
	if _, err := Pack(src, output); err != nil {
		t.Fatal(err)
	}
	m := manifest(t, output)
	zip, err := gzip.NewReader(bytes.NewReader(blob(t, output, m.Layers[0])))
	if err != nil {
		t.Fatal(err)
	}
	defer zip.Close()
	reader := tar.NewReader(zip)
	names := []string{}
	for {
		h, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if h.Mode != 0644 || h.Uid != 0 || h.Gid != 0 || h.ModTime.Unix() != 0 || strings.HasPrefix(h.Name, "/") || strings.Contains(h.Name, "..") {
			t.Fatalf("unsafe or variable archive header: %+v", h)
		}
		names = append(names, h.Name)
	}
	if strings.Join(names, ",") != "icon.svg,settings.schema.json" {
		t.Fatalf("unexpected UI payload: %v", names)
	}
}
func TestPackRefusesExistingOutputAndOutputWithinSource(t *testing.T) {
	src := source(t)
	out := t.TempDir()
	marker := filepath.Join(out, "keep")
	if err := os.WriteFile(marker, []byte("user data"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Pack(src, out); err == nil {
		t.Fatal("existing directory overwritten")
	}
	data, err := os.ReadFile(marker)
	if err != nil || string(data) != "user data" {
		t.Fatal("existing data lost")
	}
	if _, err := Pack(src, filepath.Join(src, "oci")); err == nil {
		t.Fatal("output allowed within source")
	}
	if err = os.Symlink(src, filepath.Join(src, "ui")); err != nil {
		t.Fatal(err)
	}
	if _, err := Pack(src, filepath.Join(t.TempDir(), "new")); err == nil {
		t.Fatal("symlink source accepted")
	}
}

func TestOCIConsumerReadsProducedLayout(t *testing.T) {
	output := filepath.Join(t.TempDir(), "oci")
	if _, err := Pack(source(t), output); err != nil {
		t.Fatal(err)
	}
	path, err := layout.FromPath(output)
	if err != nil {
		t.Fatal(err)
	}
	index, err := path.ImageIndex()
	if err != nil {
		t.Fatal(err)
	}
	description, err := index.IndexManifest()
	if err != nil {
		t.Fatal(err)
	}
	if len(description.Manifests) != 1 {
		t.Fatal("OCI consumer found no artifact")
	}
	image, err := index.Image(description.Manifests[0].Digest)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := image.RawManifest()
	if err != nil {
		t.Fatal(err)
	}
	var doc Manifest
	if err := json.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	if doc.ArtifactType != Type {
		t.Fatal("OCI consumer read wrong artifact type")
	}
}

func TestPayloadDirectoriesAndCanonicalLayerPartition(t *testing.T) {
	src := source(t)
	if err := os.MkdirAll(filepath.Join(src, "manifests/empty"), 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(src, "manifests/icon.svg"), []byte("<svg/>"), 0600); err != nil {
		t.Fatal(err)
	}
	raw, err := os.ReadFile(filepath.Join(src, "onemind.app.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var doc map[string]any
	if err = yaml.Unmarshal(raw, &doc); err != nil {
		t.Fatal(err)
	}
	doc["spec"].(map[string]any)["manifests"] = "manifests"
	doc["metadata"].(map[string]any)["icon"] = "./manifests/icon.svg"
	raw, err = json.Marshal(doc)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(src, "onemind.app.yaml"), raw, 0600); err != nil {
		t.Fatal(err)
	}
	output := filepath.Join(t.TempDir(), "oci")
	if _, err = Pack(src, output); err != nil {
		t.Fatal(err)
	}
	m := manifest(t, output)
	seen := map[string]int{}
	for _, layer := range m.Layers {
		if !strings.HasSuffix(layer.MediaType, "tar+gzip") {
			continue
		}
		zip, err := gzip.NewReader(bytes.NewReader(blob(t, output, layer)))
		if err != nil {
			t.Fatal(err)
		}
		reader := tar.NewReader(zip)
		for {
			header, err := reader.Next()
			if err == io.EOF {
				break
			}
			if err != nil {
				t.Fatal(err)
			}
			seen[header.Name]++
		}
		zip.Close()
	}
	if seen["manifests/empty/"] != 1 || seen["manifests/icon.svg"] != 1 {
		t.Fatalf("directories lost or overlapping file duplicated: %v", seen)
	}
}
