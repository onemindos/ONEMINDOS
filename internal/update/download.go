// SPDX-License-Identifier: Apache-2.0

package update

import (
	"context"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/hex"
	"errors"
	"fmt"
	"hash"
	"io"
	"net/http"
	"os"
	"path"
	"path/filepath"
)

// freeMargin is kept free on the download filesystem beyond the bundle itself.
const freeMargin = 256 << 20

// download fetches t to dir and verifies its length and every hash against
// the TUF-signed targets metadata. It streams to disk (bundles are far larger
// than a Pi's spare memory) and only renames the file into place once it
// verified, so a half-written or tampered file is never handed to RAUC.
// A previously verified file with the right hashes is reused.
func download(ctx context.Context, hc *http.Client, url, dir string, t *Target, free func(string) (uint64, error)) (string, error) {
	if len(t.Hashes) == 0 {
		return "", errors.New("target has no hashes")
	}
	for alg := range t.Hashes {
		if newHash(alg) == nil {
			return "", fmt.Errorf("unsupported hash algorithm %q", alg)
		}
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", err
	}
	dst := filepath.Join(dir, path.Base(t.Path))
	if verifyFile(dst, t) == nil {
		return dst, nil
	}
	if free != nil {
		if n, err := free(dir); err == nil && n < uint64(t.Length)+freeMargin {
			return "", fmt.Errorf("not enough space in %s: %d MiB free, need %d MiB", dir, n>>20, (uint64(t.Length)+freeMargin)>>20)
		}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", err
	}
	resp, err := hc.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("GET %s: HTTP %d", url, resp.StatusCode)
	}
	if resp.ContentLength > t.Length {
		return "", fmt.Errorf("server announces %d bytes, metadata says %d", resp.ContentLength, t.Length)
	}
	tmp := dst + ".part"
	f, err := os.OpenFile(tmp, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o600)
	if err != nil {
		return "", err
	}
	defer os.Remove(tmp) // no-op after the rename
	hs, w := hashers(t, f)
	n, err := io.Copy(w, io.LimitReader(resp.Body, t.Length+1))
	if err == nil {
		err = f.Sync()
	}
	if cerr := f.Close(); err == nil {
		err = cerr
	}
	if err != nil {
		return "", err
	}
	if err := checkSums(n, hs, t); err != nil {
		return "", err
	}
	if err := os.Rename(tmp, dst); err != nil {
		return "", err
	}
	return dst, nil
}

func newHash(alg string) hash.Hash {
	switch alg {
	case "sha256":
		return sha256.New()
	case "sha512":
		return sha512.New()
	}
	return nil
}

func hashers(t *Target, w io.Writer) (map[string]hash.Hash, io.Writer) {
	hs := map[string]hash.Hash{}
	ws := []io.Writer{w}
	for alg := range t.Hashes {
		h := newHash(alg)
		hs[alg] = h
		ws = append(ws, h)
	}
	return hs, io.MultiWriter(ws...)
}

func checkSums(n int64, hs map[string]hash.Hash, t *Target) error {
	if n != t.Length {
		return fmt.Errorf("length %d != signed length %d", n, t.Length)
	}
	for alg, h := range hs {
		if got := hex.EncodeToString(h.Sum(nil)); got != t.Hashes[alg] {
			return fmt.Errorf("%s mismatch: got %s, signed %s", alg, got, t.Hashes[alg])
		}
	}
	return nil
}

// verifyFile checks an existing file against t.
func verifyFile(p string, t *Target) error {
	f, err := os.Open(p)
	if err != nil {
		return err
	}
	defer f.Close()
	hs, w := hashers(t, io.Discard)
	n, err := io.Copy(w, io.LimitReader(f, t.Length+1))
	if err != nil {
		return err
	}
	return checkSums(n, hs, t)
}
