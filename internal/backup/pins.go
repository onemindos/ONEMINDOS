// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"os"
)

// Pin is one third-party binary the backup agent runs as a subprocess.
// ArchiveSHA256 is the upstream SHA256SUMS line for the release archive;
// BinarySHA256 is the hash of the executable inside it, which is what the
// agent checks before it runs the file. Both were read on 2026-11-12 from the
// GitHub release pages named in Archive and re-computed locally.
type Pin struct {
	Name          string // "restic" or "rest-server"
	Version       string
	Arch          string // GOARCH
	Archive       string // upstream release asset URL
	ArchiveSHA256 string
	BinarySHA256  string
	License       string // SPDX id of the upstream licence at this version
}

// Pins lists every binary version the agent accepts. restic 0.19.1 is the
// engine pinned by BACKUPS.md B-R1; rest-server serves `node` targets
// (append-only, private repos). Both are BSD-2-Clause and ship as separate
// executables, never linked into onemindd.
var Pins = []Pin{
	{"restic", "0.19.1", "amd64",
		"https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_amd64.bz2",
		"f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c",
		"20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639", "BSD-2-Clause"},
	{"restic", "0.19.1", "arm64",
		"https://github.com/restic/restic/releases/download/v0.19.1/restic_0.19.1_linux_arm64.bz2",
		"a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465",
		"2fb45ac6f9071b6f20eb883953a188f9e7c7cb6bbe43c67a2e47ada4e85ee7f0", "BSD-2-Clause"},
	{"rest-server", "0.14.0", "amd64",
		"https://github.com/restic/rest-server/releases/download/v0.14.0/rest-server_0.14.0_linux_amd64.tar.gz",
		"4c9c95bc079a0334e81fad379b19dc5c3353c71c2c88d652cafce2081c2b1c66",
		"ec4fa7c3472bdc1cde6bfa994d1ee3344bb6e9dc3d9c10c8ff5316e3e77af6fd", "BSD-2-Clause"},
	{"rest-server", "0.14.0", "arm64",
		"https://github.com/restic/rest-server/releases/download/v0.14.0/rest-server_0.14.0_linux_arm64.tar.gz",
		"cef139cbe8b27b16bda731d17f093b0aa466b8c60b136c12d78b6f2bff3daf22",
		"578549202f1772706ae0f940ef684d1c19b2b2abe8e16d4c6845b1c0ee62f40c", "BSD-2-Clause"},
}

// PinFor returns the pin for name on arch.
func PinFor(name, arch string) (Pin, bool) {
	for _, p := range Pins {
		if p.Name == name && p.Arch == arch {
			return p, true
		}
	}
	return Pin{}, false
}

// VerifyBinary checks that the file at path is exactly the pinned executable.
func VerifyBinary(path string, p Pin) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	if got := hex.EncodeToString(h.Sum(nil)); got != p.BinarySHA256 {
		return fmt.Errorf("%s at %s is not the pinned %s %s/%s (sha256 %s, want %s)",
			p.Name, path, p.Name, p.Version, p.Arch, got, p.BinarySHA256)
	}
	return nil
}
