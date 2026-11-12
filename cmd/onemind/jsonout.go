// SPDX-License-Identifier: Apache-2.0
package main

import (
	"encoding/json"
	"io"
)

// printJSON serves the command files that still live in package main (storage.go, mesh.go)
// until their streams move them into cmd/onemind/cli as command groups (docs/leap/core/PLUMBING.md).
func printJSON(out io.Writer, v any) error {
	enc := json.NewEncoder(out)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

// dash renders an empty value as "-" (same as the cli package helper).
func dash(s string) string {
	if s == "" {
		return "-"
	}
	return s
}
