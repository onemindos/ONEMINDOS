// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"

	"github.com/spf13/cobra"
)

// natsCommands is `onemind nats status` (issue #619): the Engine feed, GET /v1/engine, the same
// numbers as Settings > Engine in the dashboard. Connections per NATS account, each machine's leaf
// link and outbox lag, JetStream used against its cap, slow consumers. Read-only. The gateway cuts
// the answer to the caller (an owner sees everything, a machine its own, others a summary) and it
// never carries a credential, an address or a subject. --json prints the gateway's object unchanged.
func natsCommands(a *App) []*cobra.Command {
	root := &cobra.Command{Use: "nats", Short: "The message bus (NATS) as the hub sees it"}
	root.AddCommand(&cobra.Command{
		Use:   "status",
		Short: "Leaf links, outbox lag, JetStream use and connections (GET /v1/engine)",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			c, _, err := a.client()
			if err != nil {
				return err
			}
			var raw json.RawMessage
			if err := c.Do(bg(), http.MethodGet, "/v1/engine", nil, &raw); err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, raw)
			}
			var e engineView
			if err := json.Unmarshal(raw, &e); err != nil {
				return fmt.Errorf("the hub's engine feed is not readable: %w", err)
			}
			return a.printEngine(e)
		},
	})
	return []*cobra.Command{root}
}

// engineView is the part of GET /v1/engine this command prints (core/onemind_core/engine/feed.py).
type engineView struct {
	Scope   string `json:"scope"`
	Monitor struct {
		State  string            `json:"state"`
		Errors map[string]string `json:"errors"`
	} `json:"monitor"`
	Health struct {
		Status string  `json:"status"`
		Error  *string `json:"error"`
	} `json:"health"`
	Links struct {
		Up   int `json:"up"`
		Down int `json:"down"`
	} `json:"links"`
	JetStream struct {
		State     string   `json:"state"`
		Reason    string   `json:"reason"`
		Enabled   *bool    `json:"enabled"`
		UsedBytes *int64   `json:"used_bytes"`
		CapBytes  *int64   `json:"cap_bytes"`
		UsedPct   *float64 `json:"used_pct"`
	} `json:"jetstream"`
	Accounts []struct {
		Account     string  `json:"account"`
		NodeID      *string `json:"node_id"`
		Connections int     `json:"connections"`
		Leafnodes   int     `json:"leafnodes"`
	} `json:"accounts"`
	Nodes []struct {
		NodeID    string  `json:"node_id"`
		Link      string  `json:"link"`
		RTT       *string `json:"rtt"`
		Heartbeat *string `json:"heartbeat"`
		Outbox    *struct {
			Messages    *int64   `json:"messages"`
			Lag         *int64   `json:"lag"`
			LastActiveS *float64 `json:"last_active_s"`
			Error       *string  `json:"error"`
		} `json:"outbox"`
	} `json:"nodes"`
	SlowConsumers *struct {
		Total    *int `json:"total"`
		Clients  *int `json:"clients"`
		Routes   *int `json:"routes"`
		Gateways *int `json:"gateways"`
		Leafs    *int `json:"leafs"`
	} `json:"slow_consumers"`
	ConnectionsTruncated bool `json:"connections_truncated"`
}

func mib(p *int64) string {
	if p == nil {
		return "-"
	}
	return fmt.Sprintf("%.1f MiB", float64(*p)/(1<<20))
}

func i64(p *int64) string {
	if p == nil {
		return "-"
	}
	return strconv.FormatInt(*p, 10)
}

func intp(p *int) string {
	if p == nil {
		return "-"
	}
	return strconv.Itoa(*p)
}

func (a *App) printEngine(e engineView) error {
	w := a.Stdout
	health := e.Health.Status
	if e.Health.Error != nil {
		health += ": " + sanitize(*e.Health.Error)
	}
	fmt.Fprintf(w, "NATS monitor: %s (health %s)\n", e.Monitor.State, health)
	js := e.JetStream
	switch {
	case js.Enabled == nil:
		fmt.Fprintf(w, "JetStream: %s (NATS did not answer)\n", js.State)
	case !*js.Enabled:
		fmt.Fprintf(w, "JetStream: off in NATS (gateway: %s)\n", js.State)
	default:
		pct := "-"
		if js.UsedPct != nil {
			pct = fmt.Sprintf("%.1f%%", *js.UsedPct)
		}
		fmt.Fprintf(w, "JetStream: %s, %s of %s used (%s)\n", js.State, mib(js.UsedBytes), mib(js.CapBytes), pct)
	}
	if js.Reason != "" {
		fmt.Fprintf(w, "  %s\n", sanitize(js.Reason))
	}
	fmt.Fprintf(w, "Leaf links: %d up, %d down\n", e.Links.Up, e.Links.Down)
	if e.Scope == "summary" {
		fmt.Fprintln(w, "\nPer-machine and per-account detail is for the owner (and each machine for itself).")
		return nil
	}
	rows := [][]string{}
	for _, n := range e.Nodes {
		lag, msgs, active := "-", "-", "-"
		if n.Outbox != nil {
			lag, msgs = i64(n.Outbox.Lag), i64(n.Outbox.Messages)
			if n.Outbox.LastActiveS != nil {
				active = fmt.Sprintf("%.0fs ago", *n.Outbox.LastActiveS)
			}
			if n.Outbox.Error != nil {
				lag += " (error " + sanitize(*n.Outbox.Error) + ")"
			}
		}
		link := n.Link
		if link == "down" {
			link = "DOWN"
		}
		rows = append(rows, []string{n.NodeID, link, dash(sanitize(deref(n.RTT))), dash(deref(n.Heartbeat)), lag, msgs, active})
	}
	fmt.Fprintln(w)
	if err := table(w, "NODE\tLINK\tRTT\tHEARTBEAT\tOUTBOX LAG\tOUTBOX MSGS\tLAST ACTIVE", rows); err != nil {
		return err
	}
	accs := [][]string{}
	for _, x := range e.Accounts {
		accs = append(accs, []string{x.Account, dash(deref(x.NodeID)), strconv.Itoa(x.Connections), strconv.Itoa(x.Leafnodes)})
	}
	fmt.Fprintln(w)
	if err := table(w, "ACCOUNT\tNODE\tCONNECTIONS\tLEAF LINKS", accs); err != nil {
		return err
	}
	if e.ConnectionsTruncated {
		fmt.Fprintln(w, "(more connections than the monitor lists at once; the counts are a lower bound)")
	}
	if s := e.SlowConsumers; s != nil {
		fmt.Fprintf(w, "\nSlow consumers: %s (clients %s, routes %s, gateways %s, leaf links %s)\n",
			intp(s.Total), intp(s.Clients), intp(s.Routes), intp(s.Gateways), intp(s.Leafs))
	}
	keys := make([]string, 0, len(e.Monitor.Errors))
	for k := range e.Monitor.Errors {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		fmt.Fprintf(w, "monitor %s: %s\n", sanitize(k), sanitize(e.Monitor.Errors[k]))
	}
	return nil
}
