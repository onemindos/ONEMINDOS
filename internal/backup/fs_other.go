// SPDX-License-Identifier: Apache-2.0

//go:build !unix

package backup

import "errors"

var errUnsupported = errors.New("not supported on this platform")

func freeBytes(string) (int64, error)   { return 0, errUnsupported }
func isMountPoint(string) (bool, error) { return false, errUnsupported }
