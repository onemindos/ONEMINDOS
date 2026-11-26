// SPDX-License-Identifier: Apache-2.0

package main

import "testing"

func TestJobsStateDir(t *testing.T) {
	t.Setenv("ONEMIND_ETC_DIR", "/data/onemind/etc")
	t.Setenv("ONEMIND_JOBS_DIR", "")
	if got := jobsStateDir(); got != "/data/onemind/etc/jobs" {
		t.Fatalf("default %q", got)
	}
	t.Setenv("ONEMIND_JOBS_DIR", "relative/dir")
	if got := jobsStateDir(); got != "/data/onemind/etc/jobs" {
		t.Fatalf("a relative override must be ignored, got %q", got)
	}
	t.Setenv("ONEMIND_JOBS_DIR", "/var/lib/onemindd/jobs/")
	if got := jobsStateDir(); got != "/var/lib/onemindd/jobs" {
		t.Fatalf("override %q", got)
	}
}
