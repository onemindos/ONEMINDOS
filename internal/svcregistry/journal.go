// SPDX-License-Identifier: Apache-2.0

package svcregistry

import (
	"context"
	"errors"
	"fmt"
	"io"
	"strconv"
	"time"
)

// The whole-system journal (P-07). Unlike Logs it is not limited to registry units: the owner may read the
// kernel, the SSH daemon and any unit on the box. It is read only, every value is checked against a short
// allow-list before it reaches journalctl (no free-form match strings, so no way to read another user's
// journal fields), and the gateway redacts every line before anyone sees it.

// ErrBadJournalQuery: a unit, priority, boot or line count that is not one of the accepted shapes.
var ErrBadJournalQuery = errors.New("journal query: unit, priority, boot or lines is not valid")

// MaxJournalBoots is how far back --boot may reach (-1 is the previous boot).
const MaxJournalBoots = 50

// JournalQuery is one read of the journal. The zero Unit and Priority mean "all"; Boot 0 is this boot.
type JournalQuery struct {
	Unit     string // a unit name (service, socket, timer or path), or empty for every unit
	Priority string // 0-7 or emerg..debug: that level and more severe; empty for all
	Boot     int    // 0 = this boot, -1 = the previous one, down to -MaxJournalBoots
	Lines    int    // 1-MaxLogLines
	Follow   bool   // keep streaming new lines for at most FollowMax (this boot only)
}

var priorityNames = map[string]bool{"emerg": true, "alert": true, "crit": true, "err": true, "warning": true, "notice": true, "info": true, "debug": true}

// Validate checks q against the allow-lists.
func (q JournalQuery) Validate() error {
	if q.Unit != "" && !unitRE.MatchString(q.Unit) {
		return fmt.Errorf("%w: unit", ErrBadJournalQuery)
	}
	if p := q.Priority; p != "" && !priorityNames[p] {
		if n, err := strconv.Atoi(p); err != nil || n < 0 || n > 7 || len(p) != 1 {
			return fmt.Errorf("%w: priority", ErrBadJournalQuery)
		}
	}
	if q.Boot > 0 || q.Boot < -MaxJournalBoots {
		return fmt.Errorf("%w: boot", ErrBadJournalQuery)
	}
	if q.Lines < 1 || q.Lines > MaxLogLines {
		return fmt.Errorf("%w: lines must be 1-%d", ErrBadJournalQuery, MaxLogLines)
	}
	if q.Follow && q.Boot != 0 {
		return fmt.Errorf("%w: only this boot can be followed", ErrBadJournalQuery)
	}
	return nil
}

// JournalArgs is the journalctl command line for q, after Validate. Every value is one argv element joined
// with "=" so none can be read as another option.
func (q JournalQuery) JournalArgs() []string {
	args := []string{"--no-pager", "--quiet", "--output=short-iso", "--lines=" + strconv.Itoa(q.Lines), "--boot=" + strconv.Itoa(q.Boot)}
	if q.Unit != "" {
		args = append(args, "--unit="+q.Unit)
	}
	if q.Priority != "" {
		args = append(args, "--priority="+q.Priority)
	}
	if q.Follow {
		args = append(args, "--follow")
	}
	return args
}

// SystemJournal writes the journal lines q asks for to w, for at most 30 seconds (FollowMax with Follow) or
// until ctx ends. ErrBadJournalQuery is returned before anything is written.
func (r *Reader) SystemJournal(ctx context.Context, q JournalQuery, w io.Writer) error {
	if err := q.Validate(); err != nil {
		return err
	}
	journal := r.Journal
	if journal == nil {
		journal = Journalctl
	}
	limit := 30 * time.Second
	if q.Follow {
		limit = FollowMax
	}
	ctx, cancel := context.WithTimeout(ctx, limit)
	defer cancel()
	return journal(ctx, q.JournalArgs(), w)
}
