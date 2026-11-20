// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/spf13/cobra"
)

func pluginInspectCommand(a *App) *cobra.Command {
	var digest, keyPath, signaturePath string
	command := &cobra.Command{Use: "inspect <layout>", Short: "Inspect pinned local plugin content (not publisher trust)", Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		if cmd.Flags().Changed("key") != cmd.Flags().Changed("signature") || (cmd.Flags().Changed("key") && (keyPath == "" || signaturePath == "")) {
			return exitWith(ExitUsage, "signature_options", "--key and --signature must be supplied together")
		}
		bundle, err := artifact.Open(args[0], digest)
		if err != nil {
			return exitWith(ExitVerifyFailed, "artifact_invalid", err.Error())
		}
		defer bundle.Close()
		keyID := ""
		if keyPath != "" {
			key, err := signatureInput(keyPath)
			if err != nil {
				return exitWith(ExitVerifyFailed, "signature_invalid", err.Error())
			}
			sig, err := signatureInput(signaturePath)
			if err != nil {
				return exitWith(ExitVerifyFailed, "signature_invalid", err.Error())
			}
			keyID, err = artifact.CheckSignature(args[0], digest, key, sig)
			if err != nil {
				return exitWith(ExitVerifyFailed, "signature_invalid", err.Error())
			}
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"id": bundle.ID, "version": bundle.Version, "digest": bundle.Digest, "integrity": true, "verified": false, "signature_valid": keyID != "", "candidate_key_id": keyID})
		}
		fmt.Fprintf(a.Stdout, "%s %s\n%s\nContent integrity checked; publisher trust, scans and approval remain required.\n", bundle.ID, bundle.Version, bundle.Digest)
		if keyID != "" {
			fmt.Fprintf(a.Stdout, "Signature valid for candidate key %s; enrollment/trust is not established.\n", keyID)
		}
		return nil
	}}
	command.Flags().StringVar(&digest, "digest", "", "exact immutable sha256 artifact digest (required)")
	_ = command.MarkFlagRequired("digest")
	command.Flags().StringVar(&keyPath, "key", "", "candidate SPKI public key; checks a detached signature, not owner enrollment")
	command.Flags().StringVar(&signaturePath, "signature", "", "base64 detached signature of the OCI artifact manifest")
	return command
}

func signatureInput(path string) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil {
		return nil, err
	}
	if !info.Mode().IsRegular() {
		return nil, fmt.Errorf("signature inputs must be regular files")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	data, err := io.ReadAll(io.LimitReader(f, (16<<10)+1))
	if len(data) > 16<<10 {
		return nil, fmt.Errorf("signature input exceeds 16 KiB")
	}
	return data, err
}
