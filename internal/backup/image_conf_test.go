// SPDX-License-Identifier: Apache-2.0
package backup

import "testing"

// testdata/image-agent.json is what onemind-firstboot writes on an image hub (IMG-BACKUP-01;
// test/unit/test_image_backups.py checks the generator still produces exactly this file). It must load.
func TestImageAgentConfLoads(t *testing.T) {
	c, err := LoadConfig("testdata/image-agent.json")
	if err != nil {
		t.Fatal(err)
	}
	if c.Restic.Binary != "/usr/lib/onemind/restic" || c.StateDir != "/data/onemind/backup" {
		t.Fatalf("unexpected paths: %+v", c)
	}
	if c.Listen != "127.0.0.1:7480" || len(c.Targets) != 0 || !c.Schedule.GatewayHourly {
		t.Fatalf("a fresh image hub must listen on loopback with no destination: %+v", c)
	}
	if c.Units.K3s == nil || c.Units.System == nil || c.Units.System.AuditLog == "" {
		t.Fatalf("system and k3s units missing: %+v", c.Units)
	}
}
