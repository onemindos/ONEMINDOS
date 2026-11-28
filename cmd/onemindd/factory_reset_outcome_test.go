// SPDX-License-Identifier: Apache-2.0

package main

import (
	"errors"
	"io"
	"log/slog"
	"testing"

	"github.com/onemindos/onemindos/internal/host"
)

// After a successful wipe the box restarts (nothing else formats the blank
// partitions on this boot); with no marker it does not; a failed wipe never does.
func TestResetOutcomeRestartsOnlyAfterASuccessfulWipe(t *testing.T) {
	log := slog.New(slog.NewTextHandler(io.Discard, nil))
	cases := []struct {
		name       string
		err        error
		rebootErr  error
		wantCode   int
		wantReboot bool
	}{
		{"wiped", nil, nil, 0, true},
		{"no marker", host.ErrNoMarker, nil, 0, false},
		{"stale", host.ErrStaleMarker, nil, 1, false},
		{"failed", errors.New("wipefs failed"), nil, 1, false},
		{"wiped but the restart failed", nil, errors.New("no systemd"), 1, true},
	}
	for _, c := range cases {
		rebooted := false
		got := resetOutcome(c.err, log, func() error { rebooted = true; return c.rebootErr })
		if got != c.wantCode || rebooted != c.wantReboot {
			t.Errorf("%s: code %d reboot %v, want %d %v", c.name, got, rebooted, c.wantCode, c.wantReboot)
		}
	}
}
