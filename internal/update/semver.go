// SPDX-License-Identifier: Apache-2.0

package update

import (
	"fmt"
	"strconv"
	"strings"
)

// version is a OneMind release version (os/update/CHANNEL.md §5): one or
// more dot-separated decimal integers, compared numerically part by part
// (a missing part counts as 0), e.g. 0.1.20261112025704 =
// <base_version>.<snapshot YYYYMMDDHHMMSS>. Developer images carry a SemVer
// pre-release suffix (0.1.0-dev); it ranks below the same version without
// one, as in SemVer. An optional leading "v" and build metadata after '+' are
// accepted and ignored for ordering.
type version struct {
	nums []uint64
	pre  []string
}

func parseVersion(s string) (version, error) {
	s = strings.TrimPrefix(s, "v")
	if i := strings.IndexByte(s, '+'); i >= 0 {
		s = s[:i]
	}
	core, pre, hasPre := strings.Cut(s, "-")
	var v version
	for _, p := range strings.Split(core, ".") {
		n, err := strconv.ParseUint(p, 10, 64)
		if err != nil {
			return version{}, fmt.Errorf("version %q is not dot-separated integers", s)
		}
		v.nums = append(v.nums, n)
	}
	if hasPre {
		if pre == "" {
			return version{}, fmt.Errorf("version %q: empty pre-release", s)
		}
		v.pre = strings.Split(pre, ".")
		for _, id := range v.pre {
			if id == "" {
				return version{}, fmt.Errorf("version %q: empty pre-release identifier", s)
			}
		}
	}
	return v, nil
}

// compareVersions returns -1, 0 or 1.
func compareVersions(a, b string) (int, error) {
	va, err := parseVersion(a)
	if err != nil {
		return 0, err
	}
	vb, err := parseVersion(b)
	if err != nil {
		return 0, err
	}
	return va.cmp(vb), nil
}

func cmpU(a, b uint64) int {
	switch {
	case a < b:
		return -1
	case a > b:
		return 1
	}
	return 0
}

func (a version) cmp(b version) int {
	for i := 0; i < len(a.nums) || i < len(b.nums); i++ {
		var x, y uint64
		if i < len(a.nums) {
			x = a.nums[i]
		}
		if i < len(b.nums) {
			y = b.nums[i]
		}
		if c := cmpU(x, y); c != 0 {
			return c
		}
	}
	// A version without pre-release ranks above one with it.
	switch {
	case len(a.pre) == 0 && len(b.pre) == 0:
		return 0
	case len(a.pre) == 0:
		return 1
	case len(b.pre) == 0:
		return -1
	}
	for i := 0; i < len(a.pre) && i < len(b.pre); i++ {
		x, y := a.pre[i], b.pre[i]
		xn, ex := strconv.ParseUint(x, 10, 64)
		yn, ey := strconv.ParseUint(y, 10, 64)
		switch {
		case ex == nil && ey == nil:
			if c := cmpU(xn, yn); c != 0 {
				return c
			}
		case ex == nil: // numeric identifiers rank below alphanumeric
			return -1
		case ey == nil:
			return 1
		default:
			if c := strings.Compare(x, y); c != 0 {
				return c
			}
		}
	}
	return cmpU(uint64(len(a.pre)), uint64(len(b.pre)))
}
