// SPDX-License-Identifier: Apache-2.0

package cli

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"strconv"
	"strings"
	"unicode"

	"github.com/spf13/cobra"
	"gopkg.in/yaml.v3"
)

const backstageExportLimit = 16 * 1024 * 1024

type backstagePlan struct {
	Entries   []backstagePlanEntry `json:"entries"`
	MorePages bool                 `json:"more_pages"`
}

type backstagePlanEntry struct {
	Document      int    `json:"document"`
	Entity        int    `json:"entity"`
	Disposition   string `json:"disposition"`
	Destination   string `json:"destination"`
	Reason        string `json:"reason"`
	Links         int    `json:"links,omitempty"`
	SkippedLinks  int    `json:"skipped_links,omitempty"`
	Documentation bool   `json:"documentation_reference,omitempty"`
}

func importCommands(a *App) []*cobra.Command {
	group := &cobra.Command{Use: "import", Short: "Plan a one-time import from another system"}
	var plan bool
	backstage := &cobra.Command{
		Use:   "backstage --plan [EXPORT]",
		Short: "Review a Backstage entity export locally without changing the box",
		Long: "Plan from local Backstage entity YAML or JSON. Pass a file, or pipe the export to stdin. " +
			"The plan shows each entity by position and omits private metadata and link URLs.",
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if !plan {
				return usageErr(cmd, "--plan is required")
			}
			in := a.Stdin
			if len(args) == 1 && args[0] != "-" {
				file, err := os.Open(args[0])
				if err != nil {
					return errors.New("could not open the Backstage export file")
				}
				defer file.Close()
				in = file
			} else if a.Interactive() {
				return usageErr(cmd, "supply an export file or pipe the export to stdin")
			}
			result, err := readBackstagePlan(in)
			if err != nil {
				return err
			}
			if a.G.JSON {
				return printJSON(a.Stdout, result)
			}
			return printBackstagePlan(a.Stdout, result)
		},
	}
	backstage.Flags().BoolVar(&plan, "plan", false, "classify the entities without applying changes")
	group.AddCommand(backstage)
	return []*cobra.Command{group}
}

func readBackstagePlan(in io.Reader) (backstagePlan, error) {
	plan := backstagePlan{Entries: []backstagePlanEntry{}}
	data, err := io.ReadAll(io.LimitReader(in, backstageExportLimit+1))
	if err != nil {
		return plan, errors.New("could not read the Backstage export")
	}
	if len(data) > backstageExportLimit {
		return plan, errors.New("the Backstage export exceeds 16 MiB")
	}

	dec := yaml.NewDecoder(bytes.NewReader(data))
	for document := 1; ; document++ {
		var doc yaml.Node
		err := dec.Decode(&doc)
		if errors.Is(err, io.EOF) {
			return plan, nil
		}
		if err != nil {
			// Parser errors may quote content from the private export.
			return plan, fmt.Errorf("invalid Backstage YAML or JSON in document %d", document)
		}
		if len(doc.Content) == 0 || doc.Content[0].ShortTag() == "!!null" {
			continue
		}
		node := doc.Content[0]
		entities := []*yaml.Node{node}
		if node.Kind == yaml.SequenceNode {
			entities = node.Content
		} else if backstageField(node, "apiVersion") == nil && backstageField(node, "kind") == nil {
			page, items := backstageField(node, "pageInfo"), backstageField(node, "items")
			if page != nil && page.Kind == yaml.MappingNode && items != nil && items.Kind == yaml.SequenceNode {
				entities = items.Content
				plan.MorePages = plan.MorePages || backstageString(backstageField(page, "nextCursor")) != ""
			}
		}
		for i, entity := range entities {
			plan.Entries = append(plan.Entries, classifyBackstageEntity(document, i+1, entity))
		}
	}
}

// Only standard envelope fields drive this plan. Do not expand aliases, follow locations,
// or parse opaque spec fields. Retain no input strings in the plan, including entity names.
func classifyBackstageEntity(document, entity int, node *yaml.Node) backstagePlanEntry {
	entry := backstagePlanEntry{Document: document, Entity: entity, Disposition: "archived", Destination: "private archive"}
	kind := backstageString(backstageField(node, "kind"))
	api := backstageString(backstageField(node, "apiVersion"))
	metadata := backstageField(node, "metadata")
	if kind == "" || api == "" || backstageString(backstageField(metadata, "name")) == "" {
		entry.Reason = "Missing a usable catalog envelope"
		return entry
	}
	if api != "backstage.io/v1alpha1" {
		entry.Reason = "Catalog API version has no verified mapping"
		return entry
	}

	if links := backstageField(metadata, "links"); links != nil {
		if links.Kind == yaml.SequenceNode {
			for _, link := range links.Content {
				if backstageHTTPSLink(backstageString(backstageField(link, "url"))) {
					entry.Links++
				} else {
					entry.SkippedLinks++
				}
			}
		} else {
			entry.SkippedLinks++
		}
	}
	annotations := backstageField(metadata, "annotations")
	entry.Documentation = hasBackstageDocsReference(annotations)
	switch {
	case entry.Links > 0:
		entry.Disposition, entry.Destination, entry.Reason = "mapped", "Links", "Catalog hyperlinks are candidates for the Links list"
	case entry.Documentation:
		entry.Disposition, entry.Destination, entry.Reason = "linked", "documentation", "Resolve the TechDocs reference before linking"
	case entry.SkippedLinks > 0:
		entry.Reason = "No eligible HTTPS metadata links"
	case kind == "Component":
		entry.Reason = "No verified OneMind app match"
	case kind == "Resource":
		entry.Reason = "No verified OneMind device or node match"
	default:
		entry.Reason = "No verified typed destination"
	}
	return entry
}

func backstageField(node *yaml.Node, name string) *yaml.Node {
	if node == nil || node.Kind != yaml.MappingNode {
		return nil
	}
	var value *yaml.Node
	for i := 0; i < len(node.Content); i += 2 {
		if backstageString(node.Content[i]) == name {
			if value != nil {
				return nil // Ambiguous duplicate fields cannot support a typed mapping.
			}
			value = node.Content[i+1]
		}
	}
	return value
}

func backstageString(node *yaml.Node) string {
	if node == nil || node.Kind != yaml.ScalarNode || node.ShortTag() != "!!str" {
		return ""
	}
	return strings.TrimSpace(node.Value)
}

func backstageHTTPSLink(value string) bool {
	// Personal Links (core/onemind_core/home.py) take HTTPS addresses with no userinfo.
	if len(value) > 2048 || strings.ContainsRune(value, '\\') || strings.ContainsFunc(value, unicode.IsSpace) {
		return false
	}
	parsed, err := url.Parse(value)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" || parsed.User != nil {
		return false
	}
	if port := parsed.Port(); port != "" {
		_, err = strconv.ParseUint(port, 10, 16)
	}
	return err == nil
}

func hasBackstageDocsReference(annotations *yaml.Node) bool {
	ref := backstageString(backstageField(annotations, "backstage.io/techdocs-ref"))
	kind, target, _ := strings.Cut(ref, ":")
	return kind == "dir" && target != "" || kind == "url" && backstageHTTPSLink(target) ||
		backstageString(backstageField(annotations, "backstage.io/techdocs-entity")) != ""
}

func printBackstagePlan(out io.Writer, plan backstagePlan) error {
	if _, err := fmt.Fprintln(out, "Backstage import plan. No changes applied. Source positions are 1-based."); err != nil {
		return err
	}
	if plan.MorePages {
		if _, err := fmt.Fprintln(out, "The export references additional catalog pages. Only supplied entities are shown."); err != nil {
			return err
		}
	}
	rows := make([][]string, 0, len(plan.Entries))
	for _, entry := range plan.Entries {
		rows = append(rows, []string{
			fmt.Sprintf("%d/%d", entry.Document, entry.Entity), entry.Disposition, entry.Destination,
			strconv.Itoa(entry.Links), strconv.Itoa(entry.SkippedLinks), strconv.FormatBool(entry.Documentation), entry.Reason,
		})
	}
	return table(out, "DOC/ITEM\tDISPOSITION\tDESTINATION\tLINKS\tSKIPPED\tDOCS REF\tDETAIL", rows)
}
