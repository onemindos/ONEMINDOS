// SPDX-License-Identifier: Apache-2.0

//go:build !unix

package update

import "errors"

func freeBytes(string) (uint64, error) { return 0, errors.New("unsupported") }

// ErrBusy means another update run holds the lock.
var ErrBusy = errors.New("another update run is in progress")

// lock is a no-op where flock does not exist (OneMind boxes are Linux).
func lock(string) (func(), error) { return func() {}, nil }
