// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"os"
	"regexp"

	"github.com/spf13/cobra"
)

func copyCertify(a *App) *cobra.Command {
	return &cobra.Command{
		Use:   "certify BOX_ID ROOT_PRIVATE_PEM EXPORT_PUBLIC_PEM",
		Short: "Certify a box export key offline using the owner's fabric root",
		Args:  cobra.ExactArgs(3),
		RunE: func(cmd *cobra.Command, args []string) error {
			box := args[0]
			if !regexp.MustCompile("^[A-Za-z0-9._:-]{1,80}$").MatchString(box) || box == "." || box == ".." {
				return usageErr(cmd, "invalid source box ID")
			}
			rootDER, err := copyPEM(args[1], "PRIVATE KEY")
			if err != nil {
				return err
			}
			key, err := x509.ParsePKCS8PrivateKey(rootDER)
			root, ok := key.(ed25519.PrivateKey)
			if err != nil || !ok {
				return usageErr(cmd, "the fabric root must be an Ed25519 PKCS#8 key")
			}
			exportDER, err := copyPEM(args[2], "PUBLIC KEY")
			if err != nil {
				return err
			}
			key, err = x509.ParsePKIXPublicKey(exportDER)
			export, ok := key.(ed25519.PublicKey)
			rootPub := root.Public().(ed25519.PublicKey)
			if err != nil || !ok || rootPub.Equal(export) {
				return usageErr(cmd, "use a separate Ed25519 export public key")
			}
			delegation := map[string]any{"box_id": box, "public_key": []byte(export), "purpose": "export"}
			body, err := json.Marshal(delegation)
			if err != nil {
				return err
			}
			sig := ed25519.Sign(root, append([]byte("onemind.io/sovereign-copy/v1/delegate/"), body...))
			// The certificate travels to the box. The root private key stays on this machine.
			cert, err := json.Marshal(map[string]any{"root": []byte(rootPub),
				"certificate": map[string]any{"body": delegation, "signature": sig}})
			if err != nil {
				return err
			}
			if _, err := a.Stdout.Write(cert); err != nil {
				return err
			}
			_, err = fmt.Fprintf(a.Stderr, "Fabric root fingerprint (keep with the recovery kit): %x\n", sha256.Sum256(rootPub))
			return err
		},
	}
}

func copyPEM(name, kind string) ([]byte, error) {
	raw, err := os.ReadFile(name)
	if err != nil {
		return nil, err
	}
	block, rest := pem.Decode(raw)
	if block == nil || block.Type != kind || len(rest) != 0 {
		return nil, fmt.Errorf("expected one PEM %s", kind)
	}
	return block.Bytes, nil
}
