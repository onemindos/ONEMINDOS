// SPDX-License-Identifier: Apache-2.0

package mesh

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// DefaultKeyDir is where the one-time auth key file lives for the few seconds
// `tailscale up` needs it. /run is tmpfs, so the key never reaches the disk.
const DefaultKeyDir = "/run/onemind/mesh"

// DefaultUpTimeout bounds `tailscale up` and the wait for the mesh address
// (§5.1: "waits ≤ 60 s for its mesh IP").
const DefaultUpTimeout = 60 * time.Second

// EnrollOptions tune Enroll. The zero value uses the defaults.
type EnrollOptions struct {
	KeyDir  string
	Timeout time.Duration
	// Poll is the interval for WaitIP (default 1 s).
	Poll time.Duration
}

// Result is what Enroll reports.
type Result struct {
	// Already is true when tailscaled was already Running with a mesh address:
	// the key was not used (it stays single-use on the coordinator and expires
	// after 15 min).
	Already bool
	Addr    string
}

// upArgs is the exact `tailscale up` command line of §5.1. --reset makes the
// flags authoritative, so a re-run with different settings does not fail on
// tailscale's "changing settings requires mentioning all flags" check.
func upArgs(b *Bundle, keyPath string, timeout time.Duration) []string {
	args := []string{
		"up",
		"--reset",
		"--login-server=" + b.ControlURL,
		"--auth-key=file:" + keyPath,
		"--hostname=" + b.Hostname,
		"--accept-routes=false",
		"--accept-dns=true",
		"--ssh=false",
		"--timeout=" + timeout.String(),
	}
	if b.ShieldsUp {
		args = append(args, "--shields-up")
	}
	return args
}

// writeKeyFile writes the key to a new 0600 file with a random name in dir
// (created 0700) and returns its path. O_EXCL refuses a pre-planted file or
// symlink at that name.
func writeKeyFile(dir, key string) (string, error) {
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return "", fmt.Errorf("key dir: %w", err)
	}
	if err := os.Chmod(dir, 0o700); err != nil {
		return "", fmt.Errorf("key dir: %w", err)
	}
	var rnd [8]byte
	if _, err := rand.Read(rnd[:]); err != nil {
		return "", err
	}
	p := filepath.Join(dir, "authkey-"+hex.EncodeToString(rnd[:]))
	f, err := os.OpenFile(p, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return "", fmt.Errorf("key file: %w", err)
	}
	_, werr := f.WriteString(key)
	cerr := f.Close()
	if werr != nil || cerr != nil {
		_ = os.Remove(p)
		return "", fmt.Errorf("key file: %w", errors.Join(werr, cerr))
	}
	return p, nil
}

// Enroll joins this machine to the coordinator named in b (§5.1): it writes the
// one-time key to a 0600 file, runs `tailscale up` with it, always deletes the
// file, and waits for a mesh address. If the machine is already up it does
// nothing. The custodian's bind check (node registered with our key, name and
// tags) runs on the hub, not here.
func (c *Client) Enroll(ctx context.Context, b *Bundle, o EnrollOptions) (*Result, error) {
	if err := b.Validate(); err != nil {
		return nil, err
	}
	if o.KeyDir == "" {
		o.KeyDir = DefaultKeyDir
	}
	if o.Timeout <= 0 {
		o.Timeout = DefaultUpTimeout
	}
	if s := c.Status(ctx); s.State == StateUp {
		return &Result{Already: true, Addr: s.Addr}, nil
	} else if s.State == StateNone {
		return nil, ErrNotInstalled
	}
	keyPath, err := writeKeyFile(o.KeyDir, b.AuthKey)
	if err != nil {
		return nil, err
	}
	upCtx, cancel := context.WithTimeout(ctx, o.Timeout+10*time.Second)
	_, upErr := c.Runner.Run(upCtx, upArgs(b, keyPath, o.Timeout)...)
	cancel()
	rmErr := os.Remove(keyPath)
	if upErr != nil {
		return nil, fmt.Errorf("mesh enroll: %w", upErr)
	}
	if rmErr != nil && !errors.Is(rmErr, os.ErrNotExist) {
		return nil, fmt.Errorf("mesh enroll: removing the key file: %w", rmErr)
	}
	addr, err := c.WaitIP(ctx, o.Timeout, o.Poll)
	if err != nil {
		return nil, err
	}
	return &Result{Addr: addr}, nil
}

// WaitIP polls until tailscaled is Running with a mesh IPv4 address and returns
// it (`onemindd mesh wait-ip`, the k3s ExecStartPre of §5.2).
func (c *Client) WaitIP(ctx context.Context, timeout, poll time.Duration) (string, error) {
	if poll <= 0 {
		poll = time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	t := time.NewTicker(poll)
	defer t.Stop()
	var last *State
	for {
		last = c.Status(ctx)
		if last.State == StateUp {
			return last.Addr, nil
		}
		if last.State == StateNone {
			return "", ErrNotInstalled
		}
		select {
		case <-ctx.Done():
			why := last.Backend
			if last.Error != "" {
				why = last.Error
			}
			return "", fmt.Errorf("mesh not up after %s (last: %s)", timeout, why)
		case <-t.C:
		}
	}
}

// Reporter returns the heartbeat hook for agent.Config (NETWORKING.md §18): it
// reads the mesh state with a short timeout and returns the privacy-safe
// object, or nil when this machine has no mesh (so the field is omitted and
// heartbeats stay valid without it).
func Reporter(log *slog.Logger) func() *Heartbeat {
	c := NewClient()
	return reporter(c, log)
}

func reporter(c *Client, log *slog.Logger) func() *Heartbeat {
	var mu sync.Mutex
	lastErr := ""
	return func() *Heartbeat {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		s := c.Status(ctx)
		if s.State == StateNone {
			return nil
		}
		mu.Lock()
		defer mu.Unlock()
		if log != nil && s.Error != lastErr {
			if s.Error != "" {
				log.Warn("mesh status", "err", s.Error)
			} else {
				log.Info("mesh status recovered", "state", s.State)
			}
			lastErr = s.Error
		}
		return s.Heartbeat()
	}
}
