// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"path/filepath"
	"time"

	"github.com/nats-io/nats.go"
	"github.com/nats-io/nats.go/jetstream"

	"github.com/onemindos/onemindos/internal/fabric"
	"github.com/onemindos/onemindos/internal/leaf"
)

// `onemind fabric outbox` is the store-and-forward queue of a leaf-only node (CORE-FABRIC-5, #170):
// messages wait in the local leaf's JetStream outbox until the hub collects them. It talks to the
// leaf on loopback, and signs in with its own nkey (the leaf has no passwordless user, G1).
const outboxUsage = "usage: onemind fabric outbox init [--max-size MB] | status [--json] | send SUBJECT TEXT [--id ID]"

func fabricOutbox(args []string, out io.Writer) error {
	if len(args) == 0 {
		return errors.New(outboxUsage)
	}
	cmd, args := args[0], args[1:]
	fs := flag.NewFlagSet("fabric outbox "+cmd, flag.ContinueOnError)
	url := fs.String("url", "nats://"+leaf.DefaultListen, "the local leaf")
	seed := fs.String("nkey", filepath.Join(fabric.LocalKeysDir, leaf.ProgramCLI+".nk"), "this tool's nkey seed for the local leaf (written by `onemind fabric join`; run as root)")
	maxMB := fs.Int("max-size", leaf.DefaultOutboxMaxBytes>>20, "init: outbox size limit in MB")
	asJSON := fs.Bool("json", false, "status: print JSON")
	id := fs.String("id", "", "send: message id (default: a new random one); reuse it to retry safely")

	// Flags may come after the positional words (send SUBJECT TEXT --id X).
	var pos []string
	for len(args) > 0 {
		if err := fs.Parse(args); err != nil {
			return err
		}
		if fs.NArg() == 0 {
			break
		}
		pos = append(pos, fs.Arg(0))
		args = fs.Args()[1:]
	}

	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	sign, err := leaf.ClientOptions(leaf.ProgramCLI, *seed)
	if err != nil {
		return fmt.Errorf("%w (the leaf has no passwordless user: run as root on a joined node, or pass --nkey)", err)
	}
	nc, err := nats.Connect(*url, append(sign, nats.Timeout(5*time.Second), nats.Name("onemind-cli"))...)
	if err != nil {
		return fmt.Errorf("the local leaf is not reachable at %s (is this a joined node?): %w", *url, err)
	}
	defer nc.Close()
	js, err := jetstream.New(nc)
	if err != nil {
		return err
	}

	switch cmd {
	case "init":
		if *maxMB < 1 {
			return errors.New("--max-size must be at least 1 MB")
		}
		if err := leaf.EnsureOutbox(ctx, js, leaf.OutboxConfig{MaxBytes: int64(*maxMB) << 20}); err != nil {
			return fmt.Errorf("create outbox: %w", err)
		}
		fmt.Fprintf(out, "Outbox ready (limit %d MB).\n", *maxMB)
	case "status":
		st, err := leaf.Status(ctx, js)
		if err != nil {
			return fmt.Errorf("outbox: %w (run `onemind fabric outbox init`)", err)
		}
		if *asJSON {
			return printJSON(out, st)
		}
		fmt.Fprintf(out, "Waiting for the hub: %d messages, %d of %d bytes\n", st.Messages, st.Bytes, st.MaxBytes)
	case "send":
		if len(pos) != 2 {
			return errors.New(outboxUsage)
		}
		mid := *id
		if mid == "" {
			b := make([]byte, 12)
			if _, err := rand.Read(b); err != nil {
				return err
			}
			mid = hex.EncodeToString(b)
		}
		dup, err := leaf.Enqueue(ctx, js, pos[0], []byte(pos[1]), mid)
		if err != nil {
			return err
		}
		if dup {
			fmt.Fprintf(out, "Already queued (id %s), nothing added.\n", mid)
		} else {
			fmt.Fprintf(out, "Queued (id %s).\n", mid)
		}
	default:
		return errors.New(outboxUsage)
	}
	return nil
}
