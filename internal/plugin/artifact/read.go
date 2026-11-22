// SPDX-License-Identifier: Apache-2.0

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
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"

	"github.com/onemindos/onemindos/internal/plugin/validate"
	"gopkg.in/yaml.v3"
)

var digestPattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// Bundle has verified content integrity and schema only. It conveys no publisher
// trust and must never authorize installation without the separate trust gates.
type Bundle struct {
	Directory string
	Digest    string
	ID        string
	Version   string
	Manifest  []byte
}

func (b *Bundle) Close() error { return os.RemoveAll(b.Directory) }

func decode(data []byte, value any) error {
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(value); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("trailing JSON data")
	}
	return nil
}
func checkedBlob(root string, d Descriptor, maximum int64) ([]byte, error) {
	if !digestPattern.MatchString(d.Digest) || d.Size < 0 || d.Size > maximum {
		return nil, fmt.Errorf("invalid or oversized OCI descriptor")
	}
	data, err := read(root, "blobs/sha256/"+strings.TrimPrefix(d.Digest, "sha256:"), maximum)
	if err != nil {
		return nil, err
	}
	sum := sha256.Sum256(data)
	if d.Size != int64(len(data)) || d.Digest != "sha256:"+hex.EncodeToString(sum[:]) {
		return nil, fmt.Errorf("OCI blob length or digest mismatch")
	}
	return data, nil
}

// Open reads only the requested digest, never an index tag. All archive entries
// are confined to a fresh private directory with bounded expansion and no links.
func Open(directory, digest string) (bundle *Bundle, err error) {
	if !digestPattern.MatchString(digest) {
		return nil, fmt.Errorf("an immutable sha256 digest is required")
	}
	root, err := filepath.Abs(directory)
	if err != nil {
		return nil, err
	}
	layout, err := read(root, "oci-layout", 4096)
	if err != nil {
		return nil, err
	}
	var format struct {
		Version string `json:"imageLayoutVersion"`
	}
	if err = decode(layout, &format); err != nil || format.Version != "1.0.0" {
		return nil, fmt.Errorf("invalid OCI layout version")
	}
	raw, err := read(root, "blobs/sha256/"+strings.TrimPrefix(digest, "sha256:"), validate.MaxManifestBytes)
	if err != nil {
		return nil, err
	}
	sum := sha256.Sum256(raw)
	if digest != "sha256:"+hex.EncodeToString(sum[:]) {
		return nil, fmt.Errorf("artifact digest mismatch")
	}
	var manifest Manifest
	if err = decode(raw, &manifest); err != nil {
		return nil, err
	}
	if manifest.SchemaVersion != 2 || manifest.MediaType != ManifestType || manifest.ArtifactType != Type || manifest.Config.MediaType != "application/vnd.onemind.app.manifest.v1+yaml" {
		return nil, fmt.Errorf("not a supported plugin artifact")
	}
	if len(manifest.Layers) < 2 || len(manifest.Layers) > 3 {
		return nil, fmt.Errorf("invalid plugin layer count")
	}
	config, err := checkedBlob(root, manifest.Config, validate.MaxManifestBytes)
	if err != nil {
		return nil, err
	}
	if err = validate.Manifest(config); err != nil {
		return nil, err
	}
	temp, err := os.MkdirTemp("", "onemind-plugin-read-")
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = os.RemoveAll(temp)
		}
	}()
	if err = os.WriteFile(filepath.Join(temp, "onemind.app.yaml"), config, 0600); err != nil {
		return nil, err
	}
	used := map[string]bool{"onemind.app.yaml": true, "README.md": true}
	media := map[string]bool{}
	count := 0
	for _, layer := range manifest.Layers {
		if media[layer.MediaType] {
			return nil, fmt.Errorf("duplicate plugin layer type")
		}
		media[layer.MediaType] = true
		switch layer.MediaType {
		case "text/markdown":
			data, e := checkedBlob(root, layer, 4<<20)
			if e != nil {
				return nil, e
			}
			if err = os.WriteFile(filepath.Join(temp, "README.md"), data, 0600); err != nil {
				return nil, err
			}
		case "application/vnd.onemind.plugin.manifests.v1.tar+gzip", "application/vnd.onemind.plugin.ui.v1.tar+gzip":
			data, e := checkedBlob(root, layer, 64<<20)
			if e != nil {
				return nil, e
			}
			if err = extract(data, temp, used, &count); err != nil {
				return nil, err
			}
		default:
			return nil, fmt.Errorf("unsupported plugin layer media type")
		}
	}
	if !media["text/markdown"] || !media["application/vnd.onemind.plugin.ui.v1.tar+gzip"] {
		return nil, fmt.Errorf("missing plugin layers")
	}
	if err = validate.Directory(temp); err != nil {
		return nil, err
	}
	var doc struct {
		Metadata struct{ ID, Version string }
		Spec     struct{ Manifests string }
	}
	if err = yaml.Unmarshal(config, &doc); err != nil {
		return nil, err
	}
	if (doc.Spec.Manifests != "") != media["application/vnd.onemind.plugin.manifests.v1.tar+gzip"] {
		return nil, fmt.Errorf("workload layer does not match plugin declaration")
	}
	return &Bundle{Directory: temp, Digest: digest, ID: doc.Metadata.ID, Version: doc.Metadata.Version, Manifest: config}, nil
}
func extract(data []byte, directory string, used map[string]bool, count *int) error {
	zipped, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		return err
	}
	defer zipped.Close()
	limited := &io.LimitedReader{R: zipped, N: (72 << 20) + 1}
	reader := tar.NewReader(limited)
	var total int64
	for {
		header, e := reader.Next()
		if e == io.EOF {
			break
		}
		if e != nil {
			return e
		}
		*count++
		if *count > 8192 {
			return fmt.Errorf("too many archive entries")
		}
		name := strings.TrimSuffix(header.Name, "/")
		if name == "" || name == "." || path.IsAbs(name) || !filepath.IsLocal(filepath.FromSlash(name)) || path.Clean(name) != name || strings.Contains(name, "\\") || name == ".." || strings.HasPrefix(name, "../") {
			return fmt.Errorf("unsafe archive path")
		}
		if header.Typeflag != tar.TypeReg && header.Typeflag != tar.TypeDir {
			return fmt.Errorf("archive links and special files are forbidden")
		}
		target := filepath.Join(directory, filepath.FromSlash(name))
		if header.Typeflag == tar.TypeDir {
			if err = os.MkdirAll(target, 0700); err != nil {
				return err
			}
			continue
		}
		if used[name] || header.Size < 0 || header.Size > 8<<20 {
			return fmt.Errorf("duplicate, reserved or oversized archive entry")
		}
		used[name] = true
		total += header.Size
		if total > 64<<20 {
			return fmt.Errorf("archive exceeds byte limit")
		}
		if err = os.MkdirAll(filepath.Dir(target), 0700); err != nil {
			return err
		}
		file, e := os.OpenFile(target, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if e != nil {
			return e
		}
		_, copyErr := io.CopyN(file, reader, header.Size)
		closeErr := file.Close()
		if copyErr != nil {
			return copyErr
		}
		if closeErr != nil {
			return closeErr
		}
	}
	// Drain gzip to verify its checksum and reject non-padding bytes after tar EOF.
	padding, err := io.ReadAll(limited)
	if err != nil {
		return err
	}
	if limited.N <= 0 {
		return fmt.Errorf("archive expansion limit exceeded")
	}
	for _, b := range padding {
		if b != 0 {
			return fmt.Errorf("trailing archive data")
		}
	}
	return nil
}
