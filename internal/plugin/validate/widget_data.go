// SPDX-License-Identifier: Apache-2.0

package validate

import (
	"bytes"
	"fmt"
	"strings"
	"sync"

	"github.com/onemindos/onemindos/sdk/schema"
	"github.com/santhosh-tekuri/jsonschema/v6"
)

var widgetDataSchema = sync.OnceValues(func() (*jsonschema.Schema, error) {
	c := compiler()
	doc, err := jsonschema.UnmarshalJSON(strings.NewReader(schema.WidgetTemplates))
	if err != nil {
		return nil, err
	}
	const location = "https://onemind.invalid/widget-data"
	if err := c.AddResource(location, doc); err != nil {
		return nil, err
	}
	return c.Compile(location)
})

// WidgetData validates a single JSON typed-widget result against the published
// contract. Host rendering is implemented separately (#179); validation neither
// executes code nor fetches data. observed_at is syntax-checked, while the host
// decides whether a valid timestamp is stale and renders all strings as text.
func WidgetData(data []byte) error {
	if len(data) > MaxManifestBytes {
		return fmt.Errorf("widget data exceeds %d bytes", MaxManifestBytes)
	}
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(data))
	if err != nil {
		return fmt.Errorf("widget data: %w", err)
	}
	s, err := widgetDataSchema()
	if err != nil {
		return fmt.Errorf("widget schema: %w", err)
	}
	if err := s.Validate(doc); err != nil {
		return fmt.Errorf("widget data: %w", err)
	}
	return nil
}
