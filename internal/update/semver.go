// SPDX-License-Identifier: Apache-2.0

package update

import (
	"fmt"
	"strconv"
	"strings"
)

// version is a SemVer 2.0.0 version (an optional leading "v" is accepted;
// build metadata after '+' is ignored for ordering, as SemVer says).
// OneMind image versions look like 0.1.0, 0.1.0-dev, 0.1.1-sec.20261112.
type version struct {
	major, minor, patch uint64
	pre                 []string
}

func parseVersion(s string) (version, error) {
	s = strings.TrimPrefix(s, "v")
	if i := strings.IndexByte(s, '+'); i >= 0 {
		s = s[:i]
	}
	core, pre, hasPre := strings.Cut(s, "-")
	parts := strings.Split(core, ".")
	if len(parts) != 3 {
		return version{}, fmt.Errorf("version %q is not MAJOR.MINOR.PATCH", s)
	}
	var n [3]uint64
	for i, p := range parts {
		if p == "" || (len(p) > 1 && p[0] == '0') {
			return version{}, fmt.Errorf("version %q: bad number %q", s, p)
		}
		v, err := strconv.ParseUint(p, 10, 64)
		if err != nil {
			return version{}, fmt.Errorf("version %q: bad number %q", s, p)
		}
		n[i] = v
	}
	v := version{major: n[0], minor: n[1], patch: n[2]}
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

// compareVersions returns -1, 0 or 1 (SemVer precedence).
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
	if c := cmpU(a.major, b.major); c != 0 {
		return c
	}
	if c := cmpU(a.minor, b.minor); c != 0 {
		return c
	}
	if c := cmpU(a.patch, b.patch); c != 0 {
		return c
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
