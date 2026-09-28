"""MCP server two: a deliberately local package-registry fixture."""

from __future__ import annotations

from mcp.mcp_protocol import serve


TOOLS = [
    {
        "name": "lookup_package_version",
        "description": "Return version metadata and release date for a package.",
        "inputSchema": {"type": "object", "required": ["package"], "properties": {"package": {"type": "string"}}},
    },
    {
        "name": "get_deprecation_notice",
        "description": "Return deprecation notices and migration guidance for a package version.",
        "inputSchema": {"type": "object", "required": ["package", "version"], "properties": {"package": {"type": "string"}, "version": {"type": "string"}}},
    },
]

REGISTRY = {
    "requests": {"latest": "2.32.5", "released": "2025-08-18", "deprecated": {"2.25": "Upgrade to 2.32.x; urllib3 compatibility fixes are included."}},
    "acme-sdk": {"latest": "3.2.0", "released": "2026-01-15", "deprecated": {"2.0": "Use the v3 migration guide and replace ClientV2 with Client."}},
}


def lookup_package_version(arguments: dict[str, str]) -> dict[str, object]:
    package = arguments.get("package", "")
    item = REGISTRY.get(package)
    if not item:
        return {"isError": True, "content": [{"type": "text", "text": f"No registry record for {package}"}]}
    return {"content": [{"type": "text", "text": str({"package": package, **item, "source": "internal package registry fixture"})}]}


def get_deprecation_notice(arguments: dict[str, str]) -> dict[str, object]:
    package = arguments.get("package", "")
    version = arguments.get("version", "")
    item = REGISTRY.get(package)
    if not item:
        return {"isError": True, "content": [{"type": "text", "text": f"Package {package} is not in the registry; verify the package name."}]}
    notice = item["deprecated"].get(version)
    if notice:
        return {"content": [{"type": "text", "text": str({"package": package, "version": version, "deprecated": True, "notice": notice})}]}
    # Recoverable error: distinguish an unknown version from an unavailable registry.
    return {"isError": True, "content": [{"type": "text", "text": f"No deprecation record for {package} {version}; latest published is {item['latest']}. Ask for a valid version or use the latest release."}]}


if __name__ == "__main__":
    serve("package-registry", "1.0.0", TOOLS, {"lookup_package_version": lookup_package_version, "get_deprecation_notice": get_deprecation_notice})
