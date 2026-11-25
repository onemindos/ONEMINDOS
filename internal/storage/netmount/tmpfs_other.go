// SPDX-License-Identifier: Apache-2.0

//go:build !linux

package netmount

import "errors"

// onTmpfs cannot be answered off Linux: no credentials file is written there.
func onTmpfs(string) (bool, error) { return false, errors.New("tmpfs check needs Linux") }
