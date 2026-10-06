#!/usr/bin/env python3
"""Call tools/list on both Medpace toolbox MCP endpoints and compare exposure.

Prints, for each toolbox, the tool names returned by tools/list and the byte size
of the serialized tool schemas. The schema bytes are what a client would have to
put into the model prompt as tool definitions.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API_VERSION = "v1"
TOOLBOXES = ["medpace-study-toolbox-flat", "medpace-study-toolbox"]


def token() -> str:
    return subprocess.run(
        ["az", "account", "get-access-token", "--scope",
         "https://ai.azure.com/.default", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def rpc(url: str, bearer: str, payload: dict, session: str | None):
    headers = {
        "Authorization": f"Bearer {bearer}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session:
        headers["Mcp-Session-Id"] = session
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            sid = resp.headers.get("Mcp-Session-Id")
            # streamable-http may return SSE framing
            if raw.lstrip().startswith("event:") or raw.lstrip().startswith("data:"):
                for line in raw.splitlines():
                    if line.startswith("data:"):
                        return json.loads(line[5:].strip()), sid
                return None, sid
            return (json.loads(raw) if raw.strip() else None), sid
    except urllib.error.HTTPError as exc:
        print(f"  HTTP {exc.code}: {exc.read().decode()[:400]}")
        raise


def list_tools(endpoint: str, toolbox: str, bearer: str):
    url = f"{endpoint}/toolboxes/{toolbox}/mcp?api-version={API_VERSION}"
    init, sid = rpc(url, bearer, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                   "clientInfo": {"name": "medpace-verify", "version": "1.0"}},
    }, None)
    try:
        rpc(url, bearer, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    except Exception:
        pass
    result, _ = rpc(url, bearer, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
    if result and "error" in result:
        raise RuntimeError(
            f"tools/list JSON-RPC error for {toolbox}: "
            f"{json.dumps(result['error'])[:2000]}"
        )
    return url, (result or {}).get("result", {}).get("tools", [])


def main() -> int:
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    bearer = token()
    summary = {}
    for tb in TOOLBOXES:
        print(f"\n=== {tb} ===")
        url, tools = list_tools(endpoint, tb, bearer)
        print(f"url: {url}")
        print(f"tools/list returned {len(tools)} tool(s):")
        for t in tools:
            desc = (t.get("description") or "")
            print(f"  - {t.get('name')}  ({len(desc)} chars desc)")
        schema_bytes = len(json.dumps(tools))
        print(f"serialized tool schema bytes: {schema_bytes}")
        summary[tb] = {"count": len(tools), "bytes": schema_bytes,
                       "names": [t.get("name") for t in tools]}
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
