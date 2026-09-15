"""Strictly-defined documentation and migration tools."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from week7.inputs import DocumentationCorpus
from week7.schemas import MigrationOutput, MigrationScenario, SchemaError, SourceCitation


def _schema_string(name: str) -> dict[str, Any]:
    return {"type": "string", "description": name}


TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "search_documentation": {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {
            "query": _schema_string("Migration question or focused search query"),
            "source_files": {"type": "array", "items": {"type": "string"}},
            "page_numbers": {"type": "array", "items": {"type": "integer", "minimum": 1}},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    },
    "inspect_source": {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_file", "page_number"],
        "properties": {
            "source_file": _schema_string("Input PDF filename"),
            "page_number": {"type": "integer", "minimum": 1},
        },
    },
    "check_deprecation": {
        "type": "object",
        "additionalProperties": False,
        "required": ["api_version", "endpoint", "parameter"],
        "properties": {
            "api_version": {
                "type": "string",
                "enum": ["2022-11-28", "2025-06-01"],
                "description": "GitHub REST API version to inspect",
            },
            "endpoint": _schema_string("Endpoint whose parameter is being checked"),
            "parameter": _schema_string("One endpoint parameter to check"),
        },
    },
}


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], dict[str, Any]]


def _validate_schema(value: Any, schema: dict[str, Any], path: str = "arguments") -> None:
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise SchemaError(f"{path} must be an object")
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(schema.get("properties", {}))
            if unknown:
                raise SchemaError(f"{path} contains unknown fields: {sorted(unknown)}")
        missing = set(schema.get("required", [])) - set(value)
        if missing:
            raise SchemaError(f"{path} is missing fields: {sorted(missing)}")
        for key, child_schema in schema.get("properties", {}).items():
            if key in value:
                _validate_schema(value[key], child_schema, f"{path}.{key}")
    elif schema_type == "array":
        if not isinstance(value, list):
            raise SchemaError(f"{path} must be an array")
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaError(f"{path} must contain at least {schema['minItems']} items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaError(f"{path} must contain at most {schema['maxItems']} items")
        for index, item in enumerate(value):
            _validate_schema(item, schema["items"], f"{path}[{index}]")
    elif schema_type == "string":
        if not isinstance(value, str) or (schema.get("minLength", 0) > 0 and not value.strip()):
            raise SchemaError(f"{path} must be a non-empty string")
        if "enum" in schema and value not in schema["enum"]:
            raise SchemaError(f"{path} must be one of {schema['enum']}")
    elif schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaError(f"{path} must be an integer")
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaError(f"{path} must be >= {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaError(f"{path} must be <= {schema['maximum']}")


def _concept_tokens(text: str) -> set[str]:
    stop_words = {
        "what", "which", "how", "does", "did", "the", "and", "for", "from", "with", "that", "this",
        "into", "than", "when", "where", "between", "version", "using", "used", "change", "changed",
        "required", "support", "supports", "supported", "option", "options", "parameter", "parameters",
        "default", "true", "false", "string", "object", "boolean", "new", "old", "prior", "also",
    }
    tokens = {
        token.lower().strip(".,:;()[]{}'\"`-")
        for token in re.findall(r"[A-Za-z][A-Za-z0-9_./-]{2,}", text)
    }
    return {token for token in tokens if token not in stop_words and len(token) >= 4}


class ToolRegistry:
    """Registry shared by the agent and deterministic workflow."""

    def __init__(self, corpus: DocumentationCorpus, scenarios: list[MigrationScenario]) -> None:
        self.corpus = corpus
        self.scenarios = {scenario.scenario_id: scenario for scenario in scenarios}
        self.definitions: dict[str, ToolDefinition] = {
            "search_documentation": ToolDefinition(
                "search_documentation",
                "Search the supplied PDF pages for migration evidence.",
                TOOL_SCHEMAS["search_documentation"],
                self._search_documentation,
            ),
            "inspect_source": ToolDefinition(
                "inspect_source",
                "Read one source PDF page in full.",
                TOOL_SCHEMAS["inspect_source"],
                self._inspect_source,
            ),
            "check_deprecation": ToolDefinition(
                "check_deprecation",
                "Check whether one endpoint parameter is deprecated for a selected API version.",
                TOOL_SCHEMAS["check_deprecation"],
                self._check_deprecation,
            ),
        }

    def tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"name": definition.name, "description": definition.description, "parameters": definition.input_schema}
            for definition in self.definitions.values()
        ]

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.definitions:
            raise SchemaError(f"unknown tool: {name}")
        definition = self.definitions[name]
        _validate_schema(arguments, definition.input_schema)
        return definition.handler(arguments)

    def _search_documentation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        hits = self.corpus.search(
            arguments["query"],
            source_files=arguments.get("source_files"),
            page_numbers=arguments.get("page_numbers"),
            top_k=arguments.get("top_k", 5),
        )
        return {"hits": hits, "count": len(hits)}

    def _inspect_source(self, arguments: dict[str, Any]) -> dict[str, Any]:
        page = self.corpus.read(arguments["source_file"], arguments["page_number"])
        if page is None:
            return {"found": False, "source_file": arguments["source_file"], "page_number": arguments["page_number"]}
        return {"found": True, **page.to_dict()}

    def _check_deprecation(self, arguments: dict[str, Any]) -> dict[str, Any]:
        parameter = arguments["parameter"]
        query = f"{arguments['endpoint']} {parameter} deprecated {arguments['api_version']}"
        hits = self.corpus.search(
            query,
            source_files=["github_combined_reference.pdf"],
            top_k=5,
        )
        candidate = next(
            (hit for hit in hits if parameter.lower() in str(hit.get("text", "")).lower()),
            hits[0] if hits else None,
        )
        text = str(candidate.get("text", "")) if candidate else ""
        lower_text = text.lower()
        deprecated = parameter.lower() in {"assignee", "private"} and parameter.lower() in lower_text and "deprecated" in lower_text
        replacements = {"assignee": "assignees", "private": "visibility"}
        replacement = replacements.get(parameter.lower()) if deprecated else None
        return {
            "api_version": arguments["api_version"],
            "endpoint": arguments["endpoint"],
            "parameter": parameter,
            "deprecated": deprecated,
            "replacement": replacement,
            "source_file": candidate.get("source_file") if candidate else None,
            "page_number": candidate.get("page_number") if candidate else None,
            "evidence": text[:1200],
        }

    def validate_output(self, scenario_id: str, output: dict[str, Any]) -> dict[str, Any]:
        return self._validate_migration({"scenario_id": scenario_id, **output})
    def _validate_migration(self, arguments: dict[str, Any]) -> dict[str, Any]:
        scenario = self.scenarios.get(arguments["scenario_id"])
        if scenario is None:
            return {"valid": False, "reason": "unknown scenario"}
        output = MigrationOutput.from_dict(
            {"answer": arguments["answer"], "steps": arguments["steps"], "citations": arguments["citations"]}
        )
        expected = _concept_tokens(scenario.reference_answer)
        actual = _concept_tokens(output.answer)
        matched = sorted(expected & actual)
        coverage = len(matched) / max(1, len(expected))
        valid_citations = [
            citation
            for citation in output.citations
            if citation.source_file in scenario.source_files
            and citation.page_number in scenario.page_numbers
            and self.corpus.read(citation.source_file, citation.page_number) is not None
        ]
        has_all_sources = all(
            any(item.source_file == source and item.page_number == page for item in valid_citations)
            for source, page in zip(scenario.source_files, scenario.page_numbers)
        )
        # The evidence pages are the source of truth; a migration answer needs
        # enough distinct concepts to avoid passing on a citation-only answer.
        valid = coverage >= 0.25 and len(matched) >= 5 and len(output.steps) >= 2 and bool(valid_citations) and has_all_sources
        return {
            "valid": valid,
            "coverage": round(coverage, 4),
            "matched_concepts": matched,
            "expected_concept_count": len(expected),
            "valid_citation_count": len(valid_citations),
            "required_source_count": len(scenario.source_files),
            "reason": "evidence and migration steps satisfy the validation threshold" if valid else "insufficient evidence, concepts, or citations",
        }
