// SPDX-License-Identifier: Apache-2.0

package main

import (
	"os"
	"testing"
)

// TestMain keeps the tests away from the developer's own ~/.config/onemind.
func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "onemind-cli-test-")
	if err != nil {
		panic(err)
	}
	os.Setenv("XDG_CONFIG_HOME", dir)
	os.Unsetenv("ONEMIND_CONTEXT")
	os.Unsetenv("ONEMIND_CONFIG")
	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}
