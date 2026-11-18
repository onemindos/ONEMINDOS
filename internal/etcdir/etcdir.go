// SPDX-License-Identifier: Apache-2.0

// Package etcdir says where a node keeps its OneMind config files.
//
// A box set up by deploy/install.sh uses /etc/onemind. On the OS image /etc is read-only, so
// its units set ONEMIND_ETC_DIR=/data/onemind/etc, the writable directory first boot already
// uses (IMG-MESH-01, #292). The update settings (/etc/onemind/update.conf) ship with the image
// and are not affected.
package etcdir

import (
	"os"
	"path/filepath"
)

// Default is the directory used when ONEMIND_ETC_DIR is unset.
const Default = "/etc/onemind"

// Dir is ONEMIND_ETC_DIR when it is a clean absolute path, else Default.
func Dir() string {
	if d := os.Getenv("ONEMIND_ETC_DIR"); d != "" && filepath.IsAbs(d) && filepath.Clean(d) == d {
		return d
	}
	return Default
}
