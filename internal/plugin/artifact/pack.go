// SPDX-License-Identifier: Apache-2.0

// Package artifact builds local OCI plugin layouts. A digest proves content,
// not publisher identity: signing, scans and owner approval remain separate.
package artifact

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"gopkg.in/yaml.v3"
)

const Type = "application/vnd.onemind.plugin.v1"
const ManifestType = "application/vnd.oci.image.manifest.v1+json"

type Descriptor struct {
	MediaType   string            `json:"mediaType"`
	Digest      string            `json:"digest"`
	Size        int64             `json:"size"`
	Annotations map[string]string `json:"annotations,omitempty"`
}
type Manifest struct {
	SchemaVersion int          `json:"schemaVersion"`
	MediaType     string       `json:"mediaType"`
	ArtifactType  string       `json:"artifactType"`
	Config        Descriptor   `json:"config"`
	Layers        []Descriptor `json:"layers"`
}
type Index struct {
	SchemaVersion int          `json:"schemaVersion"`
	MediaType     string       `json:"mediaType"`
	Manifests     []Descriptor `json:"manifests"`
}

// Pack publishes a new local OCI directory. It never runs container builds,
// resolves mutable image tags, reads arbitrary root files or replaces a path.
func Pack(directory, output string) (string, error) {
	root, err := filepath.Abs(directory)
	if err != nil {
		return "", err
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return "", err
	}
	if err = validate.Directory(root); err != nil {
		return "", err
	}
	if output == "" {
		output = root + ".oci"
	}
	output, err = filepath.Abs(output)
	if err != nil {
		return "", err
	}
	parent, err := filepath.EvalSymlinks(filepath.Dir(output))
	if err != nil {
		return "", err
	}
	output = filepath.Join(parent, filepath.Base(output))
	if rel, e := filepath.Rel(root, output); e == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("OCI output must be outside the source bundle")
	}
	config, err := read(root, "onemind.app.yaml", validate.MaxManifestBytes)
	if err != nil {
		return "", err
	}
	if err = validate.Manifest(config); err != nil {
		return "", err
	}
	var doc struct {
		Metadata struct{ ID, Version, Icon string }
		Spec     struct {
			Manifests  string
			Extensions struct {
				Settings struct{ Schema string }
				Tiles    []struct{ Icon string }
			}
		}
	}
	if err = yaml.Unmarshal(config, &doc); err != nil {
		return "", err
	}
	blobs := map[string][]byte{}
	add := func(media string, data []byte) Descriptor {
		sum := sha256.Sum256(data)
		digest := "sha256:" + hex.EncodeToString(sum[:])
		blobs[digest] = data
		return Descriptor{MediaType: media, Digest: digest, Size: int64(len(data))}
	}
	layers := []Descriptor{}
	workloadPaths := map[string]bool{}
	if doc.Spec.Manifests != "" {
		paths, e := tree(root, doc.Spec.Manifests)
		if e != nil {
			return "", e
		}
		for _, name := range paths {
			workloadPaths[filepath.Clean(name)] = true
		}
		data, e := archive(root, paths)
		if e != nil {
			return "", e
		}
		layers = append(layers, add("application/vnd.onemind.plugin.manifests.v1.tar+gzip", data))
	}
	paths := []string{doc.Metadata.Icon}
	if doc.Spec.Extensions.Settings.Schema != "" {
		paths = append(paths, doc.Spec.Extensions.Settings.Schema)
	}
	for _, tile := range doc.Spec.Extensions.Tiles {
		if tile.Icon != "" {
			paths = append(paths, tile.Icon)
		}
	}
	if _, e := os.Lstat(filepath.Join(root, "ui")); !os.IsNotExist(e) {
		ui, e := tree(root, "ui")
		if e != nil {
			return "", e
		}
		paths = append(paths, ui...)
	}
	uiPaths := []string{}
	for _, name := range paths {
		if !workloadPaths[filepath.Clean(name)] {
			uiPaths = append(uiPaths, name)
		}
	}
	data, err := archive(root, uiPaths)
	if err != nil {
		return "", err
	}
	layers = append(layers, add("application/vnd.onemind.plugin.ui.v1.tar+gzip", data))
	readme, err := read(root, "README.md", 4<<20)
	if err != nil {
		return "", fmt.Errorf("README layer: %w", err)
	}
	layers = append(layers, add("text/markdown", readme))
	manifest, err := json.Marshal(Manifest{SchemaVersion: 2, MediaType: ManifestType, ArtifactType: Type,
		Config: add("application/vnd.onemind.app.manifest.v1+yaml", config), Layers: layers})
	if err != nil {
		return "", err
	}
	desc := add(ManifestType, manifest)
	desc.Annotations = map[string]string{"org.opencontainers.image.ref.name": doc.Metadata.ID, "org.opencontainers.image.version": doc.Metadata.Version}
	index, err := json.Marshal(Index{SchemaVersion: 2, MediaType: "application/vnd.oci.image.index.v1+json", Manifests: []Descriptor{desc}})
	if err != nil {
		return "", err
	}
	files := map[string][]byte{"oci-layout": []byte("{\"imageLayoutVersion\":\"1.0.0\"}\n"), "index.json": index}
	for digest, content := range blobs {
		files["blobs/sha256/"+strings.TrimPrefix(digest, "sha256:")] = content
	}
	if err = publish(output, files); err != nil {
		return "", err
	}
	return desc.Digest, nil
}

func read(root, relative string, maximum int64) ([]byte, error) {
	if relative == "" || strings.Contains(relative, "\\") || filepath.IsAbs(relative) {
		return nil, fmt.Errorf("invalid bundle path")
	}
	clean := filepath.Clean(relative)
	if clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return nil, fmt.Errorf("path escapes bundle")
	}
	path := root
	for _, part := range strings.Split(clean, string(filepath.Separator)) {
		path = filepath.Join(path, part)
		info, err := os.Lstat(path)
		if err != nil {
			return nil, err
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return nil, fmt.Errorf("symlink in bundle")
		}
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	info, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("bundle entry is not regular")
	}
	data, err := io.ReadAll(io.LimitReader(f, maximum+1))
	if int64(len(data)) > maximum {
		return nil, fmt.Errorf("bundle entry exceeds size limit")
	}
	return data, err
}
func tree(root, relative string) ([]string, error) {
	directory := filepath.Join(root, relative)
	info, err := os.Lstat(directory)
	if err != nil {
		return nil, err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return nil, fmt.Errorf("payload root must be a directory")
	}
	paths := []string{}
	count := 0
	err = filepath.WalkDir(directory, func(path string, d fs.DirEntry, e error) error {
		if e != nil {
			return e
		}
		count++
		if count > 4096 {
			return fmt.Errorf("payload has too many entries")
		}
		if d.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symlink in payload")
		}
		if !d.IsDir() && !d.Type().IsRegular() {
			return fmt.Errorf("special file in payload")
		}
		rel, e := filepath.Rel(root, path)
		if e != nil {
			return e
		}
		paths = append(paths, rel)
		return nil
	})
	return paths, err
}
func archive(root string, paths []string) ([]byte, error) {
	canonical := make([]string, 0, len(paths))
	for _, name := range paths {
		canonical = append(canonical, filepath.Clean(name))
	}
	paths = canonical
	sort.Strings(paths)
	var buffer bytes.Buffer
	zipped := gzip.NewWriter(&buffer)
	zipped.Header.OS = 255
	writer := tar.NewWriter(zipped)
	last := ""
	var total int64
	for _, path := range paths {
		if path == last {
			continue
		}
		last = path
		info, err := os.Lstat(filepath.Join(root, path))
		if err != nil {
			return nil, err
		}
		if info.IsDir() {
			header := &tar.Header{Name: filepath.ToSlash(path) + "/", Typeflag: tar.TypeDir, Mode: 0755, ModTime: time.Unix(0, 0), Format: tar.FormatPAX}
			if err := writer.WriteHeader(header); err != nil {
				return nil, err
			}
			continue
		}
		data, err := read(root, path, 8<<20)
		if err != nil {
			return nil, err
		}
		total += int64(len(data))
		if total > 64<<20 {
			return nil, fmt.Errorf("payload exceeds size limit")
		}
		header := &tar.Header{Name: filepath.ToSlash(filepath.Clean(path)), Mode: 0644, Size: int64(len(data)), ModTime: time.Unix(0, 0), Format: tar.FormatPAX}
		if err = writer.WriteHeader(header); err != nil {
			return nil, err
		}
		if _, err = writer.Write(data); err != nil {
			return nil, err
		}
	}
	if err := writer.Close(); err != nil {
		return nil, err
	}
	if err := zipped.Close(); err != nil {
		return nil, err
	}
	return buffer.Bytes(), nil
}
func publish(output string, files map[string][]byte) error {
	if err := os.Mkdir(output, 0755); err != nil {
		return fmt.Errorf("OCI destination must not exist: %w", err)
	}
	created := []string{}
	dirs := []string{}
	success := false
	defer func() {
		if !success {
			for _, p := range created {
				_ = os.Remove(p)
			}
			for i := len(dirs) - 1; i >= 0; i-- {
				_ = os.Remove(dirs[i])
			}
			_ = os.Remove(output)
		}
	}()
	for _, sub := range []string{"blobs", "blobs/sha256"} {
		p := filepath.Join(output, sub)
		if err := os.Mkdir(p, 0755); err != nil {
			return err
		}
		dirs = append(dirs, p)
	}
	for name, data := range files {
		path := filepath.Join(output, name)
		f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0644)
		if err != nil {
			return err
		}
		created = append(created, path)
		_, writeErr := f.Write(data)
		closeErr := f.Close()
		if writeErr != nil {
			return writeErr
		}
		if closeErr != nil {
			return closeErr
		}
	}
	success = true
	return nil
}
