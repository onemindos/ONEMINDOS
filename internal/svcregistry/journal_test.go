// SPDX-License-Identifier: Apache-2.0

package svcregistry

import (
	"context"
	"errors"
	"io"
	"strings"
	"testing"
)

func TestJournalQueryValidation(t *testing.T) {
	ok := []JournalQuery{
		{Lines: 1},
		{Unit: "sshd.service", Priority: "err", Boot: -1, Lines: 2000},
		{Unit: "onemind-gateway.service", Priority: "3", Lines: 50, Follow: true},
		{Priority: "debug", Boot: -MaxJournalBoots, Lines: 10},
	}
	for _, q := range ok {
		if err := q.Validate(); err != nil {
			t.Errorf("%+v: %v", q, err)
		}
	}
	bad := []JournalQuery{
		{Lines: 0}, {Lines: 2001},
		{Lines: 5, Unit: "--output=export"}, {Lines: 5, Unit: "x.service --vacuum"}, {Lines: 5, Unit: "sshd"},
		{Lines: 5, Priority: "8"}, {Lines: 5, Priority: "07"}, {Lines: 5, Priority: "err..debug"}, {Lines: 5, Priority: "-p"},
		{Lines: 5, Boot: 1}, {Lines: 5, Boot: -MaxJournalBoots - 1},
		{Lines: 5, Boot: -1, Follow: true},
	}
	for _, q := range bad {
		if err := q.Validate(); !errors.Is(err, ErrBadJournalQuery) {
			t.Errorf("%+v should be refused, got %v", q, err)
		}
	}
}

func TestSystemJournalRunsJournalctlWithCheckedArgs(t *testing.T) {
	var got []string
	r := &Reader{Journal: func(_ context.Context, args []string, w io.Writer) error {
		got = args
		_, err := io.WriteString(w, "a line\n")
		return err
	}}
	var sb strings.Builder
	q := JournalQuery{Unit: "sshd.service", Priority: "warning", Boot: -1, Lines: 25}
	if err := r.SystemJournal(context.Background(), q, &sb); err != nil || sb.String() != "a line\n" {
		t.Fatalf("%v %q", err, sb.String())
	}
	want := "--no-pager --quiet --output=short-iso --lines=25 --boot=-1 --unit=sshd.service --priority=warning"
	if strings.Join(got, " ") != want {
		t.Fatalf("args %v", got)
	}
	got = nil
	if err := r.SystemJournal(context.Background(), JournalQuery{Unit: "--rotate", Lines: 5}, &sb); !errors.Is(err, ErrBadJournalQuery) || got != nil {
		t.Fatalf("a bad query must not reach journalctl: %v %v", err, got)
	}
	if err := r.SystemJournal(context.Background(), JournalQuery{Lines: 5, Follow: true}, &sb); err != nil || got[len(got)-1] != "--follow" {
		t.Fatalf("follow: %v %v", err, got)
	}
}
