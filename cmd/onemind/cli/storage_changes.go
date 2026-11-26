// SPDX-License-Identifier: Apache-2.0

package cli

// onemind storage request and onemind storage operation: the gateway's storage actions
// (POST /v1/storage/plans, POST /v1/storage/actions, GET /v1/storage/operations/{id}). `request`
// first asks the box for the plan, which is a dry run, and prints it; only without --dry-run does it
// FILE the request, and an owner approves it in Approvals with a passkey (a destructive action needs
// one). Nothing here approves anything. This is separate from `onemind storage plan`, which prints
// the commands for a disk on the machine you are logged in to.

import (
	"fmt"
	"io"
	"math"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/spf13/cobra"
)

var storageActionTypes = map[string][]string{ // action -> the params it needs
	"create": {"device"}, "add": {"device"}, "replace": {"member", "device"}, "remove": {"member"}, "repair": nil,
}

func storageGatewayCommands(a *App) []*cobra.Command {
	var device, member, reason string
	var dry, unprotect, wipe bool
	request := &cobra.Command{
		Use:   "request ACTION [--device DISK] [--member M] [--dry-run]",
		Short: "Show the plan for a mirror change, then file it for an owner to approve (ACTION: create, add, replace, remove, repair)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			needs, ok := storageActionTypes[args[0]]
			if !ok {
				return usageErr(cmd, "ACTION is one of create, add, replace, remove, repair")
			}
			params := map[string]any{}
			for _, n := range needs {
				v := map[string]string{"device": device, "member": member}[n]
				if v == "" {
					return usageErr(cmd, fmt.Sprintf("storage %s needs --%s", args[0], n))
				}
				params[n] = v
			}
			if unprotect {
				params["unprotect"] = true
			}
			if wipe {
				params["wipe"] = true
			}
			typ := "storage.mirror." + args[0]
			plan, err := a.gwDo(http.MethodPost, "/v1/storage/plans", map[string]any{"type": typ, "params": params})
			if err != nil {
				return err
			}
			p := obj(obj(plan)["plan"])
			if !a.G.JSON && !a.G.Quiet {
				printStoragePlan(a.Stdout, typ, p)
			}
			if p["blocked"] == true {
				if a.G.JSON {
					_ = printJSON(a.Stdout, plan)
				}
				return exitWith(ExitConflict, "conflict", "the box will not do this: a safety check failed. Nothing was filed")
			}
			if dry {
				if a.G.JSON {
					return printJSON(a.Stdout, plan)
				}
				fmt.Fprintln(a.Stdout, "\nDry run: nothing was filed.")
				return nil
			}
			body := map[string]any{"type": typ, "params": params}
			if reason != "" {
				body["reason"] = reason
			}
			// The key is built from the request and the plan, so repeating it replays the one already waiting.
			key := idemKey("cli-storage-", typ, fmt.Sprint(params), str(obj(plan)["plan_sha256"]))
			v, err := a.gwDoKeyed(http.MethodPost, "/v1/storage/actions", key, body)
			if err != nil {
				return err
			}
			return a.printRequested("storage "+args[0], obj(v)["action"])
		},
	}
	request.Flags().StringVar(&device, "device", "", "the blank disk (path, WWN or serial)")
	request.Flags().StringVar(&member, "member", "", "the member (devid:N, a disk, or missing)")
	request.Flags().BoolVar(&dry, "dry-run", false, "only show the plan; file nothing")
	request.Flags().BoolVar(&unprotect, "unprotect", false, "remove: accept going below two members (the data is then kept once, unprotected)")
	request.Flags().BoolVar(&wipe, "wipe", false, "replace or remove: erase the old disk afterwards (not for a missing member)")
	request.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")

	operation := &cobra.Command{
		Use: "operation ACTION_ID", Short: "The stored plan of a storage request and, while it runs, its journal (GET /v1/storage/operations/{id})", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/storage/operations/"+url.PathEscape(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				pairs := [][2]string{{"request", args[0]}, {"type", str(m["type"])}, {"state", str(m["state"])}, {"risk", str(m["risk"])}}
				if r := str(m["result"]); r != "" {
					pairs = append(pairs, [2]string{"result", r})
				}
				if err := kv(w, pairs); err != nil {
					return err
				}
				var rows [][]string
				for _, j := range list(m["journal"]) {
					jm := obj(j)
					rows = append(rows, []string{str(jm["step"]), str(jm["state"]), dash(str(jm["detail"]))})
				}
				if len(rows) > 0 {
					fmt.Fprintln(w)
					return table(w, "STEP\tSTATE\tDETAIL", rows)
				}
				return nil
			})
		},
	}
	return []*cobra.Command{request, operation}
}

func printStoragePlan(w io.Writer, typ string, p map[string]any) {
	fmt.Fprintf(w, "Plan for %s\n", typ)
	for _, t := range list(p["targets"]) {
		m := obj(t)
		fmt.Fprintf(w, "  would erase and use: %s %s (%s)\n", str(m["path"]), sanitize(str(m["model"])), storageSize(m["size_bytes"]))
	}
	for _, c := range list(p["checks"]) {
		m := obj(c)
		state := "ok"
		if m["ok"] != true {
			state = "FAILED"
		}
		fmt.Fprintf(w, "  check %-7s %s\n", state, sanitize(str(m["detail"])))
	}
	for _, x := range list(p["warnings"]) {
		fmt.Fprintf(w, "  warning: %s\n", sanitize(str(x)))
	}
	fmt.Fprintf(w, "  steps: %d\n", len(list(p["steps"])))
	if p["blocked"] != true && strings.HasPrefix(typ, "storage.mirror.") {
		fmt.Fprintln(w, "  an owner approves this with a passkey in Approvals before anything changes")
	}
}

// storageSize writes a byte count the way a person reads a disk label: decimal units, TB from 1000 GB
// up, at most one decimal and no trailing ".0" (256 GB, 1.5 TB, 4 TB). The dashboard's diskSize
// (dashboard/src/pages/storage/Changes.tsx) uses the same rule.
func storageSize(v any) string {
	f, ok := v.(float64)
	if !ok || f < 0 || math.IsInf(f, 0) || math.IsNaN(f) {
		return "size not reported"
	}
	n, unit := f/1e9, "GB"
	if math.Round(n*10)/10 >= 1000 {
		n, unit = f/1e12, "TB"
	}
	return strconv.FormatFloat(math.Round(n*10)/10, 'f', -1, 64) + " " + unit
}
