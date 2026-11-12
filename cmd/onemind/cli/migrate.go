// SPDX-License-Identifier: Apache-2.0

package cli

// onemind migrate: move a namespace of an existing Kubernetes cluster onto a
// OneMind box as a private app (CORE-DEPLOY-6, docs/leap/core/MIGRATE.md).
//
// The gateway does the work; this group reads the owner's kubeconfig file,
// sends it with the request (the gateway keeps it in memory only), prints the
// dry-run report and files the approved steps: import, copy, cutover, revert.

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/spf13/cobra"
)

func migrateCommands(a *App) []*cobra.Command {
	m := &cobra.Command{Use: "migrate", Short: "Move a namespace of an existing Kubernetes cluster onto this box as a private app"}

	var ns string
	var cp, cut bool
	role := &cobra.Command{
		Use:   "role --namespace NS [--copy] [--cutover]",
		Short: "Print the minimal RBAC to apply on the old cluster (kubectl apply -f -)",
		Args:  cobra.NoArgs,
		RunE:  func(*cobra.Command, []string) error { return migrateRole(ns, cp, cut, a.Stdout) },
	}
	role.Flags().StringVar(&ns, "namespace", "", "the namespace to move")
	role.Flags().BoolVar(&cp, "copy", false, "also allow the copy step (create and delete its own helper pods, read their logs)")
	role.Flags().BoolVar(&cut, "cutover", false, "also allow OneMind to scale the old workloads at switch-over")

	var pKube, pCtx, pApp, pName, pNS string
	plan := &cobra.Command{
		Use:   "plan --kubeconfig FILE --namespace NS [--kube-context C] [--app ID] [--name NAME]",
		Short: "Read the old namespace (dry run) and print the report; nothing is changed",
		Args:  cobra.NoArgs,
		RunE:  func(*cobra.Command, []string) error { return migratePlan(a, pKube, pNS, pCtx, pApp, pName) },
	}
	plan.Flags().StringVar(&pKube, "kubeconfig", "", "self-contained kubeconfig of the cluster you are moving off")
	plan.Flags().StringVar(&pNS, "namespace", "", "namespace to move")
	plan.Flags().StringVar(&pCtx, "kube-context", "", "kubeconfig context (default: current-context)")
	plan.Flags().StringVar(&pApp, "app", "", "app id on the box (default: the namespace)")
	plan.Flags().StringVar(&pName, "name", "", "display name (default: the namespace)")

	list := &cobra.Command{
		Use:   "list",
		Short: "Migration plans on this box",
		Args:  cobra.NoArgs,
		RunE:  func(*cobra.Command, []string) error { return migrateList(a) },
	}
	show := &cobra.Command{
		Use:   "show PLAN",
		Short: "One plan: report, state, copies",
		Args:  cobra.ExactArgs(1),
		RunE:  func(_ *cobra.Command, args []string) error { return migrateShow(a, args[0]) },
	}
	m.AddCommand(role, plan, list, show)

	for _, step := range []string{"import", "copy", "cutover", "revert"} {
		step := step
		var o stepOpts
		c := &cobra.Command{
			Use:  step + " PLAN",
			Args: cobra.ExactArgs(1),
			RunE: func(_ *cobra.Command, args []string) error { return migrateStep(a, step, args[0], o) },
		}
		c.Flags().BoolVar(&o.wait, "wait", false, "wait until the step is approved and finished")
		c.Flags().DurationVar(&o.waitTimeout, "wait-timeout", 24*time.Hour, "how long --wait waits")
		c.Flags().StringVar(&o.reason, "reason", "", "why (shown on the approval card)")
		switch step {
		case "import":
			c.Short = "File the import step (an owner approves it)"
		case "copy":
			c.Short = "File the data copy step (an owner approves it)"
			c.Flags().StringArrayVar(&o.pvcs, "pvc", nil, "copy only this volume (repeatable; default: all)")
		case "cutover":
			c.Short = "File the switch-over step (an owner approves it)"
			c.Flags().BoolVar(&o.stopOld, "stop-old", false, "let OneMind scale the old workloads to 0 (needs onemind migrate role --cutover)")
		case "revert":
			c.Short = "File the undo step (an owner approves it)"
		}
		if step == "copy" || step == "cutover" || step == "revert" {
			c.Flags().StringVar(&o.kubeconfig, "kubeconfig", "", "self-contained kubeconfig of the old cluster")
			c.Flags().StringVar(&o.kubeContext, "kube-context", "", "kubeconfig context (default: current-context)")
		}
		m.AddCommand(c)
	}
	return []*cobra.Command{m}
}

// ---- shared ------------------------------------------------------------------

type gatewayError struct {
	Error   string `json:"error"`
	Message string `json:"message"`
}

// hub resolves the box and token with the usual precedence (flag, environment, context).
func (a *App) migHub() (base, token string, err error) {
	t, err := a.resolve()
	if err != nil {
		return "", "", err
	}
	return strings.TrimRight(t.hub, "/"), t.token, nil
}

var planIDRe = regexp.MustCompile(`^mig_[0-9A-Z]{26}$`)

func onePlan(pos []string) (string, error) {
	if len(pos) != 1 {
		return "", errors.New("give exactly one plan id (see onemind migrate list)")
	}
	if !planIDRe.MatchString(pos[0]) {
		return "", fmt.Errorf("%q is not a plan id (mig_...)", pos[0])
	}
	return pos[0], nil
}

// fileRefRe finds kubeconfig keys that point at files or run commands. The
// gateway refuses them too; checking here gives the fix before anything is sent.
var fileRefRe = regexp.MustCompile(`(?m)(?:^|[{,])\s*"?(certificate-authority|client-certificate|client-key|tokenFile|exec|auth-provider)"?\s*:`)

func readKubeconfig(path string) (string, error) {
	if path == "" {
		return "", errors.New("--kubeconfig is required (onemind migrate role shows how to make one)")
	}
	f, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, 64<<10+1))
	if err != nil {
		return "", err
	}
	if len(data) > 64<<10 {
		return "", errors.New("kubeconfig is larger than 64 KiB")
	}
	if m := fileRefRe.FindSubmatch(data); m != nil {
		return "", fmt.Errorf("kubeconfig uses %q; the box needs a self-contained one with a token or client certificate "+
			"(kubectl config view --minify --flatten --raw, or see onemind migrate role)", string(m[1]))
	}
	return string(data), nil
}

// send makes one JSON request to the gateway and returns the body for a 2xx.
func send(method, url, token string, body any) ([]byte, int, error) {
	var rd io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, 0, err
		}
		rd = bytes.NewReader(b)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, method, url, rd)
	if err != nil {
		return nil, 0, err
	}
	req.Header.Set("Accept", "application/json")
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	out, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, resp.StatusCode, err
	}
	if resp.StatusCode < 200 || resp.StatusCode > 299 {
		var ge gatewayError
		if json.Unmarshal(out, &ge) == nil && ge.Error != "" {
			return nil, resp.StatusCode, fmt.Errorf("HTTP %d %s: %s", resp.StatusCode, ge.Error, ge.Message)
		}
		return nil, resp.StatusCode, fmt.Errorf("%s: HTTP %d", url, resp.StatusCode)
	}
	return out, resp.StatusCode, nil
}

func printRaw(out io.Writer, body []byte) error {
	var v any
	if err := json.Unmarshal(body, &v); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	return printJSON(out, v)
}

// ---- role ---------------------------------------------------------------------

func migrateRole(ns string, cp, cut bool, out io.Writer) error {
	if !regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`).MatchString(ns) {
		return errors.New("--namespace must be a namespace name")
	}
	_, err := io.WriteString(out, roleYAML(ns, cp, cut))
	return err
}

func roleYAML(ns string, cp, cut bool) string {
	var b strings.Builder
	fmt.Fprintf(&b, `# Access for the OneMind migration kit to namespace %[1]s, and nothing else.
# Apply it on the cluster you are moving off:   onemind migrate role --namespace %[1]s | kubectl apply -f -
# Then make a self-contained kubeconfig for it (the token expires after 8 hours):
#   SERVER=$(kubectl config view --minify -o jsonpath='{.clusters[0].cluster.server}')
#   kubectl config view --minify --flatten --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d > migrate-ca.crt
#   kubectl config --kubeconfig=migrate.kubeconfig set-cluster old --server="$SERVER" --certificate-authority=migrate-ca.crt --embed-certs=true
#   kubectl config --kubeconfig=migrate.kubeconfig set-credentials onemind-migrate --token="$(kubectl -n %[1]s create token onemind-migrate --duration=8h)"
#   kubectl config --kubeconfig=migrate.kubeconfig set-context old --cluster=old --user=onemind-migrate --namespace=%[1]s
#   kubectl config --kubeconfig=migrate.kubeconfig use-context old
# Secrets are never read: their values are re-entered on the box.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: onemind-migrate
  namespace: %[1]s
automountServiceAccountToken: false
`, ns)
	rules := `- apiGroups: [""]
  resources: [pods, services, persistentvolumeclaims, configmaps]
  verbs: [get, list]
- apiGroups: [apps]
  resources: [deployments, statefulsets, daemonsets]
  verbs: [get, list]
- apiGroups: [networking.k8s.io]
  resources: [ingresses]
  verbs: [get, list]
- apiGroups: [batch]
  resources: [jobs, cronjobs]
  verbs: [get, list]
`
	writeRole(&b, ns, "onemind-migrate-read", "read the namespace (plan)", rules)
	if cp {
		writeRole(&b, ns, "onemind-migrate-copy", "run the copy helper pods", `- apiGroups: [""]
  resources: [pods]
  verbs: [create, delete]
- apiGroups: [""]
  resources: [pods/log]
  verbs: [get]
`)
	}
	if cut {
		writeRole(&b, ns, "onemind-migrate-scale", "scale the old workloads at switch-over and revert", `- apiGroups: [apps]
  resources: [deployments/scale, statefulsets/scale]
  verbs: [patch]
`)
	}
	return b.String()
}

func writeRole(b *strings.Builder, ns, name, why, rules string) {
	fmt.Fprintf(b, `---
# %[3]s
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: %[2]s
  namespace: %[1]s
rules:
%[4]s---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: %[2]s
  namespace: %[1]s
subjects:
- kind: ServiceAccount
  name: onemind-migrate
  namespace: %[1]s
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: %[2]s
`, ns, name, why, rules)
}

// ---- plan, list, show ------------------------------------------------------------

type finding struct {
	Level   string  `json:"level"`
	Kind    string  `json:"kind"`
	Name    string  `json:"name"`
	Message string  `json:"message"`
	Hint    *string `json:"hint"`
}

type planView struct {
	ID           string `json:"id"`
	AppID        string `json:"app_id"`
	Name         string `json:"name"`
	Namespace    string `json:"namespace"`
	State        string `json:"state"`
	Next         string `json:"next"`
	BundleSHA256 string `json:"bundle_sha256"`
	LastError    string `json:"last_error"`
	BusyAction   string `json:"busy_action_id"`
	Report       struct {
		Blocking int            `json:"blocking"`
		Counts   map[string]int `json:"counts"`
		Findings []finding      `json:"findings"`
		Volumes  []struct {
			PVC  string `json:"pvc"`
			Size string `json:"size"`
		} `json:"volumes"`
		Hosts    []string `json:"hosts"`
		Warnings []string `json:"warnings"`
	} `json:"report"`
	Copies []struct {
		PVC         string `json:"pvc"`
		Phase       string `json:"phase"`
		State       string `json:"state"`
		Files       *int   `json:"files"`
		FailedFiles *int   `json:"failed_files"`
		FinishedAt  string `json:"finished_at"`
	} `json:"copies"`
}

func migratePlan(a *App, kc, ns, ctxName, app, name string) error {
	base, token, err := a.migHub()
	if err != nil {
		return err
	}
	if ns == "" {
		return errors.New("--namespace is required")
	}
	text, err := readKubeconfig(kc)
	if err != nil {
		return err
	}
	body := map[string]any{"kubeconfig": text, "namespace": ns}
	for k, v := range map[string]string{"context": ctxName, "app_id": app, "name": name} {
		if v != "" {
			body[k] = v
		}
	}
	raw, _, err := send(http.MethodPost, base+"/v1/migrate/plans", token, body)
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printRaw(a.Stdout, raw)
	}
	var p planView
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	return printPlan(a.Stdout, p, true)
}

func printPlan(out io.Writer, p planView, findings bool) error {
	w := tabwriter.NewWriter(out, 0, 0, 2, ' ', 0)
	fmt.Fprintf(w, "Plan\t%s\tnamespace %s → private app %s (%q)\n", p.ID, p.Namespace, p.AppID, p.Name)
	fmt.Fprintf(w, "State\t%s\t\n", p.State)
	if findings {
		for _, f := range p.Report.Findings {
			fmt.Fprintf(w, "%s\t%s/%s\t%s\n", strings.ToUpper(f.Level), f.Kind, f.Name, f.Message)
			if f.Hint != nil && *f.Hint != "" {
				fmt.Fprintf(w, "\t\t↳ %s\n", *f.Hint)
			}
		}
	}
	if len(p.Report.Volumes) > 0 {
		vols := make([]string, 0, len(p.Report.Volumes))
		for _, v := range p.Report.Volumes {
			vols = append(vols, fmt.Sprintf("%s (%s)", v.PVC, v.Size))
		}
		fmt.Fprintf(w, "Data\t%d volume(s) to copy\t%s\n", len(vols), strings.Join(vols, ", "))
	}
	for _, c := range p.Copies {
		detail := c.State
		if c.Files != nil {
			detail += fmt.Sprintf(", %d file(s)", *c.Files)
		}
		if c.FailedFiles != nil && *c.FailedFiles > 0 {
			detail += fmt.Sprintf(", %d differ", *c.FailedFiles)
		}
		fmt.Fprintf(w, "Copy\t%s (%s)\t%s\n", c.PVC, c.Phase, detail)
	}
	for _, warn := range p.Report.Warnings {
		fmt.Fprintf(w, "Warning\t\t%s\n", warn)
	}
	if p.LastError != "" {
		fmt.Fprintf(w, "Last error\t\t%s\n", p.LastError)
	}
	c := p.Report.Counts
	fmt.Fprintf(w, "Result\t%d blocking\t%d fixed · %d to re-enter · %d dropped · %d skipped · %d notes\n",
		p.Report.Blocking, c["fixed"], c["move"], c["drop"], c["skip"], c["note"])
	if next := nextHint(p); next != "" {
		fmt.Fprintf(w, "Next\t\t%s\n", next)
	}
	return w.Flush()
}

func nextHint(p planView) string {
	if p.BusyAction != "" {
		return "action " + p.BusyAction + " is running (onemind migrate show " + p.ID + ")"
	}
	switch {
	case p.Report.Blocking > 0:
		return "fix the FAIL lines in the source cluster, then plan again"
	case p.Next == "import":
		return "onemind migrate import " + p.ID
	case p.Next == "copy":
		return "onemind migrate copy " + p.ID + " --kubeconfig FILE"
	case p.Next == "cutover":
		return "check the new app, then: onemind migrate cutover " + p.ID + " --kubeconfig FILE --stop-old"
	case p.Next == "done" && len(p.Report.Hosts) > 0:
		return "point " + strings.Join(p.Report.Hosts, ", ") + " at this box; keep the old app for 14 days"
	}
	return ""
}

func migrateList(a *App) error {
	base, token, err := a.migHub()
	if err != nil {
		return err
	}
	raw, _, err := send(http.MethodGet, base+"/v1/migrate/plans", token, nil)
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printRaw(a.Stdout, raw)
	}
	var plans []planView
	if err := json.Unmarshal(raw, &plans); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	w := tabwriter.NewWriter(a.Stdout, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "PLAN\tAPP\tNAMESPACE\tSTATE\tBLOCKING\tNEXT")
	for _, p := range plans {
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%d\t%s\n", p.ID, p.AppID, p.Namespace, p.State, p.Report.Blocking, dash(p.Next))
	}
	return w.Flush()
}

func migrateShow(a *App, planArg string) error {
	id, err := onePlan([]string{planArg})
	if err != nil {
		return err
	}
	base, token, err := a.migHub()
	if err != nil {
		return err
	}
	raw, _, err := send(http.MethodGet, base+"/v1/migrate/plans/"+id, token, nil)
	if err != nil {
		return err
	}
	if a.G.JSON {
		return printRaw(a.Stdout, raw)
	}
	var p planView
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	return printPlan(a.Stdout, p, true)
}

// ---- steps ------------------------------------------------------------------------

type stepOpts struct {
	kubeconfig, kubeContext, reason string
	wait, stopOld                   bool
	waitTimeout                     time.Duration
	pvcs                            []string
}

type actionView struct {
	ID     string `json:"id"`
	Type   string `json:"type"`
	State  string `json:"state"`
	Result *struct {
		Message string `json:"message"`
	} `json:"result"`
}

var terminal = map[string]bool{"succeeded": true, "failed": true, "outcome_unknown": true, "cancelled": true, "expired": true}

// pollInterval is how often --wait asks; tests shorten it.
var pollInterval = 3 * time.Second

func migrateStep(a *App, step, planArg string, o stepOpts) error {
	id, err := onePlan([]string{planArg})
	if err != nil {
		return err
	}
	base, token, err := a.migHub()
	if err != nil {
		return err
	}
	out := a.Stdout
	body := map[string]any{}
	if o.reason != "" {
		body["reason"] = o.reason
	}
	if step == "copy" || step == "cutover" || (o.kubeconfig != "" && step == "revert") {
		text, err := readKubeconfig(o.kubeconfig)
		if err != nil {
			return err
		}
		body["kubeconfig"] = text
		if o.kubeContext != "" {
			body["context"] = o.kubeContext
		}
	}
	if len(o.pvcs) > 0 {
		pv := append([]string(nil), o.pvcs...)
		sort.Strings(pv)
		body["pvcs"] = pv
	}
	if step == "cutover" {
		body["stop_old"] = o.stopOld
	}
	raw, _, err := send(http.MethodPost, base+"/v1/migrate/plans/"+id+"/"+step, token, body)
	if err != nil {
		return err
	}
	var act actionView
	if err := json.Unmarshal(raw, &act); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	if a.G.JSON && !o.wait {
		return printRaw(out, raw)
	}
	fmt.Fprintf(out, "action %s  %s  %s\n", act.ID, act.Type, act.State)
	if act.State == "awaiting_approval" {
		fmt.Fprintf(out, "approve it in the dashboard or on your phone (POST /v1/actions/%s/approve)\n", act.ID)
	}
	if !o.wait {
		return nil
	}
	return waitAction(out, base, token, act.ID, o.waitTimeout, a.G.JSON)
}

func waitAction(out io.Writer, base, token, id string, timeout time.Duration, asJSON bool) error {
	deadline := time.Now().Add(timeout)
	last := ""
	for {
		raw, _, err := send(http.MethodGet, base+"/v1/actions/"+id, token, nil)
		if err != nil {
			return err
		}
		var a actionView
		if err := json.Unmarshal(raw, &a); err != nil {
			return fmt.Errorf("gateway returned invalid JSON: %w", err)
		}
		if a.State != last && !asJSON {
			fmt.Fprintf(out, "%s  %s\n", time.Now().Format("15:04:05"), a.State)
			last = a.State
		}
		if terminal[a.State] {
			if asJSON {
				return printRaw(out, raw)
			}
			if a.Result != nil && a.Result.Message != "" {
				sc := bufio.NewScanner(strings.NewReader(a.Result.Message))
				for sc.Scan() {
					fmt.Fprintln(out, "  "+sc.Text())
				}
			}
			if a.State != "succeeded" {
				return fmt.Errorf("action %s ended %s", id, a.State)
			}
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("action %s still %s after %s", id, a.State, timeout)
		}
		time.Sleep(pollInterval)
	}
}
