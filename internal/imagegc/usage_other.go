// SPDX-License-Identifier: Apache-2.0

//go:build !unix

package imagegc

// DiskUsedPct is not available off Unix (the cleaner runs on Linux nodes only).
func DiskUsedPct(string) (float64, bool) { return 0, false }
