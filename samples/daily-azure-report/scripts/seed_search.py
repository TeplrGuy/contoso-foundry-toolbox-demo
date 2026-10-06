#!/usr/bin/env python3
"""Create the study-docs index and upload the three canary SOP documents.

Uses AAD (the Search service is configured for role-based auth only, no keys).
Requires AZURE_SEARCH_ENDPOINT; falls back to AZURE_SEARCH_SERVICE_NAME.

    export AZURE_SEARCH_ENDPOINT=$(azd env get-value AZURE_SEARCH_ENDPOINT)
    python3 scripts/seed_search.py
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

API_VERSION = "2024-07-01"
INDEX = os.environ.get("AZURE_SEARCH_INDEX", "study-docs")

INDEX_DEF = {
    "name": INDEX,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
        {"name": "title", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "section", "type": "Edm.String", "searchable": True, "filterable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
    ],
}

# Canary tokens are load-bearing: they prove an answer came from the index
# rather than from model memory. Do not edit them.
DOCS = [
    {
        "id": "sop-qa-014-4-2",
        "title": "SOP-QA-014",
        "section": "4.2",
        "content": (
            "PD-CANARY-4419. Before a protocol deviation can be classified as important, "
            "the study team must document the visit at which the deviation occurred, the "
            "specific protocol section that was deviated from, the impact of the deviation "
            "on subject safety and data integrity, and the investigator acknowledgement of "
            "the deviation. All four elements must be recorded before the deviation is "
            "classified as important.\n"
        ),
    },
    {
        "id": "sop-pv-007-3-1",
        "title": "SOP-PV-007",
        "section": "3.1",
        "content": (
            "SAE-CANARY-8820. A serious adverse event must be reported within 24 hours of "
            "the site becoming aware of the event. The written follow-up report is due "
            "within 5 calendar days.\n"
        ),
    },
    {
        "id": "sop-ops-003-2-4",
        "title": "SOP-OPS-003",
        "section": "2.4",
        "content": (
            "VISIT-CANARY-2304. Visit 1 screening procedures must be completed within 14 "
            "days before the first dose of study drug.\n"
        ),
    },
]


def token() -> str:
    out = subprocess.run(
        ["az", "account", "get-access-token", "--scope",
         "https://search.azure.com/.default", "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True,
    )
    return out.stdout.strip()


def request(method: str, url: str, bearer: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()[:600]}", file=sys.stderr)
        raise


def main() -> int:
    endpoint = os.environ.get("AZURE_SEARCH_ENDPOINT")
    if not endpoint:
        name = os.environ.get("AZURE_SEARCH_SERVICE_NAME")
        if not name:
            raise SystemExit("Set AZURE_SEARCH_ENDPOINT or AZURE_SEARCH_SERVICE_NAME")
        endpoint = f"https://{name}.search.windows.net"
    endpoint = endpoint.rstrip("/")
    bearer = token()

    # PUT is idempotent, so re-running the script is safe.
    request("PUT", f"{endpoint}/indexes/{INDEX}?api-version={API_VERSION}", bearer, INDEX_DEF)
    print(f"index '{INDEX}' created/updated")

    payload = {"value": [dict(d, **{"@search.action": "mergeOrUpload"}) for d in DOCS]}
    result = request(
        "POST", f"{endpoint}/indexes/{INDEX}/docs/index?api-version={API_VERSION}",
        bearer, payload,
    )
    for item in (result or {}).get("value", []):
        print(f"  {item.get('key')}: status={item.get('status')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
