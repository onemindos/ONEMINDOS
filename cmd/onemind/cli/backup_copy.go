// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"encoding/json"
	"io"
	"net/http"
	"strings"

	"github.com/spf13/cobra"
)

func backupCopies(a *App) *cobra.Command {
	root := &cobra.Command{Use: "copy", Short: "Publish or discover independently recoverable box copies"}
	var reason string
	start := &cobra.Command{
		Use:   "start DESTINATION",
		Short: "Request owner approval for a copy (reads the recovery key from stdin)",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			key, err := copyRecoveryKey(cmd, a.Stdin)
			if err != nil {
				return err
			}
			return a.backupRequest("sovereign copy", "/v1/backups/copies",
				map[string]any{"destination_id": args[0], "recovery_key": key}, reason, false)
		},
	}
	start.Flags().StringVar(&reason, "reason", "", "why, shown to the owner")
	discover := &cobra.Command{
		Use:   "discover DESTINATION BOX_ID ROOT_FINGERPRINT",
		Short: "Find and verify the newest recoverable copy on a fresh box (reads the recovery key from stdin)",
		Args:  cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			key, err := copyRecoveryKey(cmd, a.Stdin)
			if err != nil {
				return err
			}
			v, err := a.gwDo(http.MethodPost, "/v1/onboarding/restore/copy", map[string]any{
				"destination_id": args[0], "box_id": args[1], "root_fingerprint": args[2], "recovery_key": key,
			})
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, v)
			}
			point := obj(obj(v)["candidate"])
			if len(point) == 0 {
				_, err = io.WriteString(a.Stdout, "No verified copy found.\n")
				return err
			}
			return kv(a.Stdout, [][2]string{
				{"copy", str(point["copy_id"])}, {"created", str(point["created_at"])}, {"backup", str(point["backed_up_at"])},
			})
		},
	}

	var nasPrimary, s3Primary bool
	nas := &cobra.Command{
		Use:   "add-nas LABEL MOUNT_ID",
		Short: "Request a sovereign NAS destination mounted at /run/onemind/backup/MOUNT_ID",
		Args:  cobra.ExactArgs(2),
		RunE: func(_ *cobra.Command, args []string) error {
			return a.backupRequest("sovereign NAS destination", "/v1/backups/destinations", map[string]any{
				"kind": "usb", "label": args[0], "primary": nasPrimary,
				"config": map[string]any{"usb_uuid": args[1], "sovereign": true},
			}, "", false)
		},
	}
	nas.Flags().BoolVar(&nasPrimary, "primary", false, "use as the primary backup destination")
	var prefix, region string
	s3 := &cobra.Command{
		Use:   "add-s3 LABEL ENDPOINT BUCKET",
		Short: "Request a sovereign S3 destination (reads access_key and secret_key as JSON from stdin)",
		Args:  cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			var creds map[string]string
			raw, err := io.ReadAll(io.LimitReader(a.Stdin, 8193))
			if err != nil || len(raw) > 8192 || json.Unmarshal(raw, &creds) != nil ||
				len(creds) != 2 || creds["access_key"] == "" || creds["secret_key"] == "" {
				return usageErr(cmd, "stdin must contain JSON with access_key and secret_key")
			}
			return a.backupRequest("sovereign S3 destination", "/v1/backups/destinations", map[string]any{
				"kind": "s3", "label": args[0], "primary": s3Primary, "credentials": creds,
				"config": map[string]any{"endpoint": args[1], "bucket": args[2], "prefix": prefix, "region": region, "sovereign": true},
			}, "", false)
		},
	}
	s3.Flags().BoolVar(&s3Primary, "primary", false, "use as the primary backup destination")
	s3.Flags().StringVar(&prefix, "prefix", "", "object prefix")
	s3.Flags().StringVar(&region, "region", "", "S3 region")
	root.AddCommand(start, discover, nas, s3, copyCertify(a))
	return root
}

func copyRecoveryKey(cmd *cobra.Command, in io.Reader) (string, error) {
	raw, err := io.ReadAll(io.LimitReader(in, 257))
	key := strings.TrimSpace(string(raw))
	if err != nil || len(raw) > 256 || len(key) != 64 {
		return "", usageErr(cmd, "stdin must contain the printed recovery key")
	}
	return key, nil
}
