# Third Tool Description Diff

The first two tools remain single-purpose:

| Tool | Description |
|---|---|
| `search_documentation` | Search the supplied PDF pages for migration evidence. |
| `inspect_source` | Read one source PDF page in full. |

The required third tool is `check_deprecation`:

```diff
- No third tool existed in the original two-tool loop.
+ check_deprecation: Check whether one endpoint parameter is deprecated for a selected API version.
```

Its strict input schema is:

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["api_version", "endpoint", "parameter"],
  "properties": {
    "api_version": {
      "type": "string",
      "enum": ["2022-11-28", "2025-06-01"]
    },
    "endpoint": {"type": "string"},
    "parameter": {"type": "string"}
  }
}
```

The new description names exactly one job: checking deprecation status. It does not search arbitrary documentation, read pages, or validate final answers, so it does not overlap with the other two descriptions.