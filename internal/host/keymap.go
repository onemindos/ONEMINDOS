// SPDX-License-Identifier: Apache-2.0

package host

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/onemindos/onemindos/internal/keymap"
)

// KeymapSchema names GET /v1/keyboard's shape.
const KeymapSchema = "onemind.keyboard/v1"

// The units that read the keyboard file. The console unit loads it into the kernel (tty1-tty6, so the tty2 login
// too); the kiosk unit starts the box's screen with it (onemind_kiosk.py). Both are in the image's services
// registry as restartable, and the host restarts them through the same Units it uses for service-restart.
const (
	ConsoleUnit = "onemind-console-keyboard.service"
	KioskUnit   = "onemind-kiosk.service"
)

// KeymapView is GET /v1/keyboard: what is picked now and everything the image offers.
type KeymapView struct {
	Schema  string          `json:"schema"`
	Current keymap.Setting  `json:"current"`
	Seeded  bool            `json:"seeded"` // nothing chosen yet: the box runs the US seed
	Layouts []keymap.Layout `json:"layouts"`
	At      time.Time       `json:"at"`
}

// KeymapStore is the production Keymap: the keyboard file on /data and the two units that read it.
type KeymapStore struct {
	Store keymap.Store
	Units Units
	Now   func() time.Time
}

// Unavailable is empty when the image ships its list of layouts.
func (k *KeymapStore) Unavailable() string {
	if _, err := k.Store.Layouts(); err != nil {
		return err.Error()
	}
	return ""
}

// View reads the current choice and the list of layouts.
func (k *KeymapStore) View() (KeymapView, error) {
	layouts, err := k.Store.Layouts()
	if err != nil {
		return KeymapView{}, err
	}
	cur, seeded, err := k.Store.Current()
	if err != nil {
		return KeymapView{}, err
	}
	now := time.Now
	if k.Now != nil {
		now = k.Now
	}
	return KeymapView{Schema: KeymapSchema, Current: cur, Seeded: seeded, Layouts: layouts, At: now().UTC()}, nil
}

// Check delegates to the image's list.
func (k *KeymapStore) Check(layout, variant string) error { return k.Store.Check(layout, variant) }

// Set writes the layout, restarts the console unit (it loads the file with ckbcomp and loadkeys) and then the kiosk
// unit (its condition skips it when kiosk mode is off). If the console cannot load the layout, the previous file is
// put back and loaded again, and the error says so. A kiosk restart that fails after the console loaded is not an
// error of the choice: the layout is saved and the next kiosk start uses it, so it is reported in the message only.
func (k *KeymapStore) Set(ctx context.Context, layout, variant string) error {
	if err := k.Store.Check(layout, variant); err != nil {
		return err
	}
	prev, had, err := k.Store.Write(layout, variant)
	if err != nil {
		return fmt.Errorf("writing the layout to /data: %w", err)
	}
	if err := k.Units.Restart(ctx, ConsoleUnit); err != nil {
		undo := k.Store.Restore(prev, had)
		if undo == nil {
			_ = k.Units.Restart(ctx, ConsoleUnit) // load the old layout again; best effort, the boot does it too
			return fmt.Errorf("the console could not load %s, so the previous layout was kept: %w", keymap.Label(layout, variant), err)
		}
		return errors.Join(fmt.Errorf("the console could not load %s: %w", keymap.Label(layout, variant), err),
			fmt.Errorf("and the previous layout could not be put back: %w", undo))
	}
	if err := k.Units.Restart(ctx, KioskUnit); err != nil {
		return nil //nolint:nilerr // saved and loaded on the console; the kiosk takes it at its next start
	}
	return nil
}
