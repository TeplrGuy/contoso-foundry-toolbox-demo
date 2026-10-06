#!/usr/bin/env python3
"""Create the two Medpace demo toolboxes in the Foundry project.

Both toolboxes contain the SAME tool inventory (one Azure AI Search tool over the
`study-docs` index plus eight dummy MCP tools with long descriptions). The ONLY
difference is that `medpace-study-toolbox` adds a {"type": "toolbox_search"}
entry and pins the study-doc search tool, so `tools/list` returns the two
meta-tools plus the pinned tool instead of every schema.

Usage:
    python create_toolboxes.py            # create/update both toolboxes
    python create_toolboxes.py --print    # dump payloads without calling Azure
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API_VERSION = "v1"
SEARCH_TOOL_NAME = "study-doc-search"

FLAT_TOOLBOX = "medpace-study-toolbox-flat"
SEARCH_TOOLBOX = "medpace-study-toolbox"

# The eight filler tools are defined as inert agents in src/filler_*.agent.md and
# served through this sample's own Function App MCP endpoint. See dummy_mcp_tools().


def search_tool(connection_id: str, index_name: str, pin: bool) -> dict:
    tool = {
        "type": "azure_ai_search",
        "name": SEARCH_TOOL_NAME,
        "description": (
            "Searches Medpace clinical study documents and standard operating procedures "
            "(SOPs) for protocol rules, deviation handling, safety reporting timelines and "
            "visit windows. Returns the document title, section and content."
        ),
        "azure_ai_search": {
            "indexes": [
                {
                    "project_connection_id": connection_id,
                    "index_name": index_name,
                    "query_type": "simple",
                    "top_k": 3,
                }
            ]
        },
    }
    if pin:
        # Pin by explicit tool name. A "*" catch-all key pins every tool in the
        # toolbox, which defeats tool search, so the key must be the exposed
        # tool name.
        tool["tool_configs"] = {
            SEARCH_TOOL_NAME: {
                "pin": True,
                "additional_search_text": (
                    "protocol deviation important SOP study document section visit "
                    "safety reporting timeline"
                ),
            }
        }
    return tool


def dummy_mcp_tools() -> list:
    """The eight filler tools are served by this sample's own Function App MCP
    endpoint. Foundry enumerates every registered MCP source at tools/list time,
    so the source must be live and DNS-resolvable; unreachable placeholder hosts
    fail the whole tools/list call.
    """
    server_url = os.environ.get("FUNCTION_MCP_URL") or (
        f"https://{os.environ['AZURE_FUNCTION_NAME']}.azurewebsites.net/runtime/webhooks/mcp"
    )
    if not server_url.startswith("https://"):
        raise SystemExit(f"FUNCTION_MCP_URL must be an https URL, got: {server_url!r}")
    key = os.environ["FUNCTION_MCP_KEY"]
    return [
        {
            "type": "mcp",
            "name": "medpace-ops-tools",
            "description": (
                "Medpace clinical operations tool server. Exposes EDC query management, "
                "CTMS site activation, IVRS randomization, safety narrative drafting, "
                "lab result reconciliation, TMF document indexing, monitoring visit "
                "reporting and enrolment forecasting."
            ),
            "server_label": "medpace_ops",
            "server_url": server_url,
            "require_approval": "never",
            "headers": {"x-functions-key": key},
        }
    ]


def build_payloads(connection_id: str, index_name: str) -> dict:
    flat = {
        "description": "Flat toolbox: tool search OFF, every tool schema returned by tools/list.",
        "tools": [search_tool(connection_id, index_name, pin=False)] + dummy_mcp_tools(),
    }
    toolsearch = {
        "description": "Tool search ON: only the study-doc search tool is pinned; the rest are hidden behind tool_search/call_tool.",
        "tools": [
            {"type": "toolbox_search"},
            search_tool(connection_id, index_name, pin=True),
        ]
        + dummy_mcp_tools(),
    }
    return {FLAT_TOOLBOX: flat, SEARCH_TOOLBOX: toolsearch}


def token() -> str:
    return subprocess.run(
        ["az", "account", "get-access-token", "--scope",
         "https://ai.azure.com/.default", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def post_version(endpoint: str, name: str, payload: dict, bearer: str) -> dict:
    url = f"{endpoint}/toolboxes/{name}/versions?api-version={API_VERSION}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        raise SystemExit(f"FAILED creating {name}: HTTP {exc.code}\n{body}") from exc


def patch_default_version(endpoint: str, name: str, version: str, bearer: str) -> None:
    """Point the consumer MCP endpoint at the version just created.

    Creating a version does NOT move the toolbox's default_version pointer, so
    without this the /mcp endpoint keeps serving the previous version.
    """
    url = f"{endpoint}/toolboxes/{name}?api-version={API_VERSION}"
    req = urllib.request.Request(
        url,
        data=json.dumps({"default_version": str(version)}).encode(),
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
        method="PATCH",
    )
    with urllib.request.urlopen(req) as resp:
        resp.read()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print", action="store_true", dest="print_only")
    args = parser.parse_args()

    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    connection_id = os.environ.get("FOUNDRY_SEARCH_CONNECTION_NAME", "medpace-aisearch-conn")
    index_name = os.environ.get("AZURE_SEARCH_INDEX", "study-docs")

    payloads = build_payloads(connection_id, index_name)

    if args.print_only:
        print(json.dumps(payloads, indent=2))
        return 0

    bearer = token()
    for name, payload in payloads.items():
        result = post_version(endpoint, name, payload, bearer)
        version = result.get("version")
        patch_default_version(endpoint, name, version, bearer)
        print(f"{name}: version={version} (default) tools={len(result.get('tools', []))}")
        print(f"  mcp url: {endpoint}/toolboxes/{name}/mcp?api-version={API_VERSION}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
