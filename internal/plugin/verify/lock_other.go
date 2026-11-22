// SPDX-License-Identifier: Apache-2.0

//go:build !unix

package verify

import "fmt"

func lockRevocations(string) (func(), error) {
	return nil, fmt.Errorf("persistent revocation checks require a Unix file lock")
}
