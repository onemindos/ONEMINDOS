// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"

	onemind "github.com/onemindos/onemindos/sdk/go"
	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

var configFiles = []string{"settings.yaml", "apps.yaml", "users.yaml", "schedules.yaml"}

func configCommands(a *App) []*cobra.Command {
	group := &cobra.Command{Use: "config", Short: "Export, compare or request configuration for private Git"}
	add := func(verb, short string, run func(context.Context, string) error) {
		var dir string
		cmd := &cobra.Command{
			Use:   verb + " --dir <path>",
			Short: short,
			Args:  cobra.NoArgs,
			RunE: func(cmd *cobra.Command, _ []string) error {
				if strings.TrimSpace(dir) == "" {
					return usageErr(cmd, "--dir is required")
				}
				return run(cmd.Context(), dir)
			},
		}
		cmd.Flags().StringVar(&dir, "dir", "", "directory for settings.yaml, apps.yaml, users.yaml and schedules.yaml")
		group.AddCommand(cmd)
	}
	add("export", "Write the selected box's configuration as YAML", a.exportConfig)
	add("diff", "Show a dry-run comparison with the selected box", func(ctx context.Context, dir string) error {
		return a.compareConfig(ctx, dir, false)
	})
	add("apply", "Request owner approval for a configuration change", func(ctx context.Context, dir string) error {
		return a.compareConfig(ctx, dir, true)
	})
	return []*cobra.Command{group}
}

func (a *App) exportConfig(ctx context.Context, dir string) error {
	client, _, err := a.client()
	if err != nil {
		return err
	}
	var export onemind.ConfigExportView
	if err := client.Do(ctx, http.MethodGet, "/v1/config/export", nil, &export); err != nil {
		return err
	}
	files := export.Files
	legacy := files == nil
	if legacy {
		files = map[string]string{"settings.yaml": export.Yaml}
	}
	if _, ok := files["settings.yaml"]; !ok {
		return fmt.Errorf("gateway export is missing settings.yaml")
	}
	// Check the whole response before writing anything or removing stale managed files.
	for name, data := range files {
		if err := checkConfigVersion(name, data); err != nil {
			return err
		}
	}
	if err := os.MkdirAll(dir, 0o700); err != nil {
		return err
	}
	var paths, stale []string
	for _, name := range configFiles {
		path := filepath.Join(dir, name)
		_, included := files[name]
		if legacy && !included {
			continue
		}
		exists, err := configRegularFile(path)
		if err != nil {
			return err
		}
		if included {
			paths = append(paths, path)
		} else if exists {
			stale = append(stale, path)
		}
	}
	// Stage every file before replacing any existing one, so a failed temp write
	// leaves the previous export intact. Each replacement is an atomic rename.
	staged := make([]string, 0, len(paths))
	for _, path := range paths {
		tmp, err := stageFile0600(path, []byte(files[filepath.Base(path)]))
		if err != nil {
			return err
		}
		defer os.Remove(tmp)
		staged = append(staged, tmp)
	}
	for i, path := range paths {
		if err := os.Rename(staged[i], path); err != nil {
			return err
		}
	}
	for _, path := range stale {
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	if a.G.JSON {
		return printJSON(a.Stdout, map[string]any{"path": paths[0], "paths": paths})
	}
	for _, path := range paths {
		if _, err := fmt.Fprintln(a.Stdout, sanitize(path)); err != nil {
			return err
		}
	}
	return nil
}

func configRegularFile(path string) (bool, error) {
	info, err := os.Lstat(path)
	if os.IsNotExist(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	if !info.Mode().IsRegular() {
		return false, fmt.Errorf("%s must be a regular file", path)
	}
	return true, nil
}

func checkConfigVersion(name, data string) error {
	var expected string
	for _, file := range configFiles {
		if name == file {
			expected = "onemind.io/config-as-code/" + strings.TrimSuffix(file, ".yaml") + "/v1"
			break
		}
	}
	if expected == "" {
		return fmt.Errorf("unsupported config file %q", name)
	}
	var doc map[string]yaml.Node
	dec := yaml.NewDecoder(strings.NewReader(data))
	if err := dec.Decode(&doc); err != nil {
		return fmt.Errorf("%s must contain a YAML mapping", name)
	}
	if err := dec.Decode(new(yaml.Node)); err != io.EOF {
		return fmt.Errorf("%s must contain exactly one YAML document", name)
	}
	version := doc["schema"]
	if version.Kind != yaml.ScalarNode || version.Tag != "!!str" || version.Value != expected {
		return fmt.Errorf("%s requires schema %s", name, expected)
	}
	return nil
}

func readConfigDir(dir string) (map[string]string, error) {
	files := make(map[string]string, len(configFiles))
	for _, name := range configFiles {
		path := filepath.Join(dir, name)
		exists, err := configRegularFile(path)
		if err != nil {
			return nil, err
		}
		if !exists {
			continue
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return nil, err
		}
		if err := checkConfigVersion(name, string(data)); err != nil {
			return nil, err
		}
		files[name] = string(data)
	}
	if len(files) == 0 {
		return nil, fmt.Errorf("no OneMind configuration files in %s", dir)
	}
	return files, nil
}

func (a *App) compareConfig(ctx context.Context, dir string, apply bool) error {
	files, err := readConfigDir(dir)
	if err != nil {
		return err
	}
	client, _, err := a.client()
	if err != nil {
		return err
	}
	body := onemind.ConfigDiffBody{Files: files}
	var diff onemind.ConfigDiffView
	if err := client.Do(ctx, http.MethodPost, "/v1/config/diff", body, &diff); err != nil {
		return explainGateway(err)
	}
	if diff.Revision == "" || diff.Changes == nil {
		return fmt.Errorf("gateway returned an incomplete config diff")
	}
	if !apply || len(diff.Changes) == 0 || len(diff.Blockers) > 0 {
		var printErr error
		if a.G.JSON {
			printErr = printJSON(a.Stdout, diff)
		} else {
			printErr = printConfigDiff(a.Stdout, diff)
		}
		if printErr != nil {
			return printErr
		}
		if apply && len(diff.Blockers) > 0 {
			return exitWith(ExitRefused, "refused", "resolve the blocked changes before requesting config apply")
		}
		return nil
	}
	if !a.G.JSON && !a.G.Quiet {
		if err := printConfigDiff(a.Stdout, diff); err != nil {
			return err
		}
	}
	var action onemind.Action
	request := onemind.ConfigApplyBody{Files: files, Revision: diff.Revision}
	if err := client.DoIdempotent(ctx, http.MethodPost, "/v1/config/apply", freshKey(), request, &action); err != nil {
		return explainGateway(err)
	}
	if action.Id == "" || action.Type != "config.apply" || action.State == "" {
		return fmt.Errorf("gateway did not return a config apply request")
	}
	if a.G.JSON {
		return printJSON(a.Stdout, action)
	}
	if a.G.Quiet {
		_, err := fmt.Fprintln(a.Stdout, sanitize(action.Id))
		return err
	}
	if action.State == "requested" || action.State == "awaiting_approval" {
		_, err = fmt.Fprintf(a.Stdout, "Requested config apply (%s). Waiting for the owner in Approvals.\n", sanitize(action.Id))
	} else {
		_, err = fmt.Fprintf(a.Stdout, "Config apply (%s) is %s.\n", sanitize(action.Id), sanitize(action.State))
	}
	return err
}

func printConfigDiff(out io.Writer, diff onemind.ConfigDiffView) error {
	if len(diff.Changes) == 0 {
		if _, err := fmt.Fprintln(out, "No config changes."); err != nil {
			return err
		}
	}
	for _, change := range diff.Changes {
		name := sanitize(change.File)
		before := strings.ReplaceAll(strings.TrimSuffix(sanitize(change.Before), "\n"), "\n", "\n- ")
		after := strings.ReplaceAll(strings.TrimSuffix(sanitize(change.After), "\n"), "\n", "\n+ ")
		if _, err := fmt.Fprintf(out, "--- %s (live)\n+++ %s (proposed)\n- %s\n+ %s\n", name, name, before, after); err != nil {
			return err
		}
	}
	for _, blocker := range diff.Blockers {
		if _, err := fmt.Fprintf(out, "Apply blocked. %s\n", sanitize(blocker)); err != nil {
			return err
		}
	}
	return nil
}
