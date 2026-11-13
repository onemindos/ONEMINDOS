// SPDX-License-Identifier: Apache-2.0

package onemind

import "github.com/onemindos/onemindos/sdk/go/internal/gen"

// The API types, generated from sdk/openapi/onemind-v1.json (internal/gen). Fields an older SDK
// does not know are kept in AdditionalProperties, and open enums (State, Status, Type) are plain
// strings, so a newer gateway never breaks this SDK (SDK.md §5).
type (
	Instance     = gen.Instance
	Node         = gen.Node
	CatalogApp   = gen.CatalogApp
	Action       = gen.Action
	PrincipalRef = gen.PrincipalRef
	AuditRecord  = gen.AuditRecord
	AuditVerify  = gen.AuditVerify
	AuditHead    = gen.AuditHead
)

// Action types the gateway accepts today (contract §3; §12.5 adds more).
const (
	ActionAppInstall = "app.install"
	ActionAppRemove  = "app.remove"
)

// Terminal reports whether an action state is final.
func Terminal(state string) bool {
	switch state {
	case "succeeded", "failed", "cancelled", "expired", "outcome_unknown":
		return true
	}
	return false
}
