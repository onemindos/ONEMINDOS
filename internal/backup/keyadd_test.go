// SPDX-License-Identifier: Apache-2.0

package backup

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// An emergency kit issued before a destination existed is attached to the new
// destination only (design 25a): target_ids limits the add, unknown ids refuse.
func TestAddKeyOnlyNamedTargets(t *testing.T) {
	f := newFixture(t)
	key := strings.Repeat("ABCD", 13)
	got, err := f.agent.AddKey(context.Background(), key, "peer")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].TargetID != "peer" || !got[0].OK {
		t.Fatalf("only peer must get the key: %+v", got)
	}
	all, err := f.agent.AddKey(context.Background(), key)
	if err != nil || len(all) != 2 {
		t.Fatalf("no filter means every destination: %+v %v", all, err)
	}
	_, err = f.agent.AddKey(context.Background(), key, "peer", "gone")
	var bad badParams
	if !errors.As(err, &bad) {
		t.Fatalf("an unknown destination must be refused as bad params, got %v", err)
	}
}
