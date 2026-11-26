// SPDX-License-Identifier: Apache-2.0

package cli

// `onemind update fleet` and `onemind update rollouts`: which OS version every machine runs
// (GET /v1/os/fleet) and the fleet-staged rollouts (/v1/os/rollouts). Reads change nothing. Starting
// and resuming a rollout only FILE an approval request (os.rollout.start, os.rollout.resume on
// POST /v1/actions): nothing is offered to any machine until an owner approves it. Cancelling is an
// owner-only route that stops offering the version to more machines; machines already updated stay
// updated, and the gateway answers 403 to anyone but an owner.

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/spf13/cobra"
)

func fleetCommand(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "fleet",
		Short: "Every machine's OS version and update state (GET /v1/os/fleet); changes nothing",
		Args:  cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/os/fleet", func(w io.Writer, v any) error {
				m := obj(v)
				var rows [][]string
				for _, n := range list(m["machines"]) {
					x := obj(n)
					rows = append(rows, []string{dash(str(x["hostname"])), dash(str(x["board"])), str(x["status"]), dash(str(x["version"])), dash(str(x["update_state"])), dash(str(x["available_version"]))})
				}
				if err := table(w, "MACHINE\tBOARD\tSTATUS\tVERSION\tUPDATE\tON OFFER", rows); err != nil {
					return err
				}
				var vers []string
				for _, x := range list(m["versions"]) {
					vers = append(vers, fmt.Sprintf("%s x%s", str(obj(x)["version"]), str(obj(x)["count"])))
				}
				fmt.Fprintf(w, "\nVersions: %s\n", dash(strings.Join(vers, ", ")))
				if id := str(m["active_rollout_id"]); id != "" {
					fmt.Fprintf(w, "Rollout in progress: %s (onemind update rollouts show %s)\n", id, id)
				}
				return nil
			})
		},
	}
}

func rolloutsCommand(a *App) *cobra.Command {
	root := &cobra.Command{Use: "rollouts", Short: "Fleet-staged OS rollouts: list, show, start and resume (an owner approves), cancel (owner only)"}
	root.AddCommand(&cobra.Command{
		Use: "list", Short: "Rollouts, newest first (GET /v1/os/rollouts)", Args: cobra.NoArgs,
		RunE: func(*cobra.Command, []string) error {
			return a.read("/v1/os/rollouts", func(w io.Writer, v any) error {
				var rows [][]string
				for _, r := range list(v) {
					m := obj(r)
					rows = append(rows, []string{str(m["id"]), str(m["version"]), str(m["state"]), stageText(m), dash(str(m["reason"]))})
				}
				return table(w, "ROLLOUT\tVERSION\tSTATE\tSTAGE\tREASON", rows)
			})
		},
	})
	root.AddCommand(&cobra.Command{
		Use: "show ROLLOUT_ID", Short: "One rollout: its stage and each machine's state (GET /v1/os/rollouts/{id})", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.read("/v1/os/rollouts/"+url.PathEscape(args[0]), func(w io.Writer, v any) error {
				m := obj(v)
				if err := kv(w, [][2]string{{"rollout", str(m["id"])}, {"version", str(m["version"])}, {"state", str(m["state"])}, {"stage", stageText(m)}, {"reason", dash(str(m["reason"]))}}); err != nil {
					return err
				}
				var rows [][]string
				for _, n := range list(m["nodes"]) {
					x := obj(n)
					rows = append(rows, []string{str(x["node_id"]), str(x["wave"]), str(x["state"]), dash(str(x["reason"]))})
				}
				fmt.Fprintln(w)
				return table(w, "MACHINE\tWAVE\tSTATE\tREASON", rows)
			})
		},
	})
	var version, stages string
	var maxFailures int
	start := &cobra.Command{
		Use: "start --target-version V", Short: "Request a staged rollout of a version (POST /v1/actions os.rollout.start); an owner approves it", Args: cobra.NoArgs,
		RunE: func(cmd *cobra.Command, _ []string) error {
			if version == "" {
				return usageErr(cmd, "--target-version is required")
			}
			params := map[string]any{"version": version, "max_failures": maxFailures}
			if stages != "" {
				var st []int
				for _, s := range strings.Split(stages, ",") {
					n, err := strconv.Atoi(strings.TrimSpace(s))
					if err != nil {
						return usageErr(cmd, "--stages is a comma-separated list of percentages, for example 10,50,100")
					}
					st = append(st, n)
				}
				params["stages"] = st
			}
			return a.fileRolloutAction(cmd, "os.rollout.start", "rollout of "+version, params, version+stages+strconv.Itoa(maxFailures))
		},
	}
	start.Flags().StringVar(&version, "target-version", "", "the OS version to roll out")
	start.Flags().StringVar(&stages, "stages", "", "cumulative percentages of machines per wave, ending at 100 (default 10,50,100)")
	start.Flags().IntVar(&maxFailures, "max-failures", 0, "machines that may fail before the rollout pauses")
	root.AddCommand(start)
	root.AddCommand(&cobra.Command{
		Use: "resume ROLLOUT_ID", Short: "Request resuming a paused rollout (POST /v1/actions os.rollout.resume); an owner approves it", Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return a.fileRolloutAction(cmd, "os.rollout.resume", "resume of "+args[0], map[string]any{"rollout_id": args[0]}, args[0])
		},
	})
	root.AddCommand(&cobra.Command{
		Use: "cancel ROLLOUT_ID", Short: "Stop offering the version to more machines, as an owner (POST /v1/os/rollouts/{id}/cancel)", Args: cobra.ExactArgs(1),
		RunE: func(_ *cobra.Command, args []string) error {
			v, err := a.gwDo(http.MethodPost, "/v1/os/rollouts/"+url.PathEscape(args[0])+"/cancel", nil)
			if err != nil {
				return err
			}
			return a.withJSONOrText(v, func(w io.Writer, v any) error {
				_, err := fmt.Fprintf(w, "Rollout %s is %s. Machines already updated stay updated.\n", args[0], str(obj(v)["state"]))
				return err
			})
		},
	})
	return root
}

func stageText(m map[string]any) string {
	return fmt.Sprintf("%d of %d", int(floatOf(m["stage"]))+1, len(list(m["stages"])))
}

func floatOf(v any) float64 {
	f, _ := v.(float64)
	return f
}

// fileRolloutAction files one rollout request. The key is built from what is asked for and the UTC
// day, so asking twice replays the request that is already waiting instead of filing a second one.
func (a *App) fileRolloutAction(cmd *cobra.Command, typ, what string, params map[string]any, keyPart string) error {
	body := map[string]any{"type": typ, "params": params, "idempotency_key": idemKey("cli-"+strings.ReplaceAll(typ, ".", "-")+"-", keyPart),
		"expires_at": time.Now().Add(24 * time.Hour).UTC().Format(time.RFC3339)}
	v, err := a.gwDo(http.MethodPost, "/v1/actions", body)
	if err != nil {
		return err
	}
	return a.printRequested(what, v)
}
