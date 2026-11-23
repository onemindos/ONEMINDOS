// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"fmt"
	"strings"
)

// The requires / recommends / supports block (#724): the rules JSON Schema cannot say, with the same
// messages as core/onemind_core/machine_needs.py (errors), checked by the shared golden cases in
// sdk/testdata/manifest-v1.

var machineStrengths = []string{"requires", "recommends", "supports"}

var x86Levels = map[string]bool{"x86-64-v1": true, "x86-64-v2": true, "x86-64-v3": true, "x86-64-v4": true}

// baseArch is amd64 for an x86-64 psABI level, else the name itself.
func baseArch(arch string) string {
	if x86Levels[arch] {
		return "amd64"
	}
	return arch
}

// validateMachineNames refuses a vendor resource (nvidia.com/gpu) or a host path (/dev/ttyUSB0) where a
// vendor-neutral device class or accelerator capability goes. It runs before the schema, so the
// message says why instead of quoting a pattern.
func validateMachineNames(value map[string]any) error {
	spec := asMap(value["spec"])
	for _, name := range machineStrengths {
		block := asMap(spec[name])
		type found struct{ where, value string }
		var names []found
		for i, raw := range asList(block["devices"]) {
			if s, ok := raw.(string); ok {
				names = append(names, found{fmt.Sprintf("devices/%d", i), s})
			}
		}
		if s, ok := asMap(block["accelerator"])["capability"].(string); ok {
			names = append(names, found{"accelerator/capability", s})
		}
		for _, f := range names {
			if strings.ContainsAny(f.value, "/.") {
				return fmt.Errorf("spec/%s/%s: %s names a vendor or a host path; use a vendor-neutral name", name, f.where, f.value)
			}
		}
	}
	return nil
}

// validateMachine runs on a schema-valid spec: one spelling per fact, each architecture once, and
// requires.arch names the same architectures as spec.archs (the images' own list).
func validateMachine(spec map[string]any) error {
	raw := asMap(spec["requires"])
	for _, pair := range [][2]string{{"minMemoryMb", "memoryMb"}, {"cpuLevel", "arch"}, {"gpuCount", "accelerator.count"}} {
		old, newer := pair[0], pair[1]
		head, tail, nested := strings.Cut(newer, ".")
		_, hasOld := raw[old]
		_, hasHead := raw[head]
		_, hasTail := asMap(raw[head])[tail]
		if hasOld && hasHead && (!nested || hasTail) {
			return fmt.Errorf("spec/requires: %s and %s say the same thing; keep %s", old, newer, newer)
		}
	}
	for _, name := range machineStrengths {
		seen := map[string]bool{}
		for _, a := range asList(asMap(spec[name])["arch"]) {
			s, _ := a.(string)
			if seen[baseArch(s)] {
				return fmt.Errorf("spec/%s/arch: %s is named twice", name, baseArch(s))
			}
			seen[baseArch(s)] = true
		}
	}
	arch, hasArch := raw["arch"].([]any)
	archs, hasArchs := spec["archs"].([]any)
	if hasArch && hasArchs {
		want, got := map[string]bool{}, map[string]bool{}
		for _, a := range archs {
			want[fmt.Sprint(a)] = true
		}
		for _, a := range arch {
			got[baseArch(fmt.Sprint(a))] = true
		}
		same := len(want) == len(got)
		for a := range want {
			same = same && got[a]
		}
		if !same {
			return fmt.Errorf("spec/requires/arch: must name the same architectures as spec.archs")
		}
	}
	return nil
}
