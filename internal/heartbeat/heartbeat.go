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

	"github.com/onemindos/onemindos/internal/mesh"
)

// Schema is the value of the "schema" field.
const Schema = "onemind.node.status/v1"

// Subject returns the NATS subject a node publishes its heartbeat on.
func Subject(nodeID string) string { return fmt.Sprintf("onemind.node.%s.status", nodeID) }

// DepartureSchema is the schema of the departure a node publishes once, on
// Subject, when it stops cleanly (#608). It rides the node's own status
// subject on purpose: on a strict hub only that node's NATS account may
// publish there (core/onemind_core/natsconf.py), so no new export or
// permission is needed and no other machine can announce it.
const DepartureSchema = "onemind.node.departure/v1"

// Departure says "this node is going away on purpose": the gateway shows it
// offline at once instead of waiting for heartbeats to stop. A later
// heartbeat brings the node back. It carries nothing else.
type Departure struct {
	Schema string `json:"schema"`
	NodeID string `json:"node_id"`
	Reason string `json:"reason"` // "shutdown"
}

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
	CPULevel       string  `json:"cpu_level"` // x86-64-v1..v4 on amd64, "" elsewhere or unknown (NMD-09, #134)
	TPM2           bool    `json:"tpm2"`
	KVM            bool    `json:"kvm"` // /dev/kvm exists: machines can run here (MACH-01)
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
	// Mesh is this machine's mesh state (contract §12.10; internal/mesh):
	// state and path, plus counts. Never an address or a peer name. Omitted
	// when the machine has no mesh client.
	Mesh *mesh.Heartbeat `json:"mesh,omitempty"`
	// Fabric is the machine's place in the fabric (contract §12.10):
	// role hub|worker|leaf and its NATS leaf link. Omitted on v0 installs
	// that never joined through the fabric.
	Fabric *Fabric `json:"fabric,omitempty"`
	// Backup is the backup agent's last result (contract 12.10); omitted
	// when the box has no backup agent configured.
	Backup *Backup `json:"backup,omitempty"`
	// Images is the image cleanup and disk budget state (NMD-08, #133;
	// internal/imagegc); omitted when the node runs no image cleaner.
	Images *Images `json:"images,omitempty"`
	// Metrics are the node's live load figures (contract 12.10 "metrics"),
	// read at each heartbeat. Optional: omitted when none can be read.
	Metrics *Metrics `json:"metrics,omitempty"`
	// Capabilities is the hardware profile (NodeCapabilities, #618; capabilities.go). onemindd
	// always sends it; it is a pointer so heartbeats from older agents stay valid without it.
	Capabilities *Capabilities `json:"capabilities,omitempty"`
}

// Fabric is the heartbeat's fabric object (contract §12.10).
type Fabric struct {
	Role          string  `json:"role"`      // hub | worker | leaf
	LeafLink      string  `json:"leaf_link"` // up | down | none
	CertExpiresAt *string `json:"cert_expires_at,omitempty"`
}

// Backup is the heartbeat's optional "backup" object (contract 12.10).
type Backup struct {
	Running    bool    `json:"running"`
	LastRunAt  *string `json:"last_run_at"`
	LastResult string  `json:"last_result"` // succeeded | failed | partial | none
}

// Images is the heartbeat's optional "images" object (NMD-08): the container
// image store, the box's disk budget, and the last cleanup. The gateway warns
// the owner (disk.budget_near) when DiskUsedPct reaches WarnPct.
type Images struct {
	Count           int     `json:"count"`
	Bytes           int64   `json:"bytes"`
	SupersededBytes int64   `json:"superseded_bytes"`
	DiskUsedPct     float64 `json:"disk_used_pct"`
	BudgetPct       float64 `json:"budget_pct"`
	WarnPct         float64 `json:"warn_pct"`
	LastCleanupAt   *string `json:"last_cleanup_at"`
	LastResult      string  `json:"last_result"` // succeeded | partial | skipped | failed | none
	LastRemoved     int     `json:"last_removed"`
	LastFreedBytes  int64   `json:"last_freed_bytes"`
}

// Metrics feeds the gateway's per-node history and threshold alerts
// (contract 12.15). CPUPct is busy time since the previous heartbeat (null
// on the first), Load1 the 1-minute load average, TempC the hottest thermal
// zone in degrees C. Each is null when this node cannot read it.
type Metrics struct {
	CPUPct *float64 `json:"cpu_pct"`
	Load1  *float64 `json:"load1"`
	TempC  *float64 `json:"temp_c"`
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
	// PreviousVersion is the version the box ran before the update it now runs, set when the health
	// gate committed that update: the version the other A/B slot still holds and can boot ("go back",
	// P-16). Empty when unknown, and cleared when a new install starts or the gate rolled one back.
	PreviousVersion string `json:"previous_version,omitempty"`
	// Policy and Window are the update policy and maintenance window in force (REL-02, #154), and
	// SettingsSource says whose they are: "image" (the read-only update.conf, BD-09 default) or
	// "owner" (approved through the gateway). Empty from an updater that predates them.
	Policy         string `json:"policy,omitempty"`
	Window         string `json:"window,omitempty"`
	SettingsSource string `json:"settings_source,omitempty"`
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

// GPU reports an NVIDIA GPU. Model is null when there is none. Count and VRAMMB
// are additive (omitted when nvidia-smi is not there to read them, and always on
// a Jetson, whose GPU shares system memory): Count is the number of cards and
// VRAMMB the memory of the smallest one, which is what a placement must trust.
type GPU struct {
	NVIDIA bool    `json:"nvidia"`
	Model  *string `json:"model"`
	Count  *int    `json:"count,omitempty"`
	VRAMMB *int    `json:"vram_mb,omitempty"`
}
