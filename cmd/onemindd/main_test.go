package main

import "testing"

func TestValidate(t *testing.T) {
	ok := []struct{ role, id string }{{"node", ""}, {"hub", "3f9c2a1b7d4e"}, {"node", "pi-kitchen_2"}}
	for _, c := range ok {
		if err := validate(c.role, c.id); err != nil {
			t.Errorf("validate(%q, %q) = %v", c.role, c.id, err)
		}
	}
	bad := []struct{ role, id string }{{"worker", ""}, {"node", "a.b"}, {"node", "node>"}, {"node", "x y"}, {"hub", "*"}}
	for _, c := range bad {
		if validate(c.role, c.id) == nil {
			t.Errorf("validate(%q, %q) = nil, want error", c.role, c.id)
		}
	}
}
