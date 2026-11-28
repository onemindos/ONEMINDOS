// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"fmt"
	"io"
	"os"

	"github.com/onemindos/onemindos/internal/plugin/artifact"
	"github.com/spf13/cobra"
)

func pluginSignCommand(a *App) *cobra.Command {
	var digest, keyPath, output string
	command := &cobra.Command{Use: "sign <layout>", Short: "Sign a pinned local artifact with an existing private key", Args: cobra.ExactArgs(1), RunE: func(cmd *cobra.Command, args []string) error {
		key, err := privateSigningInput(keyPath)
		if err != nil {
			return exitWith(ExitVerifyFailed, "sign_failed", err.Error())
		}
		defer clear(key)
		sig, keyID, err := artifact.Sign(args[0], digest, key)
		if err != nil {
			return exitWith(ExitVerifyFailed, "sign_failed", err.Error())
		}
		f, err := os.OpenFile(output, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
		if err != nil {
			return exitWith(ExitVerifyFailed, "sign_failed", "signature output must be a new writable file")
		}
		_, err = f.Write(sig)
		closeErr := f.Close()
		if err != nil || closeErr != nil {
			_ = os.Remove(output)
			return exitWith(ExitVerifyFailed, "sign_failed", "could not write signature")
		}
		if a.G.JSON {
			return printJSON(a.Stdout, map[string]any{"digest": digest, "signature": output, "candidate_key_id": keyID, "verified": false})
		}
		fmt.Fprintf(a.Stdout, "Signed %s\nCandidate key: %s\nSignature: %s\nOwner enrollment, scans and install approval remain required.\n", digest, keyID, output)
		return nil
	}}
	command.Flags().StringVar(&digest, "digest", "", "immutable sha256 artifact digest")
	command.Flags().StringVar(&keyPath, "key", "", "existing private PKCS8 PEM file, accessible only to its owner")
	command.Flags().StringVar(&output, "output", "", "new detached base64 signature file")
	for _, flag := range []string{"digest", "key", "output"} {
		_ = command.MarkFlagRequired(flag)
	}
	return command
}

func privateSigningInput(path string) ([]byte, error) {
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("private key must be a regular file accessible only to its owner")
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("could not open private key")
	}
	defer f.Close()
	opened, err := f.Stat()
	if err != nil || !os.SameFile(info, opened) || opened.Mode().Perm()&0077 != 0 {
		return nil, fmt.Errorf("private key file changed")
	}
	data, err := io.ReadAll(io.LimitReader(f, (16<<10)+1))
	if err != nil || len(data) > 16<<10 {
		clear(data)
		return nil, fmt.Errorf("private key cannot be read or exceeds 16 KiB")
	}
	return data, nil
}
