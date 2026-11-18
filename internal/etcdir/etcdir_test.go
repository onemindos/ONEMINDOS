// SPDX-License-Identifier: Apache-2.0

package etcdir

import "testing"

func TestDir(t *testing.T) {
	for _, c := range []struct{ env, want string }{
		{"", Default},
		{"/data/onemind/etc", "/data/onemind/etc"},
		{"relative/dir", Default},       // never relative to the working directory
		{"/data/onemind/etc/", Default}, // not clean
		{"/data/../etc", Default},
	} {
		t.Setenv("ONEMIND_ETC_DIR", c.env)
		if got := Dir(); got != c.want {
			t.Errorf("ONEMIND_ETC_DIR=%q: got %q, want %q", c.env, got, c.want)
		}
	}
}
