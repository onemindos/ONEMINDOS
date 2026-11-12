// SPDX-License-Identifier: Apache-2.0

package storage

import (
	"context"
	"encoding/json"
	"fmt"
)

// Verdict is a disk's health summary, in the notification severities.
type Verdict string

const (
	VerdictOK       Verdict = "ok"
	VerdictWarning  Verdict = "warning"
	VerdictCritical Verdict = "critical"
	VerdictUnknown  Verdict = "unknown" // SMART unavailable (virtual disk, some USB bridges)
)

// Thresholds are the alert limits. Vendor temperature limits from
// `nvme id-ctrl` replace the defaults in STOR-6; these are the fallbacks.
type Thresholds struct {
	TempWarnC   int `json:"temp_warn_c"`
	TempCritC   int `json:"temp_crit_c"`
	WearWarnPct int `json:"wear_warn_pct"`
	WearCritPct int `json:"wear_crit_pct"`
}

// DefaultThresholds follow docs/umbrel2/storage.md §4.7.
var DefaultThresholds = Thresholds{TempWarnC: 60, TempCritC: 70, WearWarnPct: 80, WearCritPct: 95}

// Health is what smartctl says about one disk.
type Health struct {
	Path           string   `json:"path"`
	Supported      bool     `json:"supported"`
	Protocol       string   `json:"protocol,omitempty"` // ATA, NVMe, SCSI
	Passed         *bool    `json:"smart_passed,omitempty"`
	TemperatureC   *int     `json:"temperature_c,omitempty"`
	PowerOnHours   *int     `json:"power_on_hours,omitempty"`
	WearPercent    *int     `json:"wear_percent,omitempty"`    // NVMe percentage_used (can exceed 100)
	MediaErrors    *int     `json:"media_errors,omitempty"`    // NVMe
	AvailableSpare *int     `json:"available_spare,omitempty"` // NVMe, percent
	Reallocated    *int     `json:"reallocated_sectors,omitempty"`
	Pending        *int     `json:"pending_sectors,omitempty"`
	Uncorrectable  *int     `json:"uncorrectable_sectors,omitempty"`
	Verdict        Verdict  `json:"verdict"`
	Reasons        []string `json:"reasons,omitempty"`
	ExitStatus     int      `json:"smartctl_exit_status"`
}

// SmartArgs is the smartctl call for a disk. USB bridges usually need the
// SAT pass-through (-d sat); everything else is auto-detected.
func SmartArgs(d Disk) []string {
	args := []string{"--json=c", "-a"}
	if d.Transport == "usb" {
		args = append(args, "-d", "sat")
	}
	return append(args, d.Path)
}

// Health runs smartctl for one disk and evaluates it with t.
func (c *Collector) Health(ctx context.Context, d Disk, t Thresholds) (Health, error) {
	out, code, err := c.Run.Run(ctx, "smartctl", SmartArgs(d)...)
	if err != nil {
		return Health{Path: d.Path, Verdict: VerdictUnknown}, fmt.Errorf("smartctl: %w", err)
	}
	h, err := ParseSmart(out, code, t)
	h.Path = d.Path
	return h, err
}

type smartDoc struct {
	Smartctl struct {
		ExitStatus int `json:"exit_status"`
		Messages   []struct {
			String   string `json:"string"`
			Severity string `json:"severity"`
		} `json:"messages"`
	} `json:"smartctl"`
	Device struct {
		Protocol string `json:"protocol"`
	} `json:"device"`
	SmartStatus *struct {
		Passed bool `json:"passed"`
	} `json:"smart_status"`
	Temperature *struct {
		Current int `json:"current"`
	} `json:"temperature"`
	PowerOnTime *struct {
		Hours int `json:"hours"`
	} `json:"power_on_time"`
	NVMe *struct {
		CriticalWarning         int `json:"critical_warning"`
		AvailableSpare          int `json:"available_spare"`
		AvailableSpareThreshold int `json:"available_spare_threshold"`
		PercentageUsed          int `json:"percentage_used"`
		MediaErrors             int `json:"media_errors"`
	} `json:"nvme_smart_health_information_log"`
	ATA *struct {
		Table []struct {
			ID  int `json:"id"`
			Raw struct {
				Value int `json:"value"`
			} `json:"raw"`
		} `json:"table"`
	} `json:"ata_smart_attributes"`
}

// smartctl exit-status bits (smartctl(8) "RETURN VALUES").
const (
	exitCmdline     = 1 << 0
	exitOpenFailed  = 1 << 1
	exitDiskFailing = 1 << 3
	exitPrefail     = 1 << 4
)

// ParseSmart reads `smartctl --json -a` output. exit is smartctl's exit
// code (the JSON copy is used when present).
func ParseSmart(data []byte, exit int, t Thresholds) (Health, error) {
	var doc smartDoc
	if err := json.Unmarshal(data, &doc); err != nil {
		return Health{Verdict: VerdictUnknown, ExitStatus: exit}, fmt.Errorf("smartctl JSON: %w", err)
	}
	if doc.Smartctl.ExitStatus != 0 {
		exit = doc.Smartctl.ExitStatus
	}
	h := Health{ExitStatus: exit, Protocol: doc.Device.Protocol}
	if exit&(exitCmdline|exitOpenFailed) != 0 || doc.SmartStatus == nil && doc.NVMe == nil && doc.ATA == nil {
		h.Verdict = VerdictUnknown
		for _, m := range doc.Smartctl.Messages {
			if m.Severity == "error" {
				h.Reasons = append(h.Reasons, m.String)
			}
		}
		if len(h.Reasons) == 0 {
			h.Reasons = []string{"SMART data not available"}
		}
		return h, nil
	}
	h.Supported = true
	if doc.SmartStatus != nil {
		p := doc.SmartStatus.Passed
		h.Passed = &p
	}
	if doc.Temperature != nil {
		h.TemperatureC = intp(doc.Temperature.Current)
	}
	if doc.PowerOnTime != nil {
		h.PowerOnHours = intp(doc.PowerOnTime.Hours)
	}
	if n := doc.NVMe; n != nil {
		h.WearPercent, h.MediaErrors, h.AvailableSpare = intp(n.PercentageUsed), intp(n.MediaErrors), intp(n.AvailableSpare)
	}
	if a := doc.ATA; a != nil {
		for _, row := range a.Table {
			switch row.ID {
			case 5:
				h.Reallocated = intp(row.Raw.Value)
			case 197:
				h.Pending = intp(row.Raw.Value)
			case 198:
				h.Uncorrectable = intp(row.Raw.Value)
			}
		}
	}

	h.Verdict = VerdictOK
	raise := func(v Verdict, why string) {
		h.Reasons = append(h.Reasons, why)
		if v == VerdictCritical || h.Verdict == VerdictOK {
			h.Verdict = v
		}
	}
	if (h.Passed != nil && !*h.Passed) || exit&exitDiskFailing != 0 {
		raise(VerdictCritical, "SMART overall health check failed")
	}
	if exit&exitPrefail != 0 {
		raise(VerdictCritical, "a pre-failure attribute is at or below its threshold")
	}
	if n := doc.NVMe; n != nil {
		if n.CriticalWarning != 0 {
			raise(VerdictCritical, fmt.Sprintf("NVMe critical warning flags 0x%02x", n.CriticalWarning))
		}
		if n.AvailableSpareThreshold > 0 && n.AvailableSpare < n.AvailableSpareThreshold {
			raise(VerdictCritical, fmt.Sprintf("spare blocks %d%% below the %d%% threshold", n.AvailableSpare, n.AvailableSpareThreshold))
		}
		if n.MediaErrors > 0 {
			raise(VerdictWarning, fmt.Sprintf("%d media errors", n.MediaErrors))
		}
	}
	if w := h.WearPercent; w != nil {
		switch {
		case *w >= t.WearCritPct:
			raise(VerdictCritical, fmt.Sprintf("wear %d%% (replace now)", *w))
		case *w >= t.WearWarnPct:
			raise(VerdictWarning, fmt.Sprintf("wear %d%% (plan a replacement)", *w))
		}
	}
	if tc := h.TemperatureC; tc != nil {
		switch {
		case *tc >= t.TempCritC:
			raise(VerdictCritical, fmt.Sprintf("temperature %d°C", *tc))
		case *tc >= t.TempWarnC:
			raise(VerdictWarning, fmt.Sprintf("temperature %d°C", *tc))
		}
	}
	for _, c := range []struct {
		v    *int
		what string
	}{{h.Reallocated, "reallocated"}, {h.Pending, "pending"}, {h.Uncorrectable, "uncorrectable"}} {
		if c.v != nil && *c.v > 0 {
			raise(VerdictWarning, fmt.Sprintf("%d %s sectors", *c.v, c.what))
		}
	}
	return h, nil
}

func intp(v int) *int { return &v }
