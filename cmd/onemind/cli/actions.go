// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"sort"
	"time"

	"github.com/spf13/cobra"

	onemind "github.com/onemindos/onemindos/sdk/go"
)

func actionsCommands(a *App) []*cobra.Command {
	acts := &cobra.Command{Use: "actions", Short: "The approval queue: requests, decisions and outcomes"}
	var pending bool
	var state, by string
	var limit int
	list := &cobra.Command{
		Use:   "list",
		Short: "Actions, newest first (GET /v1/actions; filters are applied here)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if pending {
				state = "awaiting_approval"
			}
			all, err := c.Actions.List(bg())
			if err != nil {
				return err
			}
			sort.SliceStable(all, func(i, j int) bool { return all[i].CreatedAt > all[j].CreatedAt })
			var kept []onemind.Action
			for _, x := range all {
				if (state == "" || x.State == state) && (by == "" || x.RequestedBy.Id == by || x.RequestedBy.Kind+":"+x.RequestedBy.Id == by) {
					kept = append(kept, x)
				}
			}
			if limit > 0 && len(kept) > limit {
				kept = kept[:limit]
			}
			if a.G.JSON {
				if kept == nil {
					kept = []onemind.Action{}
				}
				return printJSON(a.Stdout, kept)
			}
			now := time.Now()
			var rows [][]string
			for _, x := range kept {
				target, _ := x.Params["app_id"].(string)
				rows = append(rows, []string{x.Id, x.Type, target, x.RequestedBy.Kind + ":" + x.RequestedBy.Id,
					age(x.CreatedAt, now), x.State, in(x.ExpiresAt, now)})
			}
			return table(a.Stdout, "ID\tTYPE\tTARGET\tREQUESTED BY\tAGE\tSTATE\tEXPIRES", rows)
		},
	}
	list.Flags().BoolVar(&pending, "pending", false, "only actions waiting for approval")
	list.Flags().StringVar(&state, "state", "", "only this state")
	list.Flags().StringVar(&by, "by", "", "only requests by this principal (id or kind:id)")
	list.Flags().IntVar(&limit, "limit", 0, "at most N")

	info := &cobra.Command{
		Use:   "info ACTION_ID",
		Short: "One action, with the requester's note marked as untrusted",
		Args:  cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			if a.G.JSON {
				var raw any
				if err := c.Do(bg(), http.MethodGet, "/v1/actions/"+url.PathEscape(args[0]), nil, &raw); err != nil {
					return err
				}
				return printJSON(a.Stdout, raw)
			}
			x, err := c.Actions.Get(bg(), args[0])
			if err != nil {
				return err
			}
			a.showAction(c, x)
			return nil
		},
	}
	var yes bool
	decide := func(verb string) *cobra.Command {
		cmd := &cobra.Command{
			Use:   verb + " ACTION_ID",
			Short: map[string]string{"approve": "Approve a waiting action (owners only)", "deny": "Deny a waiting action (owners only)"}[verb],
			Args:  cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error {
				c, _, err := a.client()
				if err != nil {
					return err
				}
				x, err := c.Actions.Get(bg(), args[0])
				if err != nil {
					return err
				}
				if !a.G.JSON {
					a.showAction(c, x)
				}
				if x.State != "awaiting_approval" {
					return exitWith(ExitConflict, "conflict", fmt.Sprintf("action is %s, not awaiting approval", x.State))
				}
				if !yes {
					target, _ := x.Params["app_id"].(string)
					var ok bool
					if verb == "approve" && x.Type == onemind.ActionAppRemove {
						ok, err = a.confirmTyped("Approve the removal?", target, "--yes")
					} else {
						ok, err = a.confirm(map[string]string{"approve": "Approve?", "deny": "Deny?"}[verb], "--yes")
					}
					if err != nil {
						return err
					}
					if !ok {
						return exitWith(ExitPending, "pending", "nothing decided; the action still waits")
					}
				}
				var got *onemind.Action
				if verb == "approve" {
					got, err = c.Actions.Approve(bg(), args[0])
				} else {
					got, err = c.Actions.Deny(bg(), args[0])
				}
				if err != nil {
					return err
				}
				if a.G.JSON {
					return printJSON(a.Stdout, got)
				}
				fmt.Fprintf(a.Stdout, "%sd · now %s\n", map[string]string{"approve": "approve", "deny": "denie"}[verb], got.State)
				return nil
			},
		}
		cmd.Flags().BoolVar(&yes, "yes", false, "do not ask (v0 owner tokens; passkey step-up replaces this, §12.3)")
		return cmd
	}
	watch := &cobra.Command{
		Use:   "watch",
		Short: "Follow action changes live (GET /v1/events; polls if the box has no stream)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.watchActions(pending)
		},
	}
	watch.Flags().BoolVar(&pending, "pending", false, "only new requests waiting for approval")
	acts.AddCommand(list, info, watch, decide("approve"), decide("deny"))
	return []*cobra.Command{acts}
}

// showAction prints gateway facts first, then the requester's note in a labelled, quoted block.
func (a *App) showAction(c *onemind.Client, x *onemind.Action) {
	target, _ := x.Params["app_id"].(string)
	pairs := [][2]string{
		{"id", x.Id}, {"type", x.Type}, {"target", target}, {"state", x.State},
		{"requested by", x.RequestedBy.Kind + ":" + x.RequestedBy.Id}, {"created", x.CreatedAt}, {"expires", x.ExpiresAt},
	}
	if x.DecidedBy != nil {
		pairs = append(pairs, [2]string{"decided by", x.DecidedBy.Kind + ":" + x.DecidedBy.Id})
	}
	if x.Result != nil {
		if m, ok := (*x.Result)["message"].(string); ok {
			pairs = append(pairs, [2]string{"result", m})
		}
	}
	_ = kv(a.Stdout, pairs)
	if recs, _, err := c.Audit.List(bg(), onemind.AuditQuery{ActionID: x.Id, Event: "action.requested", Limit: 1}); err == nil && len(recs) == 1 {
		if reason, ok := recs[0].Data["reason"].(string); ok && reason != "" {
			untrustedBlock(a.Stdout, "Requester's note", reason)
		}
	}
}

func (a *App) watchActions(pending bool) error {
	c, _, err := a.client()
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	emit := func(event string, x *onemind.Action) error {
		if pending && x.State != "awaiting_approval" {
			return nil
		}
		if a.G.JSON {
			return printNDJSON(a.Stdout, map[string]any{"event": event, "action": x})
		}
		target, _ := x.Params["app_id"].(string)
		_, err := fmt.Fprintln(a.Stdout, sanitize(fmt.Sprintf("%s  %-22s %s  %s %s  by %s:%s", time.Now().Format("15:04:05"), event, x.Id, x.Type, target, x.RequestedBy.Kind, x.RequestedBy.Id)))
		return err
	}
	if !a.G.Quiet && !a.G.JSON {
		fmt.Fprintln(a.Stderr, "watching actions (Ctrl-C to stop)…")
	}
	err = c.Events.Subscribe(ctx, onemind.SubscribeOptions{Types: []string{"action.*"}}, func(e onemind.Event) error {
		id, _ := e.Subject["action_id"].(string)
		if id == "" {
			return nil
		}
		x, err := c.Actions.Get(ctx, id) // events carry ids only; read the object (hydrate)
		if err != nil {
			return nil
		}
		return emit(e.Type, x)
	})
	if errors.Is(err, onemind.ErrNotFound) {
		return a.pollActions(ctx, c, emit)
	}
	if errors.Is(err, context.Canceled) {
		return nil
	}
	return err
}

// pollActions is the fallback for a box without GET /v1/events: GET /v1/actions every 2 s.
func (a *App) pollActions(ctx context.Context, c *onemind.Client, emit func(string, *onemind.Action) error) error {
	seen := map[string]string{}
	first := true
	for {
		all, err := c.Actions.List(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return err
		}
		for i := range all {
			x := &all[i]
			prev, ok := seen[x.Id]
			seen[x.Id] = x.State
			if first || prev == x.State {
				continue
			}
			ev := "action.state_changed"
			if !ok {
				ev = "action.requested"
			}
			if err := emit(ev, x); err != nil {
				return err
			}
		}
		first = false
		select {
		case <-ctx.Done():
			return nil
		case <-time.After(2 * time.Second):
		}
	}
}
