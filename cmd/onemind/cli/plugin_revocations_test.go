// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"testing"
)

func TestRevocationsCommandRequiresTrustConfigurationAndCompleteIdentity(t *testing.T) {
	for _, args := range [][]string{
		{"plugin", "revocations"},
		{"plugin", "revocations", "--root", "missing", "--metadata-url", "https://example.invalid/metadata", "--targets-url", "https://example.invalid/targets", "--state", t.TempDir(), "--id", "hello"},
		{"plugin", "revocations", "--root", "missing", "--metadata-url", "https://example.invalid/metadata", "--targets-url", "https://example.invalid/targets", "--state", t.TempDir()},
	} {
		var stdout, stderr bytes.Buffer
		if code := Run(args, Env{Stdout: &stdout, Stderr: &stderr}); code == ExitOK {
			t.Fatalf("missing trust accepted: %v", args)
		}
		if stdout.Len() != 0 {
			t.Fatal("failed check produced success output")
		}
	}
}
