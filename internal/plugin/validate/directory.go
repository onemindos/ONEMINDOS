// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

// Directory validates an unpacked, quiescent plugin bundle. Extraction and
// signature verification must finish before this check; callers must not mutate
// the directory while validating or installing it. This is not an archive extractor.
func Directory(dir string) error { return directory(dir, "") }

func directory(dir, apiLevel string) error {
	root, err := filepath.Abs(dir)
	if err != nil {
		return err
	}
	info, err := os.Lstat(root)
	if err != nil {
		return err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return fmt.Errorf("plugin root must be a directory, not a symlink")
	}
	manifest, err := bundlePath(root, "onemind.app.yaml", false)
	if err != nil {
		return err
	}
	f, err := os.Open(manifest)
	if err != nil {
		return err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, MaxManifestBytes+1))
	if err != nil {
		return err
	}
	if apiLevel == "" {
		if err := Manifest(data); err != nil {
			return err
		}
	} else if err := ManifestForAPI(data, apiLevel); err != nil {
		return err
	}
	// Manifest already established the types and single-document constraint.
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		return err
	}
	metadata := value["metadata"].(map[string]any)
	spec := value["spec"].(map[string]any)
	if _, err := bundlePath(root, metadata["icon"].(string), false); err != nil {
		return fmt.Errorf("metadata.icon: %w", err)
	}
	if _, present := spec["manifests"]; !present {
		// The gateway falls back to manifests/ when the field is absent, so an undeclared
		// folder would be rendered and applied without ever being checked or scanned.
		if _, err := os.Lstat(filepath.Join(root, "manifests")); err == nil {
			return fmt.Errorf("manifests/ present but spec.manifests is not declared")
		} else if !os.IsNotExist(err) {
			return err
		}
	}
	if relative, present := spec["manifests"].(string); present {
		manifests, err := bundlePath(root, relative, true)
		if err != nil {
			return fmt.Errorf("spec.manifests: %w", err)
		}
		// Reject symlinks anywhere in the workload tree, not only the entry directory.
		if err := filepath.WalkDir(manifests, func(path string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			info, err := entry.Info()
			if err != nil {
				return err
			}
			if !info.IsDir() && !info.Mode().IsRegular() {
				return fmt.Errorf("manifest tree contains symlink or special file: %s", entry.Name())
			}
			return nil
		}); err != nil {
			return err
		}
	}
	return validateUIBundle(root, metadata, spec)
}

func bundlePath(root, relative string, directory bool) (string, error) {
	// Check every component before cleaning: cleaning could erase a traversal.
	if filepath.IsAbs(relative) || strings.ContainsAny(relative, `\:`) {
		return "", fmt.Errorf("bundle path must be relative")
	}
	parts := strings.Split(relative, "/")
	for _, part := range parts {
		if part == ".." {
			return "", fmt.Errorf("bundle path cannot contain '..'")
		}
	}
	clean := filepath.Clean(relative)
	if clean == "." {
		return "", fmt.Errorf("bundle path must name an entry below the root")
	}
	path := root
	for _, part := range strings.Split(clean, string(filepath.Separator)) {
		path = filepath.Join(path, part)
		info, err := os.Lstat(path)
		if err != nil {
			return "", fmt.Errorf("bundle path %q: %w", relative, err)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			return "", fmt.Errorf("bundle path %q contains a symlink", relative)
		}
	}
	info, err := os.Lstat(path)
	if err != nil {
		return "", err
	}
	if directory && !info.IsDir() {
		return "", fmt.Errorf("bundle path %q must be a directory", relative)
	}
	if !directory && !info.Mode().IsRegular() {
		return "", fmt.Errorf("bundle path %q must be a regular file", relative)
	}
	return path, nil
}
