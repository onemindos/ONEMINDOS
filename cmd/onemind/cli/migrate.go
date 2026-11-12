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
	"flag"
	"fmt"
	"io"
	"net/http"
	"os"
	"regexp"
	"sort"
	"strings"
	"text/tabwriter"
	"time"
)

func migrateCommands() []Command {
	return []Command{
		{
			Path:  []string{"migrate", "role"},
			Usage: "onemind migrate role --namespace NS [--copy] [--cutover]",
			Run:   func(env *Env, args []string) error { return migrateRole(args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "plan"},
			Usage: "onemind migrate plan --hub URL --kubeconfig FILE --namespace NS [--context C] [--app ID] [--name NAME] [--json]",
			Run:   func(env *Env, args []string) error { return migratePlan(args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "list"},
			Usage: "onemind migrate list --hub URL [--json]",
			Run:   func(env *Env, args []string) error { return migrateList(args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "show"},
			Usage: "onemind migrate show PLAN --hub URL [--json]",
			Run:   func(env *Env, args []string) error { return migrateShow(args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "import"},
			Usage: "onemind migrate import PLAN --hub URL [--wait] [--json]",
			Run:   func(env *Env, args []string) error { return migrateStep("import", args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "copy"},
			Usage: "onemind migrate copy PLAN --hub URL --kubeconfig FILE [--pvc NAME]... [--wait] [--json]",
			Run:   func(env *Env, args []string) error { return migrateStep("copy", args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "cutover"},
			Usage: "onemind migrate cutover PLAN --hub URL --kubeconfig FILE [--stop-old] [--wait] [--json]",
			Run:   func(env *Env, args []string) error { return migrateStep("cutover", args, env.Stdout) },
		},
		{
			Path:  []string{"migrate", "revert"},
			Usage: "onemind migrate revert PLAN --hub URL [--kubeconfig FILE] [--wait] [--json]",
			Run:   func(env *Env, args []string) error { return migrateStep("revert", args, env.Stdout) },
		},
	}
}

// ---- shared ------------------------------------------------------------------

type hubFlags struct {
	hub, token *string
	asJSON     *bool
}

func addHubFlags(fs *flag.FlagSet) hubFlags {
	return hubFlags{
		hub:    fs.String("hub", os.Getenv("ONEMIND_HUB"), "gateway URL, e.g. http://hub.local:8080"),
		token:  fs.String("token", os.Getenv("ONEMIND_TOKEN"), "owner bearer token (or ONEMIND_TOKEN)"),
		asJSON: fs.Bool("json", false, "print the raw JSON response"),
	}
}

func (h hubFlags) base() (string, error) {
	if *h.hub == "" {
		return "", errors.New("--hub is required (or set ONEMIND_HUB)")
	}
	return strings.TrimRight(*h.hub, "/"), nil
}

// parseWithPositional lets flags come before or after the positional args
// (flag.Parse stops at the first non-flag).
func parseWithPositional(fs *flag.FlagSet, args []string) ([]string, error) {
	var pos []string
	for {
		if err := fs.Parse(args); err != nil {
			return nil, err
		}
		if fs.NArg() == 0 {
			return pos, nil
		}
		pos = append(pos, fs.Arg(0))
		args = fs.Args()[1:]
	}
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

func migrateRole(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migrate role", flag.ContinueOnError)
	ns := fs.String("namespace", "", "the namespace to move")
	cp := fs.Bool("copy", false, "also allow the copy step (create and delete its own helper pods, read their logs)")
	cut := fs.Bool("cutover", false, "also allow OneMind to scale the old workloads at switch-over")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if !regexp.MustCompile(`^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`).MatchString(*ns) {
		return errors.New("--namespace must be a namespace name")
	}
	_, err := io.WriteString(out, roleYAML(*ns, *cp, *cut))
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

func migratePlan(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migrate plan", flag.ContinueOnError)
	h := addHubFlags(fs)
	kc := fs.String("kubeconfig", "", "self-contained kubeconfig of the cluster you are moving off")
	ns := fs.String("namespace", "", "namespace to move")
	ctxName := fs.String("context", "", "kubeconfig context (default: current-context)")
	app := fs.String("app", "", "app id on the box (default: the namespace)")
	name := fs.String("name", "", "display name (default: the namespace)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	base, err := h.base()
	if err != nil {
		return err
	}
	if *ns == "" {
		return errors.New("--namespace is required")
	}
	text, err := readKubeconfig(*kc)
	if err != nil {
		return err
	}
	body := map[string]any{"kubeconfig": text, "namespace": *ns}
	for k, v := range map[string]string{"context": *ctxName, "app_id": *app, "name": *name} {
		if v != "" {
			body[k] = v
		}
	}
	raw, _, err := send(http.MethodPost, base+"/v1/migrate/plans", *h.token, body)
	if err != nil {
		return err
	}
	if *h.asJSON {
		return printRaw(out, raw)
	}
	var p planView
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	return printPlan(out, p, true)
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

func migrateList(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migrate list", flag.ContinueOnError)
	h := addHubFlags(fs)
	if err := fs.Parse(args); err != nil {
		return err
	}
	base, err := h.base()
	if err != nil {
		return err
	}
	raw, _, err := send(http.MethodGet, base+"/v1/migrate/plans", *h.token, nil)
	if err != nil {
		return err
	}
	if *h.asJSON {
		return printRaw(out, raw)
	}
	var plans []planView
	if err := json.Unmarshal(raw, &plans); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	w := tabwriter.NewWriter(out, 0, 0, 2, ' ', 0)
	fmt.Fprintln(w, "PLAN\tAPP\tNAMESPACE\tSTATE\tBLOCKING\tNEXT")
	for _, p := range plans {
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%d\t%s\n", p.ID, p.AppID, p.Namespace, p.State, p.Report.Blocking, dash(p.Next))
	}
	return w.Flush()
}

func migrateShow(args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migrate show", flag.ContinueOnError)
	h := addHubFlags(fs)
	pos, err := parseWithPositional(fs, args)
	if err != nil {
		return err
	}
	id, err := onePlan(pos)
	if err != nil {
		return err
	}
	base, err := h.base()
	if err != nil {
		return err
	}
	raw, _, err := send(http.MethodGet, base+"/v1/migrate/plans/"+id, *h.token, nil)
	if err != nil {
		return err
	}
	if *h.asJSON {
		return printRaw(out, raw)
	}
	var p planView
	if err := json.Unmarshal(raw, &p); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	return printPlan(out, p, true)
}

// ---- steps ------------------------------------------------------------------------

type pvcList []string

func (p *pvcList) String() string     { return strings.Join(*p, ",") }
func (p *pvcList) Set(v string) error { *p = append(*p, v); return nil }

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

func migrateStep(step string, args []string, out io.Writer) error {
	fs := flag.NewFlagSet("migrate "+step, flag.ContinueOnError)
	h := addHubFlags(fs)
	kc := fs.String("kubeconfig", "", "self-contained kubeconfig of the old cluster")
	ctxName := fs.String("context", "", "kubeconfig context (default: current-context)")
	reason := fs.String("reason", "", "why (shown on the approval card)")
	wait := fs.Bool("wait", false, "wait until the step is approved and finished")
	timeout := fs.Duration("timeout", 24*time.Hour, "how long --wait waits")
	var pvcs pvcList
	stopOld := false
	if step == "copy" {
		fs.Var(&pvcs, "pvc", "copy only this volume (repeatable; default: all)")
	}
	if step == "cutover" {
		fs.BoolVar(&stopOld, "stop-old", false, "let OneMind scale the old workloads to 0 (needs onemind migrate role --cutover)")
	}
	pos, err := parseWithPositional(fs, args)
	if err != nil {
		return err
	}
	id, err := onePlan(pos)
	if err != nil {
		return err
	}
	base, err := h.base()
	if err != nil {
		return err
	}
	body := map[string]any{}
	if *reason != "" {
		body["reason"] = *reason
	}
	needsKube := step == "copy" || step == "cutover"
	if needsKube || (*kc != "" && step == "revert") {
		text, err := readKubeconfig(*kc)
		if err != nil {
			return err
		}
		body["kubeconfig"] = text
		if *ctxName != "" {
			body["context"] = *ctxName
		}
	}
	if len(pvcs) > 0 {
		sort.Strings(pvcs)
		body["pvcs"] = []string(pvcs)
	}
	if step == "cutover" {
		body["stop_old"] = stopOld
	}
	raw, _, err := send(http.MethodPost, base+"/v1/migrate/plans/"+id+"/"+step, *h.token, body)
	if err != nil {
		return err
	}
	var a actionView
	if err := json.Unmarshal(raw, &a); err != nil {
		return fmt.Errorf("gateway returned invalid JSON: %w", err)
	}
	if *h.asJSON && !*wait {
		return printRaw(out, raw)
	}
	fmt.Fprintf(out, "action %s  %s  %s\n", a.ID, a.Type, a.State)
	if a.State == "awaiting_approval" {
		fmt.Fprintf(out, "approve it in the dashboard or on your phone (POST /v1/actions/%s/approve)\n", a.ID)
	}
	if !*wait {
		return nil
	}
	return waitAction(out, base, *h.token, a.ID, *timeout, *h.asJSON)
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
