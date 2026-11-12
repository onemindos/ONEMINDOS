package heartbeat

import "testing"

func TestValidateNodeID(t *testing.T) {
	for _, id := range []string{"3f9c2a1b7d4e", "beelink", "Node_01-a"} {
		if err := ValidateNodeID(id); err != nil {
			t.Errorf("ValidateNodeID(%q) = %v, want nil", id, err)
		}
	}
	long := make([]byte, 65)
	for i := range long {
		long[i] = 'a'
	}
	for _, id := range []string{"", "a.b", "*", ">", "node 1", "a\tb", "nodé", string(long)} {
		if err := ValidateNodeID(id); err == nil {
			t.Errorf("ValidateNodeID(%q) = nil, want error", id)
		}
	}
}

func TestValidateRole(t *testing.T) {
	for _, r := range []string{"hub", "node"} {
		if err := ValidateRole(r); err != nil {
			t.Errorf("ValidateRole(%q) = %v", r, err)
		}
	}
	for _, r := range []string{"", "Hub", "worker"} {
		if ValidateRole(r) == nil {
			t.Errorf("ValidateRole(%q) = nil, want error", r)
		}
	}
}
