// SPDX-License-Identifier: Apache-2.0

package leaf

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/nats-io/nkeys"
)

// WriteNkeyFile writes the node's nkey seed (from the join bundle, FABRIC §4.1)
// as the config fragment `nkey: "<seed>"` that leaf.conf includes. The file is
// 0600 and written atomically. Only a user seed (SU…) is accepted.
func WriteNkeyFile(path string, seed []byte) (bool, error) {
	seed = bytes.TrimSpace(seed)
	prefix, _, err := nkeys.DecodeSeed(seed)
	if err != nil || prefix != nkeys.PrefixByteUser {
		return false, errors.New("nkey seed is not a valid NATS user seed")
	}
	body := make([]byte, 0, len(seed)+16)
	body = append(body, "nkey: \""...)
	body = append(body, seed...)
	body = append(body, "\"\n"...)
	return writeAtomic(path, body, 0o600)
}

// Apply renders c and writes it to confPath if the content changed. It returns
// whether the file changed, so the caller reloads nats-server only then.
func Apply(confPath string, c *Config) (bool, error) {
	body, err := c.Render(confPath)
	if err != nil {
		return false, err
	}
	return writeAtomic(confPath, body, 0o600)
}

// writeAtomic replaces path with body via a temp file in the same directory,
// fsync and rename, so nats-server never reads half a file. It is a no-op when
// the content and mode are already right.
func writeAtomic(path string, body []byte, mode os.FileMode) (bool, error) {
	if old, err := os.ReadFile(path); err == nil && bytes.Equal(old, body) {
		if fi, err := os.Stat(path); err == nil && fi.Mode().Perm() == mode {
			return false, nil
		}
	}
	dir := filepath.Dir(path)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return false, err
	}
	tmp, err := os.CreateTemp(dir, ".tmp-"+filepath.Base(path)+"-*")
	if err != nil {
		return false, err
	}
	name := tmp.Name()
	ok := false
	defer func() {
		if !ok {
			_ = os.Remove(name)
		}
	}()
	if err := tmp.Chmod(mode); err != nil {
		tmp.Close()
		return false, err
	}
	if _, err := tmp.Write(body); err != nil {
		tmp.Close()
		return false, err
	}
	if err := tmp.Sync(); err != nil {
		tmp.Close()
		return false, err
	}
	if err := tmp.Close(); err != nil {
		return false, err
	}
	if err := os.Rename(name, path); err != nil {
		return false, fmt.Errorf("replace %s: %w", filepath.Base(path), err)
	}
	ok = true
	if d, err := os.Open(dir); err == nil {
		_ = d.Sync()
		d.Close()
	}
	return true, nil
}
