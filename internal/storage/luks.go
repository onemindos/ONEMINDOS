// SPDX-License-Identifier: Apache-2.0

package storage

// LUKS2 for the data set (H-11, CORE-SEC-5, docs/umbrel2/storage.md §4.3,
// §4.10). Every member carries the same keyslots, so one recovery key and
// one TPM2 policy open the whole set:
//
//	keyslot  what                          where it comes from
//	recovery the owner's recovery key       InitData, shown once, never stored
//	set key  64 random bytes                InitData; kept inside the unlocked
//	                                        set at SetKeyPath so onemindd can
//	                                        open a member it just prepared
//	tpm2     systemd-tpm2 token (PCR 7,     InitData when a TPM2 is present
//	         + signed PCR 11 policy if the
//	         image ships its public key)
//
// A new member (mirror.create/add/replace) gets a byte copy of an existing
// member's LUKS2 header (CloneHeaderSteps): the same volume key and the same
// keyslots, then a fresh UUID. That is the only way to give it the recovery
// keyslot without asking the owner for the recovery key, and it needs no
// key at all: the header holds only wrapped keys. The volume key is shared
// across members as a result (see docs/leap/core/STORAGE-ACTIONS.md §5 for
// the trade-off and the alternative the founder may pick instead).
//
// Each member also carries a OneMind LUKS2 token (TokenID) naming the set and
// a generation that grows on every membership change, so the boot assembly
// (os patch, STORAGE-ACT-os.patch.md) unlocks exactly the current members and
// treats an older disk as stale.

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

const (
	// SetKeyPath is the set key, relative to the data mount (inside @).
	SetKeyPath = "onemind/storage/keys/set.key"
	// TokenID is the LUKS2 token slot OneMind uses (0..31; systemd takes the
	// lowest free ones, so the top end avoids them).
	TokenID = 30
	// TokenType names the OneMind token in the LUKS2 header.
	TokenType = "onemind-storage"
	// RunDir holds short-lived files: the cloned header while it is copied,
	// the pending recovery key until the owner has seen it. tmpfs, never disk.
	RunDir = "/run/onemind/storage"
	// RecoveryKeyFile is the one-time recovery key waiting to be shown.
	RecoveryKeyFile = RunDir + "/recovery-key"
	// PBKDFMemoryKiB pins argon2id memory for the recovery keyslot so the
	// smallest supported board (4 GiB) can unlock (lab finding 4).
	PBKDFMemoryKiB = "262144"
)

// Token is the OneMind LUKS2 token.
type Token struct {
	Type       string `json:"type"`
	Keyslots   []int  `json:"keyslots"`
	SetUUID    string `json:"set_uuid"`
	MemberUUID string `json:"member_uuid"`
	// PartUUID is the member's own GPT partition id. A header copied onto
	// another partition carries the wrong one, so the boot assembly never
	// opens a half-prepared disk (one cut between the header copy and its
	// own token) as a member.
	PartUUID   string `json:"partuuid"`
	Generation int    `json:"generation"`
}

// DerivedUUID is a stable UUID-shaped id from a seed (the set), a disk id and
// a purpose ("part", "luks"). Plans must be reproducible, so the same request
// on the same disks gives the same plan_sha256 at request, approval and run.
func DerivedUUID(seed, diskID, purpose string) string {
	h := sha256.Sum256([]byte("onemind-storage\x00" + seed + "\x00" + diskID + "\x00" + purpose))
	b := h[:16]
	b[6] = b[6]&0x0f | 0x40 // version 4 layout (name-derived, but tools only check the shape)
	b[8] = b[8]&0x3f | 0x80 // RFC 4122 variant
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// CloneHeaderSteps copy the LUKS2 header of an existing member (src, a
// partition) onto the new member's partition and give it its own UUID. The
// backup file lives in RunDir (tmpfs) for the seconds the copy takes.
func CloneHeaderSteps(src, part, luksUUID string) []Step {
	hdr := RunDir + "/header-" + luksUUID[:8] + ".img"
	return []Step{
		{ID: "rundir", Phase: PhasePrepare, Cmd: []string{"mkdir", "-p", "-m", "0700", RunDir}, Why: "tmpfs folder for the header copy"},
		{ID: "luks-header-drop", Phase: PhasePrepare, Cmd: []string{"rm", "-f", hdr}, Why: "no leftover copy from an interrupted run"},
		{ID: "luks-header-backup", Phase: PhasePrepare, Cmd: []string{"cryptsetup", "luksHeaderBackup", src, "--header-backup-file", hdr},
			Why: "copy the LUKS2 header of an existing member: the same keyslots (recovery key, TPM2, set key) will open the new one"},
		{ID: "luks-header-restore", Phase: PhasePrepare, Cmd: []string{"cryptsetup", "luksHeaderRestore", "--batch-mode", part, "--header-backup-file", hdr},
			Why: "write that header onto the new member", Destructive: true},
		{ID: "luks-header-drop", Phase: PhasePrepare, Cmd: []string{"rm", "-f", hdr}, Why: "remove the copy"},
		{ID: "luks-uuid", Phase: PhasePrepare, Cmd: []string{"cryptsetup", "luksUUID", "--batch-mode", "--uuid", luksUUID, part},
			Why: "its own LUKS UUID, so the two members never look like one device"},
	}
}

// TokenSteps write OneMind token generation gen on every present member
// except devid skip (-1: none), and on the new member nm when it is set. The
// boot assembly unlocks the members of the newest generation only, so a
// member leaves the set (for the boot) when the others move past it.
func TokenSteps(m *Mirror, nm newMember, skip, gen int, phase string) []Step {
	var steps []Step
	if nm.Part != "" {
		id := "token"
		if phase != PhasePrepare {
			id = "token-member"
		}
		steps = append(steps, tokenStep(id, phase, m.UUID, nm.LUKSUUID, nm.PartUUID, nm.Part, gen))
	}
	for _, mem := range m.Members {
		if mem.Missing || mem.DevID == skip || mem.Backing == "" {
			continue
		}
		p := phase
		if p == PhasePrepare {
			p = PhaseJoin
		}
		steps = append(steps, tokenStep("token-member", p, m.UUID, mem.LUKSUUID, mem.PartUUID, mem.Backing, gen))
	}
	return steps
}

func tokenStep(id, phase, set, member, partuuid, part string, gen int) Step {
	b, _ := json.Marshal(Token{Type: TokenType, Keyslots: []int{}, SetUUID: set, MemberUUID: member, PartUUID: partuuid, Generation: gen})
	return Step{ID: id, Phase: phase, Cmd: []string{"cryptsetup", "token", "import", "--token-replace", "--token-id", fmt.Sprint(TokenID), part},
		Stdin: string(b), Why: fmt.Sprintf("OneMind token on %s: set %s, generation %d (the boot assembly unlocks the members of the newest generation)", part, short(set), gen)}
}

func short(s string) string {
	if len(s) > 8 {
		return s[:8]
	}
	return s
}

// ParseLUKSDump reads `cryptsetup luksDump --dump-json-metadata` and returns
// the OneMind token, if any.
func ParseLUKSDump(data []byte) (*Token, error) {
	var doc struct {
		Tokens map[string]json.RawMessage `json:"tokens"`
	}
	if err := json.Unmarshal(data, &doc); err != nil {
		return nil, fmt.Errorf("luksDump JSON: %w", err)
	}
	for _, raw := range doc.Tokens {
		var t Token
		if json.Unmarshal(raw, &t) == nil && t.Type == TokenType {
			return &t, nil
		}
	}
	return nil, nil
}

// LUKS fills each present member's Backing (its LUKS2 partition), LUKSUUID
// and the set's Generation (the newest OneMind token). A member whose header
// cannot be read keeps generation 0; plans then start a fresh generation.
func (c *Collector) LUKS(ctx context.Context, m *Mirror, disks []Disk) {
	for i := range m.Members {
		mem := &m.Members[i]
		if mem.Missing {
			continue
		}
		mem.Backing = BackingOf(disks, mem.Path)
		if mem.Backing == "" {
			continue
		}
		m.Encrypted = true
		if _, s, ok := containing(disks, mem.Backing); ok {
			mem.LUKSUUID, mem.PartUUID = s.UUID, s.PartUUID
		}
		out, code, err := c.Run.Run(ctx, "cryptsetup", "luksDump", "--dump-json-metadata", mem.Backing)
		if err != nil || code != 0 {
			continue
		}
		if t, err := ParseLUKSDump(out); err == nil && t != nil {
			if t.MemberUUID != "" {
				mem.LUKSUUID = t.MemberUUID
			}
			if t.Generation > m.Generation {
				m.Generation = t.Generation
			}
		}
	}
}

// modhex is systemd's recovery-key alphabet (systemd-cryptenroll
// --recovery-key): it types the same on most keyboard layouts.
const modhex = "cbdefghijklnrtuv"

// NewRecoveryKey returns 256 random bits as 64 modhex characters in eight
// dash-separated groups, the format systemd-cryptenroll uses, so the owner
// can type it at the systemd passphrase prompt on any member.
func NewRecoveryKey() (string, error) {
	var b [32]byte
	if _, err := rand.Read(b[:]); err != nil {
		return "", err
	}
	var sb strings.Builder
	for i, x := range b {
		if i > 0 && i%4 == 0 {
			sb.WriteByte('-')
		}
		sb.WriteByte(modhex[x>>4])
		sb.WriteByte(modhex[x&0x0f])
	}
	return sb.String(), nil
}

// MakeRunDir creates dir (RunDir, or a lab's) with mode 0700. A missing parent
// (/run/onemind) is made 0755 whatever the umask: other services' sockets
// live there and the gateway must reach them, while MkdirAll alone would give
// the parent dir's 0700.
func MakeRunDir(dir string) error {
	parent := filepath.Dir(dir)
	if _, err := os.Stat(parent); errors.Is(err, fs.ErrNotExist) {
		if err := os.MkdirAll(parent, 0o755); err != nil {
			return err
		}
		if err := os.Chmod(parent, 0o755); err != nil {
			return err
		}
	}
	return os.MkdirAll(dir, 0o700)
}

// TPM2Present reports a TPM 2.0 the kernel exposes through the resource manager.
func TPM2Present() bool {
	_, err := os.Stat("/dev/tpmrm0")
	return err == nil
}

// PCRPublicKey is where a signed-UKI image ships the public key of its PCR 11
// signature (systemd-measure); when present, TPM2 unlock is also bound to it.
const PCRPublicKey = "/etc/systemd/tpm2-pcr-public-key.pem"

// InitOptions describe a fresh data partition (first boot, H-11).
type InitOptions struct {
	Part     string // the onemind-data partition, e.g. /dev/disk/by-partlabel/onemind-data
	PartUUID string // its GPT partition id (blkid PARTUUID), recorded in the token
	Mapper   string // default onemind-data
	Label    string // default onemind-data
	TPM2     bool   // enrol a TPM2 keyslot (systemd-cryptenroll)
	PCRKey   string // signed PCR 11 policy public key, if the image has one
	Top      string // where the top-level btrfs is mounted while subvolumes are created
	SetUUID  string // btrfs fsid; random when empty
}

// InitSteps are the first-boot steps for onemind-data: LUKS2 with the
// recovery key, the set key and (when present) TPM2, the OneMind token, btrfs
// single/dup with @, @storage and @snapshots, and the set key moved inside
// @. Key files are in RunDir (tmpfs) only. Run by `onemindd storage init`.
func InitSteps(o InitOptions) []Step {
	if o.Mapper == "" {
		o.Mapper = "onemind-data"
	}
	if o.Label == "" {
		o.Label = "onemind-data"
	}
	if o.Top == "" {
		o.Top = RunDir + "/top"
	}
	rk, sk := RecoveryKeyFile, RunDir+"/set.key"
	luksUUID := DerivedUUID(o.SetUUID, o.Part, "luks")
	dev := "/dev/mapper/" + o.Mapper
	steps := []Step{
		{ID: "luks-format", Cmd: []string{"cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode", "--cipher", "aes-xts-plain64", "--key-size", "512",
			"--pbkdf", "argon2id", "--pbkdf-memory", PBKDFMemoryKiB, "--label", o.Label, "--uuid", luksUUID, "--key-file", rk, o.Part},
			Why: "LUKS2 on the data partition; the first keyslot is the owner's recovery key", Destructive: true},
		{ID: "luks-setkey", Cmd: []string{"cryptsetup", "luksAddKey", "--batch-mode", "--pbkdf", "pbkdf2", "--pbkdf-force-iterations", "1000", "--key-file", rk, o.Part, sk},
			Why: "the set key (512 random bits, so a fast KDF is enough) for onemindd's own operations"},
	}
	if o.TPM2 {
		cmd := []string{"systemd-cryptenroll", "--tpm2-device=auto", "--tpm2-pcrs=7", "--unlock-key-file=" + sk}
		if o.PCRKey != "" {
			cmd = append(cmd, "--tpm2-public-key="+o.PCRKey, "--tpm2-public-key-pcrs=11")
		}
		steps = append(steps, Step{ID: "luks-tpm2", Cmd: append(cmd, o.Part), Why: "unlock at boot with the TPM2 when the firmware and signed system are unchanged"})
	}
	b, _ := json.Marshal(Token{Type: TokenType, Keyslots: []int{}, SetUUID: o.SetUUID, MemberUUID: luksUUID, PartUUID: o.PartUUID, Generation: 1})
	steps = append(steps,
		Step{ID: "token", Cmd: []string{"cryptsetup", "token", "import", "--token-id", fmt.Sprint(TokenID), o.Part}, Stdin: string(b), Why: "OneMind token, generation 1"},
		Step{ID: "luks-open", Cmd: []string{"cryptsetup", "open", "--key-file", sk, o.Part, o.Mapper}, Why: "unlock it"},
		Step{ID: "mkfs", Cmd: []string{"mkfs.btrfs", "--label", o.Label, "--uuid", o.SetUUID, "--data", "single", "--metadata", "dup", dev}, Why: "btrfs, one disk: one data copy, two metadata copies", Destructive: true},
		Step{ID: "top", Cmd: []string{"mkdir", "-p", o.Top}, Why: "temporary mount point"},
		Step{ID: "mount", Cmd: []string{"mount", "-o", MountOptions, dev, o.Top}, Why: "mount the top level"},
	)
	for _, sv := range []string{"@", "@storage", "@snapshots"} {
		steps = append(steps, Step{ID: "subvolume", Cmd: []string{"btrfs", "subvolume", "create", o.Top + "/" + sv}, Why: "subvolume layout (storage.md §4.2)"})
	}
	keyDir := filepath.Dir(o.Top + "/@/" + SetKeyPath)
	steps = append(steps,
		Step{ID: "keydir", Cmd: []string{"install", "-d", "-m", "0700", keyDir}, Why: "folder for the set key, inside the encrypted set"},
		Step{ID: "keymove", Cmd: []string{"install", "-m", "0600", sk, o.Top + "/@/" + SetKeyPath}, Why: "keep the set key inside the encrypted set"},
		Step{ID: "keydrop", Cmd: []string{"rm", "-f", sk}, Why: "no key file left in /run"},
		Step{ID: "umount", Cmd: []string{"umount", o.Top}, Why: "the image's fstab mounts @ at /data (os patch)"},
	)
	return steps
}
