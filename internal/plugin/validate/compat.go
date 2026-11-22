// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"strings"

	"github.com/Masterminds/semver/v3"
	"gopkg.in/yaml.v3"
)

// ManifestForAPI validates the manifest and checks its compatibility range
// against the box's plugin API level. The level is supplied by the caller;
// it is never fetched over the network during validation.
func ManifestForAPI(data []byte, apiLevel string) error {
	if err := Manifest(data); err != nil {
		return err
	}
	if strings.TrimSpace(apiLevel) != apiLevel || apiLevel == "" {
		return fmt.Errorf("plugin API level is required without surrounding whitespace")
	}
	version, err := semver.NewVersion(apiLevel)
	if err != nil {
		return fmt.Errorf("invalid plugin API level: %w", err)
	}
	var value map[string]any
	if err := yaml.Unmarshal(data, &value); err != nil {
		return err
	}
	spec := value["spec"].(map[string]any)
	constraint := spec["compat"].(map[string]any)["onemind"].(string)
	required, err := semver.NewConstraint(constraint)
	if err != nil {
		return err
	}
	if !required.Check(version) {
		return fmt.Errorf("plugin requires API %s; box API is %s", constraint, apiLevel)
	}
	return nil
}

// DirectoryForAPI checks bundle paths and the caller-supplied box API level.
func DirectoryForAPI(dir, apiLevel string) error {
	if apiLevel == "" {
		return fmt.Errorf("plugin API level is required")
	}
	return directory(dir, apiLevel)
}
