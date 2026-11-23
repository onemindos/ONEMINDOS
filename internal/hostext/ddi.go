// SPDX-License-Identifier: Apache-2.0

package hostext

// Reading a Discoverable Disk Image (DDI): a GPT disk image whose partitions are found by type.
// A signed sysext or confext carries three partitions of one class (root or /usr): the file
// system, its dm-verity hash tree and a verity signature partition. The signature partition
// holds JSON {rootHash, signature, certificateFingerprint}: a PKCS#7 signature over the exact
// root-hash string, padded with NUL bytes to a multiple of 4096. The data and verity partition
// UUIDs are the first and last 128 bits of that root hash, which ties the signed hash to them.
// Source: UAPI Group, Discoverable Partitions Specification (uapi-group.org/specifications/specs/
// discoverable_partitions_specification), "Verity" and the partition type table.

import (
	"bytes"
	"crypto/x509"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"hash/crc32"
	"io"
	"os"
	"regexp"
)

// PartTypes are the GPT partition type UUIDs per systemd architecture identifier (the
// specification's table; OneMind ships x86-64 and arm64 images only).
var PartTypes = map[string]struct{ Root, RootVerity, RootSig, Usr, UsrVerity, UsrSig string }{
	"x86-64": {
		"4f68bce3-e8cd-4db1-96e7-fbcaf984b709", "2c7357ed-ebd2-46d9-aec1-23d437ec2bf5", "41092b05-9fc8-4523-994f-2def0408b176",
		"8484680c-9521-48c6-9c11-b0720656f69e", "77ff5f63-e7b6-4633-acf4-1565b864c0e6", "e7bb33fb-06cf-4e81-8273-e543b413e2e2",
	},
	"arm64": {
		"b921b045-1df0-41c3-af44-4c6f280d3fae", "df3300ce-d69f-4c92-978c-9bfb0f38d820", "6db69de6-29f4-4758-a7a5-962190f00ce3",
		"b0e01050-ee5f-4390-949a-9101b17104e9", "6e11a4e7-fbca-4ded-b9e9-e1a512bb664e", "c23ce4ff-44bd-4b00-b2d4-b41b3419e02a",
	},
}

// Verified is what the signature check proved about an image.
type Verified struct {
	RootHash    string `json:"root_hash"`
	Partition   string `json:"partition"` // "root" or "usr"
	Fingerprint string `json:"key_fingerprint"`
}

type gptPart struct {
	typ, uuid   string
	first, last uint64
}

const maxSigPartition = 1 << 20

var hexHash = regexp.MustCompile(`^[0-9a-f]{64,128}$`)

func guidString(b []byte) string {
	return fmt.Sprintf("%08x-%04x-%04x-%x-%x", binary.LittleEndian.Uint32(b[0:]), binary.LittleEndian.Uint16(b[4:]),
		binary.LittleEndian.Uint16(b[6:]), b[8:10], b[10:16])
}

// readGPT reads the primary GPT, trying 512- and 4096-byte sectors, and checks both CRCs.
func readGPT(f io.ReaderAt) ([]gptPart, uint64, error) {
	for _, ss := range []uint64{512, 4096} {
		h := make([]byte, ss)
		if _, err := f.ReadAt(h, int64(ss)); err != nil || string(h[:8]) != "EFI PART" {
			continue
		}
		hsize := binary.LittleEndian.Uint32(h[12:])
		if hsize < 92 || uint64(hsize) > ss {
			return nil, 0, fmt.Errorf("GPT header size %d", hsize)
		}
		hc := append([]byte{}, h[:hsize]...)
		binary.LittleEndian.PutUint32(hc[16:], 0)
		if crc32.ChecksumIEEE(hc) != binary.LittleEndian.Uint32(h[16:]) {
			return nil, 0, fmt.Errorf("GPT header checksum mismatch")
		}
		lba, n, es := binary.LittleEndian.Uint64(h[72:]), binary.LittleEndian.Uint32(h[80:]), binary.LittleEndian.Uint32(h[84:])
		if es < 128 || es%8 != 0 || n == 0 || uint64(n)*uint64(es) > 1<<20 {
			return nil, 0, fmt.Errorf("GPT table of %d entries of %d bytes", n, es)
		}
		tbl := make([]byte, uint64(n)*uint64(es))
		if _, err := f.ReadAt(tbl, int64(lba*ss)); err != nil {
			return nil, 0, fmt.Errorf("GPT table: %w", err)
		}
		if crc32.ChecksumIEEE(tbl) != binary.LittleEndian.Uint32(h[88:]) {
			return nil, 0, fmt.Errorf("GPT table checksum mismatch")
		}
		var parts []gptPart
		for i := uint32(0); i < n; i++ {
			e := tbl[uint64(i)*uint64(es):]
			if bytes.Equal(e[:16], make([]byte, 16)) {
				continue
			}
			parts = append(parts, gptPart{guidString(e[0:16]), guidString(e[16:32]),
				binary.LittleEndian.Uint64(e[32:]), binary.LittleEndian.Uint64(e[40:])})
		}
		return parts, ss, nil
	}
	return nil, 0, fmt.Errorf("no GPT partition table")
}

func uuidOf(hexPart string) string {
	return hexPart[0:8] + "-" + hexPart[8:12] + "-" + hexPart[12:16] + "-" + hexPart[16:20] + "-" + hexPart[20:32]
}

// VerifyImage checks that path is a DDI for arch whose verity root hash is signed by one of keys.
// It reads only the partition table and the signature partition; the kernel's dm-verity checks
// every data block against that root hash when systemd merges the image.
func VerifyImage(path, arch string, keys []*x509.Certificate) (*Verified, error) {
	ty, ok := PartTypes[arch]
	if !ok {
		return nil, refuse("wrong_arch", "this host's architecture %q has no extension support", arch)
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	parts, ss, err := readGPT(f)
	if err != nil {
		return nil, refuse("not_image", "not a disk image (%v): only signed .raw images are accepted", err)
	}
	find := func(typ string) []gptPart {
		var out []gptPart
		for _, p := range parts {
			if p.typ == typ {
				out = append(out, p)
			}
		}
		return out
	}
	class, data, verity, sig := "usr", find(ty.Usr), find(ty.UsrVerity), find(ty.UsrSig)
	if rs := find(ty.RootSig); len(rs) > 0 || len(sig) == 0 {
		class, data, verity, sig = "root", find(ty.Root), find(ty.RootVerity), rs
		if len(rs) > 0 && len(find(ty.UsrSig)) > 0 {
			return nil, refuse("not_image", "the image carries both a root and a /usr signature")
		}
	}
	if len(sig) == 0 {
		return nil, refuse("unsigned", "no verity signature partition for %s: unsigned images are refused", arch)
	}
	if len(sig) != 1 || len(data) != 1 || len(verity) != 1 {
		return nil, refuse("not_image", "the image needs exactly one %s data, verity and signature partition", class)
	}
	size := (sig[0].last - sig[0].first + 1) * ss
	if sig[0].last < sig[0].first || size > maxSigPartition {
		return nil, refuse("not_image", "signature partition of %d bytes", size)
	}
	raw := make([]byte, size)
	if _, err := f.ReadAt(raw, int64(sig[0].first*ss)); err != nil {
		return nil, refuse("not_image", "signature partition: %v", err)
	}
	var js struct {
		RootHash    string `json:"rootHash"`
		Signature   string `json:"signature"`
		Fingerprint string `json:"certificateFingerprint"`
	}
	if err := json.Unmarshal(bytes.TrimRight(raw, "\x00"), &js); err != nil || js.Signature == "" {
		return nil, refuse("unsigned", "the signature partition holds no signature")
	}
	if !hexHash.MatchString(js.RootHash) || len(js.RootHash)%2 != 0 {
		return nil, refuse("bad_signature", "the signed root hash is not lowercase hex")
	}
	if data[0].uuid != uuidOf(js.RootHash) || verity[0].uuid != uuidOf(js.RootHash[len(js.RootHash)-32:]) {
		return nil, refuse("bad_signature", "the signed root hash does not match the image's partitions")
	}
	der, err := base64.StdEncoding.DecodeString(js.Signature)
	if err != nil {
		return nil, refuse("bad_signature", "the signature is not base64")
	}
	cert, err := verifyPKCS7(der, []byte(js.RootHash), keys, js.Fingerprint)
	if err != nil {
		return nil, err
	}
	return &Verified{RootHash: js.RootHash, Partition: class, Fingerprint: fingerprint(cert)}, nil
}

func fingerprint(c *x509.Certificate) string {
	s := sha256Sum(c.Raw)
	return hex.EncodeToString(s[:])
}
