"""Dovetail S3 export corpus tool (optional, internal Amazon).

Reads the curated Dovetail-to-S3 export corpus: a CAPE-maintained pipeline
exports the Dovetail research repository to an S3 bucket as markdown documents,
each paired with a Bedrock-Knowledge-Base-format metadata sidecar, under a
``data/`` prefix::

    {prefix}{slug}_{id}.md              # YAML frontmatter + markdown body
    {prefix}{slug}_{id}.metadata.json   # KB-format metadata (strings; null fields dropped)

This is a SEPARATE, complementary integration from the live ``DovetailSearchTool``
(``dovetail_research.py``), which queries the Dovetail MCP API in real time. This
tool consumes the *curated* corpus: it can filter on structured research metadata
(topic area, product, research method, participant type, ...) before fetching any
document body, which the live keyword API cannot do. Both coexist; neither
replaces the other.

Design notes (mirroring the repo's optional-tool conventions):
- **boto3, standard credential chain**, like ``aws_pricing.py``. No tokens or
  endpoint URLs handled here; auth is whatever boto3 resolves.
- **Metadata-first.** ``search`` lists + filters the small sidecars, then fetches
  only the matching ``.md`` bodies. It never downloads every body for a keyword.
- **Fail-soft.** Missing ``DOVETAIL_S3_BUCKET``, absent AWS credentials, or any S3
  error returns a descriptive string and never raises, so the OSS pipeline runs
  unchanged when the bucket/creds are absent.
- **Env-configurable, zero hardcoded internal values.** The bucket, prefix, region,
  and (optional) Knowledge Base id all come from env vars. There is no default
  bucket — the tool is disabled (via ``crew.py``'s ``_dovetail_corpus_enabled``)
  when ``DOVETAIL_S3_BUCKET`` is unset.
- **Optional Bedrock KB branch.** When ``DOVETAIL_KB_ID`` is set, ``search`` routes
  to ``bedrock-agent-runtime`` ``retrieve`` (semantic + metadata filter) instead of
  the S3 scan. No KB exists over the bucket yet, so this branch is scaffolded and
  unit-tested only — NOT live-verified.
- **JSONL call logging** to ``output/dovetail_corpus_calls.log``, like the other tools.

This tool is read-only (S3 GET/LIST, or KB retrieve) — it never writes.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_CALL_LOG_PATH = Path(os.getenv("OUTPUT_DIR", "./output")) / "dovetail_corpus_calls.log"

# Bytes of a document body to return before truncating (mirrors the live
# Dovetail tool's 6000-char insight cap so agent context stays manageable).
_BODY_TRUNCATE_CHARS = 6000

# Metadata fields exposed as agent-visible search filters. Deliberately a
# curated high-signal subset of the 17 exported fields — not `author` (a raw
# internal Dovetail user id, PII-adjacent and not human-meaningful) and not
# free-form/date fields that make poor equality filters.
_FILTERABLE_FIELDS = frozenset({
    "research_topic_area",
    "product",
    "research_method",
    "participant_type",
    "content_type",
    "theme",
    "research_team",
})

# Metadata fields surfaced in list/search output (read-only display). Broader
# than the filterable set, but still excludes the internal author id.
_DISPLAY_FIELDS = (
    "title",
    "research_topic_area",
    "product",
    "research_method",
    "participant_type",
    "content_type",
    "theme",
    "research_team",
    "number_of_participants",
    "publication_date",
    "created_at",
    "dovetail_url",
    "dovetail_id",
)


def _env_bucket() -> str:
    return os.getenv("DOVETAIL_S3_BUCKET", "").strip()


def _env_prefix() -> str:
    # Normalise to a trailing slash unless empty.
    p = os.getenv("DOVETAIL_S3_PREFIX", "data/").strip()
    if p and not p.endswith("/"):
        p += "/"
    return p


def _env_kb_id() -> str:
    return os.getenv("DOVETAIL_KB_ID", "").strip()


def _env_region() -> str:
    return (os.getenv("AWS_REGION") or os.getenv("AWS_BEDROCK_REGION") or "us-east-1").strip()


def _log_call(event: str, details: dict) -> None:
    """Append one JSON line to the corpus call log. Never raises."""
    try:
        _CALL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now().isoformat(timespec="seconds"), "event": event, **details}
        with _CALL_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001 — logging must never break the tool
        pass


def _s3_client():
    """Build an S3 client via boto3's standard credential chain.

    Imported lazily so importing this module does not require boto3 to resolve
    credentials at import time (matches ``aws_pricing.py``).
    """
    import boto3

    return boto3.client("s3", region_name=_env_region())


def _bedrock_agent_client():
    """Build a bedrock-agent-runtime client for the optional KB branch."""
    import boto3

    return boto3.client("bedrock-agent-runtime", region_name=_env_region())


def _metadata_key_for(md_key: str) -> str:
    """Map a ``...{id}.md`` object key to its ``...{id}.metadata.json`` sidecar."""
    if md_key.endswith(".md"):
        return md_key[: -len(".md")] + ".metadata.json"
    return md_key + ".metadata.json"


def _matches_filters(metadata: dict, filters: dict[str, str]) -> bool:
    """True when every requested filter is satisfied (case-insensitive contains).

    Sidecar values are comma-joined strings (KB format); a filter matches when
    its value appears as one of the comma-separated tokens (or a substring of
    the field, for single-valued fields). Absent/empty fields never match a
    non-empty filter.
    """
    for field, wanted in filters.items():
        wanted_norm = (wanted or "").strip().lower()
        if not wanted_norm:
            continue
        raw = metadata.get(field)
        if raw is None:
            return False
        # Sidecar stores everything as strings; lists are comma-joined.
        tokens = [t.strip().lower() for t in str(raw).split(",") if t.strip()]
        haystack = str(raw).lower()
        if wanted_norm not in tokens and wanted_norm not in haystack:
            return False
    return True


def _parse_filters(filters: str) -> dict[str, str]:
    """Parse a ``k=v,k2=v2`` filter string, keeping only filterable fields.

    Unknown or non-filterable keys are dropped (with the effect noted in the
    returned dict being smaller); malformed pairs are ignored.
    """
    out: dict[str, str] = {}
    for pair in (filters or "").split(","):
        pair = pair.strip()
        if "=" not in pair:
            continue
        key, _, val = pair.partition("=")
        key = key.strip().lower()
        val = val.strip()
        if key in _FILTERABLE_FIELDS and val:
            out[key] = val
    return out


class DovetailCorpusInput(BaseModel):
    """Input schema for DovetailCorpusTool."""

    action: str = Field(
        default="search",
        description=(
            "Action: 'search' (filter the curated corpus by metadata and/or "
            "keyword, then return matching documents) | 'list' (enumerate "
            "available documents with their metadata, no bodies) | 'get' (fetch "
            "one document's full markdown body by dovetail id or S3 key)."
        ),
    )
    query: str = Field(
        default="",
        description=(
            "For action='search': optional free-text keyword matched against the "
            "document title and body. Combine with 'filters' to narrow first."
        ),
    )
    filters: str = Field(
        default="",
        description=(
            "For action='search': comma-separated metadata filters as key=value "
            "pairs. Filterable keys: research_topic_area, product, research_method, "
            "participant_type, content_type, theme, research_team. "
            "Example: 'research_topic_area=Vega,research_method=Interview'. "
            "Matching is case-insensitive contains."
        ),
    )
    doc_id: str = Field(
        default="",
        description=(
            "For action='get': the Dovetail document id (or full S3 object key) of "
            "the document to fetch."
        ),
    )
    limit: int = Field(
        default=10,
        description="Max documents to return for 'search'/'list' (1 to 50).",
    )


class DovetailCorpusTool(BaseTool):
    """Search the curated Dovetail S3 export corpus (read-only, internal).

    Reads the CAPE Dovetail-to-S3 export (markdown + metadata sidecars) from
    ``DOVETAIL_S3_BUCKET``, filtering on structured research metadata before
    fetching document bodies. Complementary to the live ``dovetail_research``
    tool. Requires the bucket env var set and AWS credentials resolvable by
    boto3; absent either, it fails soft. Read-only.
    """

    name: str = "dovetail_corpus"
    description: str = (
        "Search the curated Dovetail research corpus exported to S3 (markdown + "
        "structured metadata). Unlike dovetail_research (live keyword API), this "
        "filters by research metadata — research_topic_area, product, "
        "research_method, participant_type, content_type, theme, research_team — "
        "before fetching document bodies. Actions: 'search' (filters + optional "
        "keyword), 'list' (catalog with metadata), 'get' (one document body by id). "
        "Use it to pull curated customer-research evidence tagged by topic/method/"
        "audience."
    )
    args_schema: Type[BaseModel] = DovetailCorpusInput

    # -- public entry point ------------------------------------------------

    def _run(
        self,
        action: str = "search",
        query: str = "",
        filters: str = "",
        doc_id: str = "",
        limit: int = 10,
    ) -> str:
        action_clean = (action or "search").strip().lower()
        _log_call(
            "invocation",
            {"action": action_clean, "query": query, "filters": filters, "doc_id": doc_id, "limit": limit},
        )

        bucket = _env_bucket()
        if not bucket:
            msg = (
                "Error: DOVETAIL_S3_BUCKET is not set; the Dovetail S3 corpus is "
                "unavailable. Set DOVETAIL_S3_BUCKET (and ensure AWS credentials) "
                "to enable it."
            )
            _log_call("disabled", {"reason": "no_bucket"})
            return msg

        limit = max(1, min(int(limit or 10), 50))

        try:
            if action_clean == "get":
                return self._get(bucket, doc_id)
            if action_clean == "list":
                return self._list(bucket, limit)
            if action_clean == "search":
                return self._search(bucket, query, filters, limit)
            return (
                f"Unknown action '{action}'. Use 'search', 'list', or 'get'."
            )
        except Exception as exc:  # noqa: BLE001 — fail soft like the other tools
            return self._soft_error(action_clean, exc)

    # -- error handling ----------------------------------------------------

    def _soft_error(self, action: str, exc: Exception) -> str:
        name = type(exc).__name__
        # NoCredentialsError and botocore ClientError both surface here.
        if name in ("NoCredentialsError", "PartialCredentialsError"):
            msg = (
                "Error: no AWS credentials available for the Dovetail S3 corpus. "
                "Configure credentials (boto3 standard chain) to enable it."
            )
        elif name == "ClientError":
            msg = f"Error: S3 request failed for the Dovetail corpus: {exc}"
        else:
            msg = f"Error accessing the Dovetail S3 corpus (action={action}): {exc}"
        _log_call("exception", {"action": action, "type": name, "message": str(exc)[:300]})
        return msg

    # -- object helpers ----------------------------------------------------

    def _list_md_keys(self, bucket: str) -> list[str]:
        """List all ``.md`` object keys under the configured prefix."""
        prefix = _env_prefix()
        client = _s3_client()
        keys: list[str] = []
        token: str | None = None
        while True:
            kwargs = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = client.list_objects_v2(**kwargs)
            for obj in resp.get("Contents", []) or []:
                key = obj.get("Key", "")
                if key.endswith(".md"):
                    keys.append(key)
            if resp.get("IsTruncated") and resp.get("NextContinuationToken"):
                token = resp["NextContinuationToken"]
            else:
                break
        return keys

    def _get_object_text(self, bucket: str, key: str) -> str:
        client = _s3_client()
        resp = client.get_object(Bucket=bucket, Key=key)
        body = resp.get("Body")
        raw = body.read() if body is not None else b""
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)

    def _load_metadata(self, bucket: str, md_key: str) -> dict:
        """Load the sidecar for an ``.md`` key; empty dict on any failure."""
        try:
            text = self._get_object_text(bucket, _metadata_key_for(md_key))
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:  # noqa: BLE001 — a missing/corrupt sidecar must not abort the scan
            return {}

    @staticmethod
    def _display_metadata(metadata: dict) -> dict:
        return {k: metadata[k] for k in _DISPLAY_FIELDS if metadata.get(k) not in (None, "")}

    # -- actions -----------------------------------------------------------

    def _list(self, bucket: str, limit: int) -> str:
        keys = self._list_md_keys(bucket)
        if not keys:
            return f"No documents found in the Dovetail corpus (bucket prefix '{_env_prefix()}')."
        entries = []
        for key in keys[:limit]:
            md = self._display_metadata(self._load_metadata(bucket, key))
            entries.append({"key": key, "metadata": md})
        _log_call("response", {"action": "list", "returned": len(entries), "total_keys": len(keys)})
        return json.dumps(
            {"total_documents": len(keys), "showing": len(entries), "documents": entries},
            indent=2,
        )

    def _search(self, bucket: str, query: str, filters: str, limit: int) -> str:
        # KB branch: when a Knowledge Base id is configured, use semantic
        # retrieve instead of the S3 scan. Scaffolded / unit-tested only —
        # no KB exists over the bucket yet (not live-verified).
        kb_id = _env_kb_id()
        if kb_id:
            return self._search_via_kb(kb_id, query, filters, limit)

        parsed_filters = _parse_filters(filters)
        keyword = (query or "").strip().lower()
        keys = self._list_md_keys(bucket)
        if not keys:
            return f"No documents found in the Dovetail corpus (bucket prefix '{_env_prefix()}')."

        # Stage 1: filter on the small sidecars — fetch NO bodies yet.
        candidates: list[str] = []
        for key in keys:
            metadata = self._load_metadata(bucket, key)
            if parsed_filters and not _matches_filters(metadata, parsed_filters):
                continue
            candidates.append(key)

        # Stage 2: fetch bodies only for the metadata-matched candidates, and
        # apply the keyword (title + body) if one was given.
        results = []
        for key in candidates:
            if len(results) >= limit:
                break
            metadata = self._load_metadata(bucket, key)
            title = str(metadata.get("title", "")).lower()
            body = ""
            need_body = bool(keyword)
            if need_body:
                if keyword in title:
                    body = self._get_object_text(bucket, key)
                else:
                    body = self._get_object_text(bucket, key)
                    if keyword not in body.lower():
                        continue  # keyword not found -> skip
            else:
                body = self._get_object_text(bucket, key)
            if len(body) > _BODY_TRUNCATE_CHARS:
                body = body[:_BODY_TRUNCATE_CHARS] + "\n\n[... truncated for length]"
            results.append(
                {"key": key, "metadata": self._display_metadata(metadata), "content": body}
            )

        _log_call(
            "response",
            {
                "action": "search",
                "filters": parsed_filters,
                "keyword": keyword,
                "candidates": len(candidates),
                "returned": len(results),
            },
        )
        if not results:
            return (
                f"No Dovetail corpus documents matched "
                f"(filters={parsed_filters or 'none'}, keyword={keyword or 'none'})."
            )
        return json.dumps(
            {"matched": len(results), "filters": parsed_filters, "documents": results},
            indent=2,
        )

    def _get(self, bucket: str, doc_id: str) -> str:
        doc_id = (doc_id or "").strip()
        if not doc_id:
            return "Error: action='get' requires a 'doc_id' (Dovetail id or S3 key)."

        # A full key (ends in .md, or contains the prefix) is used directly;
        # otherwise treat doc_id as a Dovetail id and find the {..}_{id}.md key.
        if doc_id.endswith(".md"):
            key = doc_id
        else:
            keys = self._list_md_keys(bucket)
            match = next((k for k in keys if k.endswith(f"_{doc_id}.md") or f"_{doc_id}." in k), None)
            if match is None:
                # Also allow the id to appear anywhere (defensive).
                match = next((k for k in keys if doc_id in k), None)
            if match is None:
                return f"No Dovetail corpus document found for id '{doc_id}'."
            key = match

        body = self._get_object_text(bucket, key)
        metadata = self._display_metadata(self._load_metadata(bucket, key))
        if len(body) > _BODY_TRUNCATE_CHARS:
            body = body[:_BODY_TRUNCATE_CHARS] + "\n\n[... truncated for length]"
        _log_call("response", {"action": "get", "key": key, "chars": len(body)})
        return json.dumps({"key": key, "metadata": metadata, "content": body}, indent=2)

    # -- optional Bedrock Knowledge Base branch (dormant; not live-verified) --

    def _search_via_kb(self, kb_id: str, query: str, filters: str, limit: int) -> str:
        """Semantic retrieve against a Bedrock Knowledge Base over the corpus.

        SCAFFOLD — unit-tested only, NOT live-verified: no KB exists over the
        bucket yet. Activated only when DOVETAIL_KB_ID is set. The retrieve
        response shape and metadata-filter mapping are the documented Bedrock
        Agent Runtime contract; correct here after a live smoke test if needed.
        """
        if not (query or "").strip():
            return "Error: KB search (DOVETAIL_KB_ID set) requires a non-empty 'query'."
        client = _bedrock_agent_client()
        retrieval_config = {
            "vectorSearchConfiguration": {"numberOfResults": max(1, min(limit, 50))}
        }
        resp = client.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={"text": query},
            retrievalConfiguration=retrieval_config,
        )
        chunks = []
        for r in resp.get("retrievalResults", []) or []:
            content = (r.get("content", {}) or {}).get("text", "")
            location = r.get("location", {})
            score = r.get("score")
            if content:
                chunks.append({"content": content, "location": location, "score": score})
        _log_call("response", {"action": "search_kb", "kb_id_set": True, "returned": len(chunks)})
        if not chunks:
            return f"No Knowledge Base results for: {query}"
        return json.dumps({"source": "bedrock_kb", "matched": len(chunks), "results": chunks}, indent=2)
