// SPDX-License-Identifier: Apache-2.0

package onemind

import "github.com/onemindos/onemindos/sdk/go/internal/gen"

// The API types, generated from sdk/openapi/onemind-v1.json (internal/gen). Fields an older SDK
// does not know are kept in AdditionalProperties, and open enums (State, Status, Type) are plain
// strings, so a newer gateway never breaks this SDK (SDK.md §5).
type (
	Instance     = gen.Instance
	About        = gen.About
	AboutNode    = gen.AboutNode
	Node         = gen.Node
	CatalogApp   = gen.CatalogApp
	AppPlacement = gen.AppPlacement
	SystemApp    = gen.SystemAppRow
	Action       = gen.Action
	PrincipalRef = gen.PrincipalRef
	AuditRecord  = gen.AuditRecord
	AuditVerify  = gen.AuditVerify
	AuditHead    = gen.AuditHead
	StatusView   = gen.StatusView
	SourceStatus = gen.SourceStatus
	Usage        = gen.Usage
	ServicesView = gen.ServicesView
	ServiceCard  = gen.ServiceCard

	KeyboardView    = gen.KeyboardView
	KeyboardLayout  = gen.KeyboardLayout
	KeyboardVariant = gen.KeyboardVariant
	KeyboardSetting = gen.KeyboardSetting
	FirewallView    = gen.FirewallView
	FirewallRule    = gen.FirewallRule
	AllowRule       = gen.AllowRule
	AllowRequest    = gen.AllowRequest
)

// Action types the gateway accepts today (contract §3; §12.5 adds more).
const (
	ActionAppInstall = "app.install"
	ActionAppRemove  = "app.remove"
	// Built-in apps are switched off and on, never removed (appstore/system.py).
	ActionAppDisable = "app.disable"
	ActionAppEnable  = "app.enable"
)

// Terminal reports whether an action state is final.
func Terminal(state string) bool {
	switch state {
	case "succeeded", "failed", "cancelled", "expired", "outcome_unknown":
		return true
	}
	return false
}
