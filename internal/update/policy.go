// SPDX-License-Identifier: Apache-2.0

package update

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

// Window is a daily local-time maintenance window in minutes after midnight.
// End < Start wraps past midnight (22:00-04:00). Any = no restriction.
type Window struct {
	Start, End int
	Any        bool
}

// ParseWindow parses "HH:MM-HH:MM" or "any".
func ParseWindow(s string) (Window, error) {
	if s == "any" {
		return Window{Any: true}, nil
	}
	a, b, ok := strings.Cut(s, "-")
	if !ok {
		return Window{}, fmt.Errorf("want HH:MM-HH:MM or any")
	}
	st, err := parseHHMM(a)
	if err != nil {
		return Window{}, err
	}
	en, err := parseHHMM(b)
	if err != nil {
		return Window{}, err
	}
	if st == en {
		return Window{}, fmt.Errorf("start and end are equal; use \"any\" for no window")
	}
	return Window{Start: st, End: en}, nil
}

func parseHHMM(s string) (int, error) {
	h, m, ok := strings.Cut(strings.TrimSpace(s), ":")
	if !ok {
		return 0, fmt.Errorf("bad time %q", s)
	}
	hh, err1 := strconv.Atoi(h)
	mm, err2 := strconv.Atoi(m)
	if err1 != nil || err2 != nil || hh < 0 || hh > 23 || mm < 0 || mm > 59 {
		return 0, fmt.Errorf("bad time %q", s)
	}
	return hh*60 + mm, nil
}

// Contains reports whether t (in its own location; pass local time) is inside the window.
func (w Window) Contains(t time.Time) bool {
	if w.Any {
		return true
	}
	m := t.Hour()*60 + t.Minute()
	if w.Start < w.End {
		return m >= w.Start && m < w.End
	}
	return m >= w.Start || m < w.End
}

func (w Window) String() string {
	if w.Any {
		return "any"
	}
	return fmt.Sprintf("%02d:%02d-%02d:%02d", w.Start/60, w.Start%60, w.End/60, w.End%60)
}

// Decision is what the policy says to do with an available release.
type Decision string

// Decisions.
const (
	DecideNothing      Decision = "nothing"       // no applicable newer release
	DecideBlockedTrial Decision = "blocked-trial" // a previous update awaits the health gate's verdict
	DecideOff          Decision = "off"           // policy off (opt-out)
	DecidePostponed    Decision = "postponed"     // owner postponed updates
	DecideNotify       Decision = "notify"        // report only
	DecideWait         Decision = "wait-window"   // auto, outside the maintenance window
	DecideInstall      Decision = "install"
)

// DecideInput is everything the policy looks at.
type DecideInput struct {
	Policy        Policy
	Window        Window
	Now           time.Time // local time
	PostponeUntil time.Time // zero = not postponed
	TrialPending  bool      // gate marker present (trial running or install awaiting reboot)
	HaveCandidate bool
	Explicit      bool // the owner asked now (`onemind update apply`)
}

// Decide applies BD-09. The order matters: a pending gate verdict blocks
// everything, even an explicit request; an explicit owner request overrides
// opt-out, postpone, notify and the window (the owner is the human approver).
func Decide(in DecideInput) (Decision, string) {
	switch {
	case !in.HaveCandidate:
		return DecideNothing, "no applicable newer release"
	case in.TrialPending:
		return DecideBlockedTrial, "previous update awaits the health gate's verdict"
	case in.Explicit:
		return DecideInstall, "owner requested apply"
	case in.Policy == PolicyOff:
		return DecideOff, "policy off (opt-out)"
	case !in.PostponeUntil.IsZero() && in.Now.Before(in.PostponeUntil):
		return DecidePostponed, "postponed until " + in.PostponeUntil.Format(time.RFC3339)
	case in.Policy == PolicyNotify:
		return DecideNotify, "policy notify: run `onemind update apply` to install"
	case !in.Window.Contains(in.Now):
		return DecideWait, "outside maintenance window " + in.Window.String()
	}
	return DecideInstall, "policy auto, inside maintenance window " + in.Window.String()
}
