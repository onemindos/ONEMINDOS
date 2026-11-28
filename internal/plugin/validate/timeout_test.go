// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"strings"
	"testing"
	"time"

	"github.com/dlclark/regexp2"
)

// TestPatternNoFalseTimeoutAfterIdle guards against a valid value failing a
// schema pattern. Patterns run through regexp2 with a 100 ms match timeout,
// measured by a background clock that stops after about a second without
// matches. Up to regexp2 v1.11.4 the first matches after the clock restarted
// got a deadline from the stale clock value, so its first tick expired a
// match that was still running and MatchString reported "no match": CI run
// 45729613811 rejected 'uptime-kuma' against ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$.
// The test lets the clock stop, then runs back-to-back matches of a few
// milliseconds each (far below the timeout) across the restart.
func TestPatternNoFalseTimeoutAfterIdle(t *testing.T) {
	if testing.Short() {
		t.Skip("waits for regexp2's idle clock to stop")
	}
	const expr = `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`
	// Size the input so one match takes about 5 ms on this machine, timed
	// with an untimed copy of the pattern (which does not touch the clock).
	untimed := regexp2.MustCompile(expr, regexp2.ECMAScript)
	input := "uptime-kuma"
	for {
		start := time.Now()
		if ok, err := untimed.MatchString(input); !ok || err != nil {
			t.Fatalf("calibration match failed: %v %v", ok, err)
		}
		if time.Since(start) >= 5*time.Millisecond {
			break
		}
		input = strings.Repeat("a", 2*len(input))
	}
	if d := matchTime(t, untimed, input); d > patternTimeout/4 {
		t.Skipf("one match takes %v here, too close to the %v timeout to test", d, patternTimeout)
	}
	re, err := pattern(expr)
	if err != nil {
		t.Fatal(err)
	}
	for round := 0; round < 2; round++ {
		if !re.MatchString("uptime-kuma") {
			t.Fatal("short value rejected")
		}
		// The clock stops once it passes the last deadline plus one second.
		time.Sleep(2500 * time.Millisecond)
		for stop := time.Now().Add(300 * time.Millisecond); time.Now().Before(stop); {
			if !re.MatchString(input) {
				t.Fatalf("round %d: valid %d-byte value rejected after the regexp clock restarted", round, len(input))
			}
		}
	}
}

func matchTime(t *testing.T, re *regexp2.Regexp, input string) time.Duration {
	t.Helper()
	start := time.Now()
	if ok, err := re.MatchString(input); !ok || err != nil {
		t.Fatalf("match failed: %v %v", ok, err)
	}
	return time.Since(start)
}
