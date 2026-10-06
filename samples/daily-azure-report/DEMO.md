# Medpace demo — Functions agents runtime + Foundry + Foundry Toolbox tool search

One running app that shows three things together:

1. **Azure Functions agents runtime** — this sample, unchanged in shape. Agents are still `*.agent.md` files in `src/`.
2. **Microsoft Foundry as the model provider** — `gpt-5.4`, Global Standard.
3. **Foundry Toolbox with tool search**, holding an **Azure AI Search** tool, measured side by side against a flat toolbox.

This is an extension of `samples/daily-azure-report`. No second architecture was introduced.

---

## 1. Infra verification (done before any edit)

Modules in `infra/main.bicep` **as shipped**, and what each deploys:

| Module | Deploys |
| --- | --- |
| `monitoring` (`core/monitor/monitoring.bicep`) | Log Analytics workspace + Application Insights |
| `storage` (`core/storage/storage-account.bicep`) | Storage account for AzureWebJobsStorage, deployment container, agent chat history |
| `appServicePlan` (`core/host/appserviceplan.bicep`) | Flex Consumption (FC1) Linux plan |
| `userAssignedIdentity` | User-assigned managed identity for the Function App |
| `foundry` (`app/foundry.bicep`) | Foundry (AIServices) account, project, and the `gpt-5.4` Global Standard deployment |
| `o365Connector` (`app/o365-connector.bicep`) | Connector gateway + Office 365 Outlook connection (the original sample's email step) |
| `api` (`app/api.bicep`) | The Function App itself, app settings, and role assignments |
| `storageRoleAssignments`, `foundryRoleAssignments` | Data-plane RBAC for the function identity |

**Confirmed gaps** (matching the brief): the stock template creates **no Azure AI Search** and **no Foundry Toolbox**. Both were added.

### What was added

| Added | Where | Why |
| --- | --- | --- |
| `search` module | `infra/app/search.bicep` | Azure AI Search, Basic SKU, AAD-only auth, RBAC for the function + operator |
| `searchConnection` module | `infra/app/search-connection.bicep` | Foundry `CognitiveSearch` connection, `authType: AAD` (keyless) — this is what the toolbox tool binds to |
| Toolbox MCP URL app settings + outputs | `infra/main.bicep` | `FOUNDRY_TOOLBOX_MCP_URL`, `FOUNDRY_TOOLBOX_FLAT_MCP_URL` |
| Account/project identity + principal outputs | `infra/app/foundry.bicep` | needed for the role grants |

The **Foundry Toolbox is a data-plane resource and is not expressible in Bicep** at the API version this repo uses. It is created after deploy via the REST API — see §4 for the exact calls.

---

## 2. Region

| Component | Region | Reason |
| --- | --- | --- |
| Functions, Foundry, storage, plan, connector gateway | `eastus2` | The sample's Bicep `@allowed` list excludes Canada. `eastus2` is the sample-sanctioned region for Flex Consumption + `gpt-5.4` Global Standard. |
| Azure AI Search | `canadacentral` | `eastus2` Search returned a hard capacity error (below). Search is reached over public HTTPS and needs no co-location with Foundry, so only this one service moved. |

The original `eastus2` Search failure, verbatim, from deployment `medpace-demo-1791246822`:

```
InsufficientResourcesAvailable: The region 'eastus2' is currently out of the
resources required to provision new services.
```

Canada Central was confirmed to support `Microsoft.Search` with free Basic-SKU quota (0/16 used) before retrying. The region is parameterised, not hard-coded:

```bicep
param searchLocation string = 'canadacentral'   // infra/main.bicep
```
```json
"searchLocation": { "value": "${AZURE_SEARCH_LOCATION=canadacentral}" }
```

---

## 3. Deployed resources

azd environment: **`medpace-demo`**, resource group **`rg-medpace-demo`**, subscription `8fcc5e8e-6540-4288-89e7-849e94290205`.

| Resource | Name | Region |
| --- | --- | --- |
| Function App | `func-agent-func-hbcyongnalrgq` | eastus2 |
| App Service plan (Flex FC1) | `plan-hbcyongnalrgq` | eastus2 |
| Storage | `sthbcyongnalrgq` | eastus2 |
| Foundry account | `cog-hbcyongnalrgq` | eastus2 |
| Foundry project | `cog-hbcyongnalrgq-proj` | eastus2 |
| Model deployment | `gpt-5.4` (Global Standard) | eastus2 |
| **Azure AI Search** | `srch-medpace-hbcyongnalrgq` | **canadacentral** |
| Foundry → Search connection | `medpace-aisearch-conn` (AAD, keyless) | — |
| App Insights / Log Analytics | `appi-hbcyongnalrgq` / `log-hbcyongnalrgq` | eastus2 |
| User-assigned identity | `id-agent-func-hbcyongnalrgq` | eastus2 |
| Connector gateway (stock sample) | `cg-hbcyongnalrgq` | eastus2 |

**Foundry project endpoint**

```
https://cog-hbcyongnalrgq.services.ai.azure.com/api/projects/cog-hbcyongnalrgq-proj
```

**Model:** `gpt-5.4`

### Search index `study-docs`

Fields: `id` (key), `title`, `section`, `content`. Three documents, canary tokens unmodified:

| id | title | section | canary |
| --- | --- | --- | --- |
| `sop-qa-014-4-2` | SOP-QA-014 | 4.2 | `PD-CANARY-4419` |
| `sop-pv-007-3-1` | SOP-PV-007 | 3.1 | `SAE-CANARY-8820` |
| `sop-ops-003-2-4` | SOP-OPS-003 | 2.4 | `VISIT-CANARY-2304` |

---

## 4. The two toolboxes

Both live in the same Foundry project. Created with `scripts/create_toolboxes.py`, which calls:

```
POST  {projectEndpoint}/toolboxes/{name}/versions?api-version=v1      # create a version
PATCH {projectEndpoint}/toolboxes/{name}?api-version=v1               # {"default_version":"4"}
```

Auth scope: `https://ai.azure.com/.default`.

> **The PATCH is required.** Creating a version does *not* move the toolbox's
> `default_version` pointer, and the `/mcp` consumer endpoint always serves the
> default. Skipping it silently serves the previous version.

| | `medpace-study-toolbox-flat` | `medpace-study-toolbox` |
| --- | --- | --- |
| Tool search | **off** | **on** (`{"type":"toolbox_search"}`) |
| Azure AI Search tool `study-doc-search` | present, unpinned | present, **pinned** |
| 8 extra MCP tools (long descriptions) | all exposed | hidden behind `tool_search` |
| Version | 4 (default) | 4 (default) |

**MCP endpoints**

```
flat:        https://cog-hbcyongnalrgq.services.ai.azure.com/api/projects/cog-hbcyongnalrgq-proj/toolboxes/medpace-study-toolbox-flat/mcp?api-version=v1
tool search: https://cog-hbcyongnalrgq.services.ai.azure.com/api/projects/cog-hbcyongnalrgq-proj/toolboxes/medpace-study-toolbox/mcp?api-version=v1
```

### Where the 8 extra tools come from

They are **real, reachable** MCP tools, not placeholders. Foundry enumerates every
registered MCP source live during `tools/list`; unreachable hosts fail the whole
call with JSON-RPC `-32007`. So the filler tools are eight inert
`filler_*.agent.md` agents hosted on **this same Function App**, surfaced through
its own MCP endpoint and registered as one `mcp` tool source (`server_label: medpace_ops`):

```
https://func-agent-func-hbcyongnalrgq.azurewebsites.net/runtime/webhooks/mcp
```

This also satisfies the optional step-4 item: **the Function App MCP endpoint is
registered as a custom MCP tool, and it worked** — no auth blocker. It
authenticates with the `mcp_extension` system key passed as an `x-functions-key`
**header** (a `?code=` query string is rejected with 401). The first-party
Azure Functions queue tool was not used; it is not a toolbox tool type.

### Pinning

Pinning must key on the **exposed tool name**. A `"*"` catch-all pins every tool
in the toolbox and silently defeats tool search (observed: all 10 tools still
listed). The working form:

```json
"tool_configs": {
  "study-doc-search": { "pin": true, "additional_search_text": "protocol deviation important SOP ..." }
}
```

### `tools/list` proof

`scripts/verify_toolboxes.py`, run against both default versions:

| Toolbox | Tools returned | Serialized schema bytes |
| --- | ---: | ---: |
| `medpace-study-toolbox-flat` | **10** | **12,797** |
| `medpace-study-toolbox` | **3** | **2,655** |

Flat returns every schema:

```
medpace_ops___filler_ctms_site_activation   medpace_ops___filler_edc_query_manager
medpace_ops___filler_enrollment_forecast    medpace_ops___filler_ivrs_randomization
medpace_ops___filler_lab_reconciliation     medpace_ops___filler_monitoring_visit
medpace_ops___filler_safety_narrative       medpace_ops___filler_tmf_indexer
medpace_ops___main                          study-doc-search
```

Tool search returns only the entry points plus the pinned tool — **it does not dump every unpinned schema**:

```
tool_search    call_tool    study-doc-search
```

That is a **79% reduction in tool-schema bytes** on the wire (12,797 → 2,655).

---

## 5. Wiring the sample at the toolbox

`src/mcp.json` keeps `microsoft-learn`, keeps the Outlook connector, and adds two
HTTP servers whose URLs come from app settings:

```json
"foundry-toolbox":      { "type": "http", "url": "${FOUNDRY_TOOLBOX_MCP_URL}",      "auth": { "scope": "https://ai.azure.com/.default" } },
"foundry-toolbox-flat": { "type": "http", "url": "${FOUNDRY_TOOLBOX_FLAT_MCP_URL}", "auth": { "scope": "https://ai.azure.com/.default" } }
```

Neither demo agent depends on Outlook.

### Keeping the comparison honest

Agents inherit **all** servers in `mcp.json` and can only filter with `mcp.exclude`
(there is no include-list). So **both** agents exclude `microsoft-learn` and
`office365-outlook`, and each excludes the other's toolbox. Both set
`tools: false` and `skills: false`. **The toolbox is the only variable.**

The instruction bodies of `src/study_assistant.agent.md` and
`src/study_assistant_flat.agent.md` are **byte-identical (823 bytes)**, verified with `diff`.
They differ only in the frontmatter `mcp.exclude` list.

> Any name listed in `mcp.exclude` must resolve to a server that actually loaded,
> otherwise the worker raises `ValueError: Unknown MCP server reference` and the
> host returns 503 with 0 functions.

**Chat URLs**

```
tool search:  https://func-agent-func-hbcyongnalrgq.azurewebsites.net/agents/study_assistant/
flat:         https://func-agent-func-hbcyongnalrgq.azurewebsites.net/agents/study_assistant_flat/
```

Chat API is `POST .../agents/{name}/chat` with body `{"prompt": "..."}` and a
function key header. Both endpoints use function-level auth; no keys are printed here.

Role grant (step 7): the function's user-assigned identity holds **Foundry User**
on the project so it can call the toolbox. In this tenant the roles are named
**Foundry User** / **Foundry Project Manager** — not "Azure AI User". RBAC took
~100 s to propagate.

### Foundry-native prompt agent

A separate prompt agent was created in the same Foundry project for use from the
Foundry portal:

| Property | Value |
| --- | --- |
| Agent | `medpace-study-assistant` |
| Agent version | `1` (`active`) |
| Definition kind | `prompt` |
| Model | `gpt-5.4` |
| MCP server label | `medpace-study-toolbox` |
| MCP endpoint | the unversioned `medpace-study-toolbox` consumer endpoint |
| Tool approval | `never` |
| Endpoint protocol | Responses |
| Endpoint authorization | Microsoft Entra |
| Agent identity principal ID | `23fffb69-5bee-48b3-b531-c7142f0d9e0d` |

The toolbox was explicitly added as an MCP tool in the agent definition; it is
**not** inherited automatically merely because the agent and toolbox are in the
same project. The agent identity has **Foundry User** on the project and
**Search Index Data Reader** on `srch-medpace-hbcyongnalrgq`.

The verification request was sent to:

```text
POST {FOUNDRY_PROJECT_ENDPOINT}/agents/medpace-study-assistant/endpoint/protocols/openai/responses?api-version=v1
```

It completed successfully as response
`resp_0e871a4d7fb28129006ac45d20c2008195b473710b1a19564a`, enumerated only
`tool_search`, `call_tool`, and the pinned `study-doc-search`, then called
`study-doc-search`. The final answer cited SOP-QA-014 §4.2 and contained
`Provenance: PD-CANARY-4419` (1,546 input tokens, 151 output tokens).

### Foundry-native flat-toolbox prompt agent

A second Foundry prompt agent was created for the control arm:

| Property | Value |
| --- | --- |
| Agent | `medpace-study-assistant-flat` |
| Agent version | `1` (`active`) |
| Definition kind | `prompt` |
| Model | `gpt-5.4` |
| MCP server label | `medpace-study-toolbox-flat` |
| MCP endpoint | the unversioned `medpace-study-toolbox-flat` consumer endpoint |
| Tool approval | `never` |
| Endpoint protocol | Responses |
| Endpoint authorization | Microsoft Entra |
| Agent identity principal ID | `2aba8f9e-bafa-48c2-a23c-7972efc5ec15` |

This agent is configured with the flat toolbox, so its MCP `tools/list` response
contains the full tool inventory and does **not** include the `tool_search` or
`call_tool` tool-search entry points. Its identity has **Foundry User** on the
project and **Search Index Data Reader** on `srch-medpace-hbcyongnalrgq`.

Verification response:

```text
POST {FOUNDRY_PROJECT_ENDPOINT}/agents/medpace-study-assistant-flat/endpoint/protocols/openai/responses?api-version=v1
```

The request completed successfully, called `study-doc-search` through
`medpace-study-toolbox-flat`, cited SOP-QA-014 §4.2, and contained
`Provenance: PD-CANARY-4419`. The verified response
`resp_0acb40b838d16ba2006ac45f39c8c0819791591acba87f93aa` used 2,259 input
tokens and 154 output tokens. Its `mcp_list_tools` trace contained all 10 flat
tool schemas and contained neither `tool_search` nor `call_tool`; its
`mcp_call` trace invoked `study-doc-search` through
`medpace-study-toolbox-flat`.

The sanitized live `GET` definition, RBAC check, toolbox inventory, and response
trace are retained in
`verification/medpace-study-assistant-flat.json`.

---

## 6. Canary check — both arms

Question, identical for both:

> What has to be documented before a protocol deviation is classified as important?

| Agent | HTTP | Tool actually called | Cites | `PD-CANARY-4419` |
| --- | --- | --- | --- | --- |
| `study_assistant_flat` | 200 (7.7 s) | `study-doc-search` | SOP-QA-014 §4.2 | **yes** |
| `study_assistant` | 200 (14.4 s) | `study-doc-search` | SOP-QA-014 §4.2 | **yes** |

Both returned the four required elements — visit, protocol section, impact on
subject safety and data integrity, investigator acknowledgement — and echoed
`Provenance: PD-CANARY-4419`. The canary is the proof the answer came from the
Search index rather than model memory.

---

## 7. Token comparison

Measured from the run traces (`agent_token_usage`, App Insights `appi-hbcyongnalrgq`),
same question, same model, same instructions, back to back on a warm host.

| | Flat toolbox (`study_assistant_flat`) | Tool search (`study_assistant`) | Delta |
| --- | ---: | ---: | ---: |
| Tool schemas sent on `tools/list` | **10** | **3** | −7 |
| Tool-schema bytes | **12,797** | **2,655** | −79% |
| **Input tokens** | **3,279** | **1,885** | **−1,394 (−42.5%)** |
| Output tokens | 174 | 183 | +9 |
| Model | gpt-5.4 | gpt-5.4 | — |

### What this does and does not claim

- **The claim:** the tool-search run sent **fewer input tokens because the seven
  unused tool definitions were never placed in the prompt**. With tool search on,
  the model sees `tool_search`, `call_tool`, and the one pinned `study-doc-search`
  schema; the rest stay behind `tool_search` until something asks for them.
- **Not a caching claim.** Nothing here asserts the SOP text or the Azure AI Search
  result was cached. Both runs performed a live `study-doc-search` call and both
  received the same three documents. The saving is unsent tool schemas, nothing else.
- Output tokens are essentially unchanged (174 vs 183), as expected — the answer is
  the same; only the prompt's tool-schema overhead differs.
- The delta scales with the number of unused tools. Eight filler tools is a small
  catalogue; a real Medpace tool estate would widen the gap.

---

## 8. Reproducing

```bash
cd samples/daily-azure-report

azd env new medpace-demo
azd env set AZURE_LOCATION eastus2
azd env set AZURE_SEARCH_LOCATION canadacentral
azd env set TO_EMAIL demo@contoso.com
azd up

# index + canary documents
python3 scripts/seed_search.py

# both toolboxes (also PATCHes default_version)
export FOUNDRY_PROJECT_ENDPOINT=$(azd env get-value FOUNDRY_PROJECT_ENDPOINT)
export AZURE_FUNCTION_NAME=$(azd env get-value AZURE_FUNCTION_NAME)
export FUNCTION_MCP_KEY=...   # mcp_extension system key, via ARM listkeys
python3 scripts/create_toolboxes.py

# proof that tool search hides unpinned schemas
python3 scripts/verify_toolboxes.py

azd deploy
```

### Operational notes

- **Cold start exceeds the gateway timeout.** The plan scales to zero and drains
  right after each run, so the first POST after idle or after `azd deploy` returns
  **504 at ~240 s** while the run itself still completes server-side. Warm the host
  with a cheap `GET /agents/{name}/` first; both measured runs then completed in
  7–15 s. For a live demo, pre-warm or configure always-ready instances.
- **Deployment requirement.** The sample's `src/requirements.txt` ships an editable
  install (`-e ../../..[monitor]`) that Oryx cannot build. It is pinned to
  `azurefunctions-agents-runtime[monitor]==0.1.0b16`, the exact version of the
  local source tree.
- Toolbox tool types accepted: `azure_ai_search`, `mcp`, `toolbox_search`,
  `work_iq_preview`, `web_search`, `code_interpreter`, `file_search`. There is no
  inline `function` type — it is rejected with `Unknown ToolboxToolType`.

No secrets, storage keys, or function keys appear in this document.
