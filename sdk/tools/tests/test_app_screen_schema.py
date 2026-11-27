# SPDX-License-Identifier: Apache-2.0
"""The screen describes content only; an app descriptor must authorize all referenced operations."""

import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


class ScreenSchemaTest(unittest.TestCase):
    def setUp(self):
        schema_path = Path(__file__).resolve().parents[2] / "schema" / "onemind.screen.schema.json"
        schema = json.loads(schema_path.read_text())
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def page(self, *nodes):
        return {"schema": "onemind.screen/v1", "id": "work", "title": "Work", "nodes": list(nodes)}

    def test_document_contains_every_supported_node(self):
        data = {"tool": "work_tasks_list"}
        labelled = [{"key": "title", "label": "Task"}]
        nodes = [
            {"type": "list", "data": data, "columns": labelled},
            {"type": "detail", "data": data, "fields": labelled},
            {"type": "form", "action": "work.task.create", "fields": [{**labelled[0], "format": "text"}]},
            {"type": "stat", "data": data, "value": "total"},
            {"type": "timeline", "data": data, "when": "created_at", "label": "title"},
            {"type": "empty", "message": "No tasks"},
            {"type": "error", "message": "Cannot load tasks"},
            {"type": "map-layer", "data": data, "geometry": "position"},
        ]
        self.validator.validate(self.page(*({"title": "Tasks", **node} for node in nodes)))

    def test_refuses_unknown_nodes_executable_fields_and_unvetted_urls(self):
        each = [
            {"type": "script", "source": "alert(1)"},
            {"type": "empty", "message": "hello", "onload": "alert(1)"},
            {"type": "map-layer", "data": {"tool": "list", "url": "https://example.invalid"}, "geometry": "position"},
            {"type": "stat", "data": {"tool": "https://example.invalid"}, "value": "total"},
            {"type": "form", "action": "/v1/actions", "fields": [{"key": "title", "label": "Title", "format": "text"}]},
        ]
        for node in each:
            with self.subTest(node=node):
                self.assertFalse(self.validator.is_valid(self.page({"title": "Tasks", **node})))
