// SPDX-License-Identifier: Apache-2.0

package ops

import (
	"context"
	"crypto/rand"
	"fmt"
	"os"
	"strings"

	"github.com/onemindos/onemindos/internal/storage"
)

// NewUUID returns a random version 4 UUID.
func NewUUID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = b[6]&0x0f | 0x40
	b[8] = b[8]&0x3f | 0x80
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// InitData formats a fresh onemind-data partition at first boot (H-11):
// LUKS2 with a new recovery key (left in storage.RecoveryKeyFile, tmpfs, for
// the owner to see once), the set key, TPM2 when asked, the OneMind token
// and btrfs with its subvolumes. It refuses a partition that already holds
// anything unless force is set. It returns the set's btrfs UUID.
func InitData(ctx context.Context, r Runner, o storage.InitOptions, force bool) (string, error) {
	if o.Part == "" {
		return "", fmt.Errorf("no partition given")
	}
	out, _, err := r.Exec(ctx, "", "blkid", "-o", "value", "-s", "TYPE", o.Part)
	if err != nil {
		return "", fmt.Errorf("blkid: %w", err)
	}
	if t := strings.TrimSpace(string(out)); t != "" && !force {
		return "", fmt.Errorf("%s already holds %s; refusing to format it (force overrides)", o.Part, t)
	}
	if err := os.MkdirAll(storage.RunDir, 0o700); err != nil {
		return "", err
	}
	rk, err := storage.NewRecoveryKey()
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(storage.RecoveryKeyFile, []byte(rk), 0o600); err != nil {
		return "", err
	}
	sk := make([]byte, 64)
	if _, err := rand.Read(sk); err != nil {
		return "", err
	}
	setKey := storage.RunDir + "/set.key"
	if err := os.WriteFile(setKey, sk, 0o600); err != nil {
		return "", err
	}
	defer os.Remove(setKey)
	if o.SetUUID == "" {
		o.SetUUID = NewUUID()
	}
	for _, st := range storage.InitSteps(o) {
		if !allowed[st.Cmd[0]] {
			return "", fmt.Errorf("step %s: program not allowed", st.ID)
		}
		out, code, err := r.Exec(ctx, st.Stdin, st.Cmd[0], st.Cmd[1:]...)
		if err != nil || code != 0 {
			return "", fmt.Errorf("step %s (%s) exited %d: %s", st.ID, st.Cmd[0], code, tail(out, 400))
		}
	}
	return o.SetUUID, nil
}
