// Package version holds the build version of the OneMind Go binaries.
// The Makefile overrides Version with
// -ldflags "-X github.com/onemindos/onemindos/internal/version.Version=<v>".
package version

// Version is the agent_version reported in every heartbeat (contract §2).
var Version = "0.1.0"
