// Package heartbeat defines the node heartbeat object of the proof-of-concept
// v0 contract (sdk/contracts/poc-v0.md §2). The same JSON is published on NATS
// subject onemind.node.<node_id>.status and served at GET :7480/api/v1/node.
//
// Privacy rule (contract §2): this object never carries serial numbers, MAC
// addresses, IP addresses or user names. Add a field only if it keeps that rule.
package heartbeat

import (
	"fmt"
	"regexp"
)

// Schema is the value of the "schema" field.
const Schema = "onemind.node.status/v1"

// Subject returns the NATS subject a node publishes its heartbeat on.
func Subject(nodeID string) string { return fmt.Sprintf("onemind.node.%s.status", nodeID) }

// nodeIDRe is the node id charset the gateway accepts on ingest: one NATS
// subject token, no '.', '*', '>' or whitespace.
var nodeIDRe = regexp.MustCompile(`^[A-Za-z0-9_-]{1,64}$`)

// ValidateNodeID reports whether id can be used as node_id and as the
// <node_id> token of Subject. Derived ids (12 hex characters) always pass;
// the check matters for the ONEMIND_NODE_ID override.
func ValidateNodeID(id string) error {
	if !nodeIDRe.MatchString(id) {
		return fmt.Errorf("node id must be 1-64 characters of A-Z, a-z, 0-9, '_' or '-', got %q", id)
	}
	return nil
}

// ValidateRole reports whether role is one of the contract §1 roles.
func ValidateRole(role string) error {
	if role != "hub" && role != "node" {
		return fmt.Errorf("role must be hub or node, got %q", role)
	}
	return nil
}

// Board values (contract §2).
const (
	BoardX86EFI     = "x86_64-efi"
	BoardARM64EFI   = "arm64-efi"
	BoardRPi5       = "rpi5"
	BoardJetsonOrin = "jetson-orin"
	BoardVM         = "vm"
	BoardVMDO       = "vm-do"
	BoardUnknown    = "unknown"
)

// Secure Boot values (contract §2).
const (
	SecureBootEnabled     = "enabled"
	SecureBootDisabled    = "disabled"
	SecureBootUnsupported = "unsupported"
	SecureBootUnknown     = "unknown"
)

// Status is the heartbeat object. Field order and names follow contract §2.
type Status struct {
	Schema         string  `json:"schema"`
	NodeID         string  `json:"node_id"`
	Hostname       string  `json:"hostname"`
	Role           string  `json:"role"`
	Board          string  `json:"board"`
	Arch           string  `json:"arch"`
	OS             OS      `json:"os"`
	Kernel         string  `json:"kernel"`
	CPUModel       string  `json:"cpu_model"`
	CPUs           int     `json:"cpus"`
	MemTotalMB     int64   `json:"mem_total_mb"`
	MemAvailableMB int64   `json:"mem_available_mb"`
	DiskTotalGB    float64 `json:"disk_total_gb"`
	DiskFreeGB     float64 `json:"disk_free_gb"`
	TPM2           bool    `json:"tpm2"`
	SecureBoot     string  `json:"secure_boot"`
	K3s            K3s     `json:"k3s"`
	RAUC           RAUC    `json:"rauc"`
	GPU            GPU     `json:"gpu"`
	UptimeS        int64   `json:"uptime_s"`
	AgentVersion   string  `json:"agent_version"`
	ObservedAt     string  `json:"observed_at"`
	// Update is the OS update state (contract §10.1, brief 30 B4.2). It is
	// optional and additive: omitted when the box has no update service
	// configured, so heartbeats without it stay valid.
	Update *Update `json:"update,omitempty"`
	// Backup is the backup agent's last result (contract §12.10); omitted
	// when the box has no backup agent configured.
	Backup *Backup `json:"backup,omitempty"`
}

// Backup is the heartbeat's optional "backup" object (contract §12.10).
type Backup struct {
	Running    bool    `json:"running"`
	LastRunAt  *string `json:"last_run_at"`
	LastResult string  `json:"last_result"` // succeeded | failed | partial | none
}

// Update states (internal/update keeps the state machine).
const (
	UpdateIdle          = "idle"
	UpdateDownloading   = "downloading"
	UpdateInstalling    = "installing"
	UpdatePendingReboot = "pending_reboot"
	UpdateTrial         = "trial"
	UpdateCommitted     = "committed"
	UpdateRolledBack    = "rolled_back"
	UpdateError         = "error"
)

// Update reports the box's OS update channel and progress. AvailableVersion
// and LastCheck are null until a check found something / ran.
type Update struct {
	Channel          string  `json:"channel"`
	CurrentVersion   string  `json:"current_version"`
	AvailableVersion *string `json:"available_version"`
	State            string  `json:"state"`
	LastCheck        *string `json:"last_check"`
	LastResult       string  `json:"last_result"`
}

// OS is parsed from /etc/os-release.
type OS struct {
	ID        string `json:"id"`
	VersionID string `json:"version_id"`
	Pretty    string `json:"pretty"`
}

// K3s reports whether k3s is installed, in which role, and whether it is ready.
// Role is null when k3s is not present.
type K3s struct {
	Present bool    `json:"present"`
	Role    *string `json:"role"`
	Ready   bool    `json:"ready"`
}

// RAUC reports the A/B slot state. BootedSlot is null when RAUC is absent.
// Slots is always a JSON array (never null) so clients can iterate it.
type RAUC struct {
	Present    bool    `json:"present"`
	BootedSlot *string `json:"booted_slot"`
	Slots      []Slot  `json:"slots"`
}

// Slot is one RAUC slot. It deliberately omits the device path: on many
// systems that is a /dev/disk/by-id/... name that embeds the disk serial.
type Slot struct {
	Name          string `json:"name"`
	Class         string `json:"class,omitempty"`
	Bootname      string `json:"bootname,omitempty"`
	State         string `json:"state,omitempty"`
	BootStatus    string `json:"boot_status,omitempty"`
	BundleVersion string `json:"bundle_version,omitempty"`
}

// GPU reports an NVIDIA GPU. Model is null when there is none.
type GPU struct {
	NVIDIA bool    `json:"nvidia"`
	Model  *string `json:"model"`
}
