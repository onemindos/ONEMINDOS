// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"flag"
	"fmt"
	"io"
	"strings"
	"text/tabwriter"

	"github.com/spf13/cobra"

	"github.com/onemindos/onemindos/internal/storage"
)

// storageUsage is appended to the main usage text when the command is
// registered (see internal/storage/README.md, "Wiring").
const storageUsage = `  onemind storage disks  [--json]
  onemind storage health [--json] [DISK...]
  onemind storage status [--mount DIR] [--json]
  onemind storage plan create  --device DISK [--device DISK...] [--mount DIR] [--encrypt] [--key-file F] [--json]
  onemind storage plan protect --device DISK [--mount DIR] [--key-file F] [--json]
  onemind storage plan repair  [--mount DIR] [--json]
`

// newStorageCollector is replaced in tests (recorded tool output).
var newStorageCollector = storage.New

// stringList is a repeatable flag.
type stringList []string

func (s *stringList) String() string     { return strings.Join(*s, ",") }
func (s *stringList) Set(v string) error { *s = append(*s, v); return nil }

// storageCmd implements `onemind storage ...` (storage.md §4.8, STOR-9's
// read half). Everything here is read-only: plan prints commands, it never
// runs them. smartctl needs root.
func storageCmd(args []string, out io.Writer) error {
	if len(args) == 0 {
		return fmt.Errorf("usage:\n%s", storageUsage)
	}
	sub := args[0]
	if sub == "plan" {
		if len(args) < 2 {
			return fmt.Errorf("usage:\n%s", storageUsage)
		}
		sub = "plan " + args[1]
		args = args[1:]
	}
	fs := flag.NewFlagSet("storage "+sub, flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "print JSON")
	mount := fs.String("mount", "/data", "where the data set is mounted")
	encrypt := fs.Bool("encrypt", false, "plan create: LUKS2 under every member")
	keyFile := fs.String("key-file", "", "LUKS2 key file for new members (TPM2 + recovery key replace it in STOR-1)")
	var devices stringList
	fs.Var(&devices, "device", "disk path or id (repeatable)")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	ctx := context.Background()
	c := newStorageCollector()

	switch sub {
	case "disks":
		m, _ := c.MirrorStatus(ctx, *mount) // marks members when the set is mounted
		disks, err := c.Inventory(ctx, m)
		if err != nil {
			return err
		}
		if *asJSON {
			return printJSON(out, disks)
		}
		tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
		fmt.Fprintln(tw, "DISK\tSIZE\tTRAN\tMODEL\tSERIAL\tROLE")
		for _, d := range disks {
			fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\n", d.Path, human(d.SizeBytes), dash(d.Transport), dash(d.Model), dash(tailOrEmpty(d.SerialTail)), d.Role)
		}
		return tw.Flush()

	case "health":
		disks, err := c.Inventory(ctx, nil)
		if err != nil {
			return err
		}
		var res []storage.Health
		for _, d := range disks {
			if len(fs.Args()) > 0 && !contains(fs.Args(), d.Path) {
				continue
			}
			h, err := c.Health(ctx, d, storage.DefaultThresholds)
			if err != nil {
				return err
			}
			res = append(res, h)
		}
		if *asJSON {
			return printJSON(out, res)
		}
		tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
		fmt.Fprintln(tw, "DISK\tVERDICT\tTEMP\tWEAR\tHOURS\tREASONS")
		for _, h := range res {
			fmt.Fprintf(tw, "%s\t%s\t%s\t%s\t%s\t%s\n", h.Path, h.Verdict, num(h.TemperatureC, "°C"), num(h.WearPercent, "%"), num(h.PowerOnHours, ""), strings.Join(h.Reasons, "; "))
		}
		return tw.Flush()

	case "status":
		m, err := c.MirrorStatus(ctx, *mount)
		if err != nil {
			return err
		}
		if *asJSON {
			return printJSON(out, m)
		}
		fmt.Fprintf(out, "%s: %s", m.Mount, strings.ToUpper(string(m.State)))
		if m.Degraded {
			fmt.Fprint(out, " (mounted degraded)")
		}
		fmt.Fprintln(out)
		for _, r := range m.Reasons {
			fmt.Fprintln(out, "  !", r)
		}
		for _, p := range m.Profiles {
			fmt.Fprintf(out, "  %-9s %-8s %s used of %s\n", p.Kind, p.Profile, human(p.UsedBytes), human(p.TotalBytes))
		}
		for _, mem := range m.Members {
			path := mem.Path
			if mem.Missing {
				path = "MISSING"
			}
			fmt.Fprintf(out, "  devid %d  %-28s %s\n", mem.DevID, path, human(mem.SizeBytes))
		}
		if len(m.Repair) > 0 {
			fmt.Fprintln(out, "  repair:", strings.Join(m.Repair, " -> "), "(onemind storage plan repair)")
		}
		return nil

	case "plan create", "plan protect", "plan repair":
		m, err := c.MirrorStatus(ctx, *mount)
		if err != nil {
			return err
		}
		disks, err := c.Inventory(ctx, m)
		if err != nil {
			return err
		}
		o := storage.PlanOptions{Mount: *mount, Encrypt: *encrypt, KeyFile: *keyFile, Health: map[string]storage.Health{}}
		for _, ref := range devices {
			if d, ok := storage.Find(disks, ref); ok {
				if h, err := c.Health(ctx, d, storage.DefaultThresholds); err == nil {
					o.Health[d.Path] = h
				}
			}
		}
		var p storage.Plan
		switch sub {
		case "plan create":
			if len(devices) == 0 {
				return fmt.Errorf("plan create: give at least one --device")
			}
			p = storage.PlanCreate(disks, devices, o)
		case "plan protect":
			if len(devices) != 1 {
				return fmt.Errorf("plan protect: give exactly one --device")
			}
			p = storage.PlanProtect(disks, m, devices[0], o)
		default:
			p = storage.PlanRepair(m)
		}
		if *asJSON {
			return printJSON(out, p)
		}
		printPlan(out, p)
		return nil
	}
	return fmt.Errorf("unknown storage command %q\nusage:\n%s", sub, storageUsage)
}

func printPlan(out io.Writer, p storage.Plan) {
	fmt.Fprintf(out, "PLAN %s on %s (dry run, nothing was changed)\n", p.Kind, p.Mount)
	if p.DataProfile != "" {
		fmt.Fprintf(out, "  profile: data %s, metadata %s", p.DataProfile, p.MetaProfile)
		if p.Kind != "repair" {
			fmt.Fprintf(out, ", encrypted %t", p.Encrypted)
		}
		fmt.Fprintln(out)
	}
	for _, t := range p.Targets {
		fmt.Fprintf(out, "  WILL ERASE: %s  %s  model %s  serial %s\n", t.Path, human(t.SizeBytes), dash(t.Model), dash(tailOrEmpty(t.SerialTail)))
	}
	fmt.Fprintln(out, "checks:")
	for _, c := range p.Checks {
		mark := "ok  "
		if !c.OK {
			mark = "FAIL"
		}
		fmt.Fprintf(out, "  [%s] %s: %s\n", mark, c.ID, c.Detail)
	}
	for _, w := range p.Warnings {
		fmt.Fprintln(out, "  warning:", w)
	}
	if p.Blocked {
		fmt.Fprintln(out, "BLOCKED: a check failed, no steps generated")
	} else {
		fmt.Fprintln(out, "steps:")
		for i, s := range p.Steps {
			mark := ""
			if s.Destructive {
				mark = "  # ERASES DATA"
			}
			fmt.Fprintf(out, "  %2d. %s%s\n      # %s\n", i+1, s, mark, s.Why)
		}
	}
	fmt.Fprintln(out, "plan_sha256:", p.SHA256)
}

func human(b uint64) string {
	const unit = 1024
	if b < unit {
		return fmt.Sprintf("%dB", b)
	}
	div, exp := uint64(unit), 0
	for n := b / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f%ciB", float64(b)/float64(div), "KMGTPE"[exp])
}

func num(p *int, suffix string) string {
	if p == nil {
		return "-"
	}
	return fmt.Sprintf("%d%s", *p, suffix)
}

func tailOrEmpty(s string) string {
	if s == "" {
		return ""
	}
	return "…" + s
}

func contains(xs []string, v string) bool {
	for _, x := range xs {
		if x == v {
			return true
		}
	}
	return false
}

// storageCommands registers `onemind storage` (a group line in root.go). Read-only: plan
// prints commands, it never runs them.
func storageCommands(a *App) []*cobra.Command {
	return []*cobra.Command{{
		Use:                "storage disks|health|status|plan ...",
		Short:              "List disks, check their health and print storage plans (read-only)",
		DisableFlagParsing: true,
		RunE: func(_ *cobra.Command, args []string) error {
			return storageCmd(args, a.Stdout)
		},
	}}
}
