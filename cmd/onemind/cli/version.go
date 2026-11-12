// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"

	"github.com/onemindos/onemindos/internal/version"
)

func versionCommands() []Command {
	return []Command{{
		Path:  []string{"version"},
		Usage: "onemind version",
		Run: func(env *Env, _ []string) error {
			fmt.Fprintln(env.Stdout, "onemind", version.Version)
			return nil
		},
	}}
}
