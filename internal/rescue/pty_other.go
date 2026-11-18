// SPDX-License-Identifier: Apache-2.0

//go:build !linux

package rescue

import "errors"

// PTY is only implemented on Linux, where the OS image runs.
type PTY struct {
	Shell string
	Env   []string
}

// Spawn implements Spawner.
func (PTY) Spawn() (Session, error) { return nil, errors.New("the rescue terminal needs Linux") }
