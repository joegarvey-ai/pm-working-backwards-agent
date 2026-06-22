# Dovetail Full-Content Export to S3: High-Level Path to Green

**Audience:** Engineer exploring how to pull full Dovetail research content into S3 for internal agent consumption.
**Status:** Advisory. No code committed yet.
**Date:** 2026-04-29

## TL;DR

You are likely calling the Dovetail **MCP endpoint** (`https://dovetail.com/api/mcp`), which returns titles and IDs for search results and requires follow-up calls per item to get content. That is the correct design for agent-time retrieval, but it is the wrong tool for bulk export.

For the S3 export use case, switch to Dovetail's **REST API** at `https://dovetail.com/api/v1/`. It exposes dedicated `/export/{markdown|html}` endpoints that return full body content, supports `offset`/`limit` pagination up to 250 per page, and accepts the same Personal API Token via `Authorization: Bearer <token>`. No new credentials required.

## Why you're seeing titles and metadata only

The Dovetail MCP server exposes these tools:

| MCP tool | Returns |
|---|---|
| `search_workspace` | Titles, IDs, project IDs. No body content. |
| `list_project_insights` | Insight titles and IDs. No content. |
| `get_project_highlights` | Quote text inline. |
| `get_insight_content` | Full insight markdown. Requires `insight_id`. |
| `get_data_content` | Full data entry content (transcript, survey response). Requires `data_id`. |

Search-like calls return metadata by design. To get bodies, you chain: search then list then fetch-per-item. The existing `DovetailSearchTool` in this repo does this via its `deep_search` action (see `src/pm_agent_system/tools/dovetail_research.py`). It works, but:

- MCP responses are capped (~10 items per search) and truncated for long insights (this repo cuts at 6000 chars)
- Three round trips per insight is slow for bulk
- MCP is optimized for LLM tool-calling, not paginated export

For "export everything to S3," the REST API is the right surface.

## Dovetail REST API: the endpoints that matter

Base URL: `https://dovetail.com/api/v1/`
Auth: `Authorization: Bearer <DOVETAIL_API_TOKEN>` (same Personal API Token already in `.env`)

Key references:

- [Introduction](https://developers.dovetail.com/docs/introduction)
- [Authorization](https://developers.dovetail.com/docs/authorization)
- [List data](https://developers.dovetail.com/reference/get_v1-data) (paginated list of data entries)
- [Export data](https://developers.dovetail.com/reference/get_v1-data-data-id-export-type) (`/v1/data/{id}/export/{markdown|html}`)
- [List notes](https://developers.dovetail.com/reference/get_v1-notes)
- [Export note](https://developers.dovetail.com/reference/get_v1-notes-note-id-export-type)
- [List highlights](https://developers.dovetail.com/reference/get_v1-highlights) (tagged customer quotes, rich list response)
- [Export doc](https://developers.dovetail.com/reference/get_v1-docs-doc-id-export-type) (insights are now "docs")
- [Magic Search](https://developers.dovetail.com/reference/post_v1-search)

Pattern: list endpoint (paginate), then for each item call `/export/markdown`, then write to S3.

Content was rephrased for compliance with licensing restrictions.

## Recommended architecture

### Runtime

Python 3.11+, `httpx`, `tenacity` for retry. Run as:

- **Scheduled Lambda** triggered by EventBridge cron (daily or hourly). Lambda fits if a full sync completes under 15 minutes.
- **ECS Fargate task** for longer-running backfills or large workspaces.

### S3 layout

```
s3://<bucket>/dovetail/<workspace-slug>/
  data/<data_id>.md            # transcripts, survey responses, raw entries
  notes/<note_id>.md           # documents within projects
  docs/<doc_id>.md             # published insights (renamed to "docs" in the v1 API)
  highlights/<yyyy-mm-dd>.jsonl  # highlights are rich enough in list form; no /export needed
  manifest/<run-timestamp>.json  # index: IDs, titles, tags, updated_at, s3_key
```

Rationale:
- One object per entity keeps S3 `GetObject` cheap for downstream agents
- Markdown (not HTML) keeps it LLM-friendly
- JSONL for highlights since they are small and benefit from line-oriented consumption
- Manifest gives downstream systems an index without having to `ListObjects`

### Incremental sync

Store a checkpoint in DynamoDB:

- Partition key: `workspace#resource_type` (e.g., `acme#data`)
- Sort key: `resource_id`
- Attributes: `updated_at`, `s3_key`, `content_hash`, `last_exported_at`

On each run, compare each item's `updated_at` from the list response against the checkpoint. Only re-export changed items. First run is a full backfill; subsequent runs finish in minutes.

### Rate limits and concurrency

Dovetail rate-limits the REST API. Keep it boring:

- `tenacity` with exponential backoff on 429 and 5xx (same pattern as the existing `_dovetail_post_with_retry` in `src/pm_agent_system/tools/dovetail_research.py`)
- `asyncio.Semaphore(5..10)` to bound concurrent exports per worker
- Retry budget capped (e.g., 3 attempts) so a broken item does not stall the run

### Downstream agent integration

Once content is in S3 as Markdown, downstream agents have two easy paths:

1. **Bedrock Knowledge Base** pointed at the S3 prefix. Handles chunking, embeddings, and vector search automatically. Best for semantic retrieval ("find customer evidence about onboarding friction").
2. **Direct `GetObject` by key** using the manifest as an index. Best for deterministic lookups by ID.

For event-driven pipelines: S3 `ObjectCreated` then EventBridge then downstream consumer (Lambda, SQS, or SNS fan-out).

## Credentials and governance (flag before going to prod)

Personal API Tokens inherit the user's workspace permissions. That is fine for a prototype and may be fine for an internal pilot, but for a shared export bucket:

- If the token owner leaves or rotates the token, the export breaks silently. Put the token in AWS Secrets Manager, not just `.env`, and alarm on auth failures.
- Workspace content in S3 should use KMS encryption at rest, a bucket policy that blocks public access, and a narrow IAM policy on consumers.
- Ask Dovetail support about a service-account-style token or OAuth client credentials for a longer-term setup. See [OAuth 2.0](https://developers.dovetail.com/docs/oauth-2).

## Reuse from this repo

- **Auth header pattern** and **retry decorator**: lift from `src/pm_agent_system/tools/dovetail_research.py` (`_get_headers`, `_dovetail_post_with_retry`)
- **`.env` loader pattern**: already handles `DOVETAIL_API_TOKEN` being unset gracefully

The exporter should live in its own module or repo, not inside the CrewAI `tools/` directory. Different lifecycle (scheduled job vs. agent tool), different deploy target (Lambda/ECS vs. local CLI).

## Suggested path to first working export

1. **Validate REST access.** Run a one-off script that hits `GET /v1/data?limit=5` with the Personal API Token and confirms 200 responses. Takes 15 minutes.
2. **Single-project proof.** Export one project's data entries and docs as Markdown to a local folder. Validates pagination, the `/export/markdown` endpoint, and content quality.
3. **Write to S3.** Same script, swap local write for `boto3.put_object`. Add the manifest file.
4. **Add incremental sync.** Introduce the DynamoDB checkpoint table.
5. **Deploy.** Wrap in Lambda + EventBridge schedule, or ECS Fargate if runs exceed 15 minutes.
6. **Wire downstream.** Point a Bedrock Knowledge Base at the S3 prefix, or have other agents read from the manifest.

## Open questions worth answering early

- How large is the workspace? (Item counts determine Lambda vs. ECS and whether Knowledge Base ingestion fits under its file limits.)
- Which resource types matter? (Data entries and docs are the highest-signal; highlights are gold for customer quotes; notes may or may not be relevant depending on how the team uses Dovetail.)
- What refresh cadence? (Daily is typically enough. Hourly if agents need near-real-time evidence.)
- Who owns the bucket and the IAM policies? (Security review gate before anything touches production.)

## References

- [Dovetail API Introduction](https://developers.dovetail.com/docs/introduction)
- [Authorization](https://developers.dovetail.com/docs/authorization)
- [Existing MCP tool in this repo](../../src/pm_agent_system/tools/dovetail_research.py)
- [Deep test script showing MCP chaining](../../scripts/dovetail_deep_test.py)
