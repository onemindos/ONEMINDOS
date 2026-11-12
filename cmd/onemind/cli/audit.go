// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func auditCommands(a *App) []*cobra.Command {
	audit := &cobra.Command{Use: "audit", Short: "The hash-chained audit log: verify and read"}
	var file string
	verify := &cobra.Command{
		Use:   "verify",
		Short: "Recompute every hash (from the box, or a local copy with --file)",
		Long: "Downloads the log (GET /v1/audit/events, owner or adult), recomputes each hash with the rule of\n" +
			"core/onemind_core/audit.py and compares the head with the gateway's own check. --file checks a local\n" +
			"JSONL copy offline and needs no credential. A file proves only that the chain is self-consistent: a\n" +
			"full rewrite is caught only by a signed checkpoint kept off the box (not built yet, H-10). Exit 8 on failure.",
		Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			if file != "" {
				f, err := os.Open(file)
				if err != nil {
					return err
				}
				defer f.Close()
				return a.reportChain(onemind.VerifyChain(f), "file "+file, nil)
			}
			return a.verifyRemote()
		},
	}
	verify.Flags().StringVar(&file, "file", "", "a local JSONL copy of the log")

	var n int
	var follow bool
	var actionID, principal string
	tail := &cobra.Command{
		Use:   "tail",
		Short: "Print the last entries; -f follows",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.auditTail(n, follow, actionID, principal)
		},
	}
	tail.Flags().IntVarP(&n, "lines", "n", 50, "how many entries")
	tail.Flags().BoolVarP(&follow, "follow", "f", false, "keep printing new entries")
	tail.Flags().StringVar(&actionID, "action", "", "only entries about this action")
	tail.Flags().StringVar(&principal, "principal", "", "only entries by this principal id")
	audit.AddCommand(verify, tail)
	return []*cobra.Command{audit}
}

// allRecords pages through GET /v1/audit/events keeping the gateway's raw JSON for each record.
func allRecords(ctx context.Context, c *onemind.Client, q onemind.AuditQuery) ([]json.RawMessage, error) {
	var out []json.RawMessage
	q.Limit = 500
	for {
		path := "/v1/audit/events?" + auditValues(q)
		var page []json.RawMessage
		if err := c.Do(ctx, http.MethodGet, path, nil, &page); err != nil {
			return nil, err
		}
		out = append(out, page...)
		if len(page) < q.Limit {
			return out, nil
		}
		var last struct {
			Seq int `json:"seq"`
		}
		_ = json.Unmarshal(page[len(page)-1], &last)
		q.AfterSeq = last.Seq
	}
}

func auditValues(q onemind.AuditQuery) string {
	parts := []string{fmt.Sprintf("limit=%d", q.Limit)}
	if q.AfterSeq > 0 {
		parts = append(parts, fmt.Sprintf("after_seq=%d", q.AfterSeq))
	}
	if q.ActionID != "" {
		parts = append(parts, "action_id="+urlq(q.ActionID))
	}
	if q.PrincipalID != "" {
		parts = append(parts, "principal_id="+urlq(q.PrincipalID))
	}
	return strings.Join(parts, "&")
}

func (a *App) verifyRemote() error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	ctx := bg()
	recs, err := allRecords(ctx, c, onemind.AuditQuery{})
	if err != nil {
		return err
	}
	// Rebuild the JSONL exactly: decode with UseNumber, re-encode canonically (VerifyChain does the same).
	var buf bytes.Buffer
	for _, r := range recs {
		dec := json.NewDecoder(bytes.NewReader(r))
		dec.UseNumber()
		var m map[string]any
		if err := dec.Decode(&m); err != nil {
			return exitWith(ExitVerifyFailed, "verify_failed", "the gateway sent a record that is not JSON")
		}
		buf.WriteString(onemind.CanonicalJSON(m))
		buf.WriteByte('\n')
	}
	res := onemind.VerifyChain(&buf)
	server, serr := c.Audit.Verify(ctx)
	return a.reportChain(res, "box "+c.BaseURL(), func() error {
		if serr != nil {
			return serr
		}
		if !server.Ok {
			return exitWith(ExitVerifyFailed, "verify_failed", "the gateway's own check failed: "+server.Reason)
		}
		// Records may be appended between the two calls; at the same seq the hashes must agree.
		if server.Head != nil && res.Head != nil && server.Head.Seq == res.Head.Seq && server.Head.Hash != res.Head.Hash {
			return exitWith(ExitVerifyFailed, "verify_failed", "the gateway's head hash differs from the downloaded chain")
		}
		return nil
	})
}

func (a *App) reportChain(res onemind.ChainResult, source string, extra func() error) error {
	var extraErr error
	if extra != nil {
		extraErr = extra()
	}
	if a.G.JSON {
		if err := printJSON(a.Stdout, map[string]any{"schema": "onemind.cli.audit_verify/v1", "source": source, "result": res,
			"checkpoint": nil, "checks": []string{"chain"}}); err != nil {
			return err
		}
	} else if res.OK {
		head := "empty log"
		if res.Head != nil {
			head = fmt.Sprintf("head seq %d sha256:%s…", res.Head.Seq, res.Head.Hash[:12])
		}
		fmt.Fprintf(a.Stdout, "%d entries · chain ok · %s\n", res.Records, head)
		fmt.Fprintf(a.Stdout, "Checked: the chain of %s. Not checked: a signed checkpoint (none exist yet, H-10).\n", source)
	} else {
		fmt.Fprintf(a.Stdout, "FAIL at seq %d: %s\n", *res.FirstBadSeq, res.Reason)
	}
	if !res.OK {
		return exitWith(ExitVerifyFailed, "verify_failed", fmt.Sprintf("audit chain broken at seq %d", *res.FirstBadSeq))
	}
	var ee *exitError
	if errors.As(extraErr, &ee) {
		return extraErr
	}
	if extraErr != nil && !errors.Is(extraErr, onemind.ErrPermissionDenied) {
		return extraErr
	}
	return nil
}

func (a *App) auditTail(n int, follow bool, actionID, principal string) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	recs, err := allRecords(ctx, c, onemind.AuditQuery{ActionID: actionID, PrincipalID: principal})
	if err != nil {
		return err
	}
	if n >= 0 && len(recs) > n {
		recs = recs[len(recs)-n:]
	}
	last := 0
	for _, r := range recs {
		if s, err := a.printRecord(r); err != nil {
			return err
		} else {
			last = s
		}
	}
	if !follow {
		return nil
	}
	// Follow: poll after the last seq every 2 s (works for every principal that may read the log).
	for {
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(2 * time.Second):
		}
		more, err := allRecords(ctx, c, onemind.AuditQuery{AfterSeq: last, ActionID: actionID, PrincipalID: principal})
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		for _, r := range more {
			s, err := a.printRecord(r)
			if err != nil {
				return err
			}
			last = s
		}
	}
}

func (a *App) printRecord(raw json.RawMessage) (int, error) {
	var r onemind.AuditRecord
	if err := json.Unmarshal(raw, &r); err != nil {
		return 0, err
	}
	if a.G.JSON {
		var v any
		_ = json.Unmarshal(raw, &v)
		return r.Seq, printNDJSON(a.Stdout, v)
	}
	who := "-"
	if r.Principal != nil {
		who = r.Principal.Kind + ":" + r.Principal.Id
	}
	act := "-"
	if r.ActionId != nil {
		act = *r.ActionId
	}
	_, err := fmt.Fprintln(a.Stdout, sanitize(fmt.Sprintf("%6d  %s  %-26s %-16s %s", r.Seq, r.Ts, r.Event, who, act)))
	return r.Seq, err
}
