"""Unit tests for DovetailCorpusTool.

The tool reads the curated Dovetail-to-S3 export via boto3. These tests mock
the S3 client (and, for the KB branch, the bedrock-agent-runtime client) with a
tiny synthetic corpus of PLACEHOLDER documents — no real bucket, ids, titles,
or research content. No network or AWS credentials are touched.

Metadata-first is the key property: a filtered `search` must fetch document
bodies ONLY for the metadata-matched candidates, never for the whole corpus.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest

from pm_agent_system.tools import dovetail_corpus as dc
from pm_agent_system.tools.dovetail_corpus import DovetailCorpusTool


# ---------------------------------------------------------------------------
# Synthetic placeholder corpus (bucket prefix "data/")
# ---------------------------------------------------------------------------
# 3 docs. Sidecars use the KB format (comma-joined string lists). Bodies are
# markdown with frontmatter. All ids/titles are obvious placeholders.
_CORPUS = {
    "data/alpha_ID001.md": (
        "---\ntitle: Alpha Report\n---\n\nAlpha body about vega tooling.\n"
    ),
    "data/alpha_ID001.metadata.json": json.dumps({
        "title": "Alpha Report",
        "research_topic_area": "Vega, Tooling",
        "research_method": "Interview",
        "participant_type": "External developer",
        "number_of_participants": "8",
        "dovetail_id": "ID001",
        "author": "internal-user-id-should-not-surface-as-filter",
    }),
    "data/beta_ID002.md": (
        "---\ntitle: Beta Survey\n---\n\nBeta body about pricing feedback.\n"
    ),
    "data/beta_ID002.metadata.json": json.dumps({
        "title": "Beta Survey",
        "research_topic_area": "Pricing",
        "research_method": "Survey",
        "participant_type": "Internal user",
        "dovetail_id": "ID002",
    }),
    "data/gamma_ID003.md": (
        "---\ntitle: Gamma Study\n---\n\nGamma body about vega onboarding.\n"
    ),
    "data/gamma_ID003.metadata.json": json.dumps({
        "title": "Gamma Study",
        "research_topic_area": "Vega",
        "research_method": "Interview",
        "participant_type": "External developer",
        "dovetail_id": "ID003",
    }),
}


class _FakeS3:
    """Minimal S3 client stub over the synthetic corpus. Records GET keys."""

    def __init__(self, store: dict[str, str]):
        self.store = store
        self.get_keys: list[str] = []

    def list_objects_v2(self, **kwargs):
        prefix = kwargs.get("Prefix", "")
        contents = [{"Key": k} for k in sorted(self.store) if k.startswith(prefix)]
        return {"Contents": contents, "IsTruncated": False}

    def get_object(self, Bucket=None, Key=None):
        self.get_keys.append(Key)
        if Key not in self.store:
            # Mimic botocore's behavior: raise for a missing key.
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.store[Key].encode("utf-8"))}


@pytest.fixture
def bucket_env(monkeypatch):
    monkeypatch.setenv("DOVETAIL_S3_BUCKET", "placeholder-bucket")
    monkeypatch.setenv("DOVETAIL_S3_PREFIX", "data/")
    monkeypatch.delenv("DOVETAIL_KB_ID", raising=False)


@pytest.fixture
def fake_s3(monkeypatch):
    client = _FakeS3(dict(_CORPUS))
    monkeypatch.setattr(dc, "_s3_client", lambda: client)
    return client


# ---------------------------------------------------------------------------
# Gating / fail-soft
# ---------------------------------------------------------------------------
class TestFailSoft:
    def test_missing_bucket_returns_error_never_raises(self, monkeypatch):
        monkeypatch.delenv("DOVETAIL_S3_BUCKET", raising=False)
        out = DovetailCorpusTool()._run(action="search", query="x")
        assert isinstance(out, str)
        assert "DOVETAIL_S3_BUCKET" in out

    def test_no_credentials_fails_soft(self, bucket_env, monkeypatch):
        class _NoCreds(Exception):
            pass
        _NoCreds.__name__ = "NoCredentialsError"

        def boom():
            raise _NoCreds("no creds")

        monkeypatch.setattr(dc, "_s3_client", lambda: (_ for _ in ()).throw(_NoCreds("no creds")))
        out = DovetailCorpusTool()._run(action="list")
        assert isinstance(out, str)
        assert "credential" in out.lower()

    def test_unknown_action(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="delete", query="x")
        assert "unknown action" in out.lower()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------
class TestList:
    def test_list_returns_titles_and_metadata_no_bodies(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="list", limit=10)
        data = json.loads(out)
        assert data["total_documents"] == 3
        titles = {d["metadata"]["title"] for d in data["documents"]}
        assert titles == {"Alpha Report", "Beta Survey", "Gamma Study"}
        # list reads only sidecars, never the .md bodies.
        assert not any(k.endswith(".md") for k in fake_s3.get_keys)

    def test_list_never_surfaces_author_field(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="list", limit=10)
        assert "author" not in out
        assert "internal-user-id" not in out


# ---------------------------------------------------------------------------
# search — metadata-first
# ---------------------------------------------------------------------------
class TestSearch:
    def test_metadata_filter_matches_only_matching_docs(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(
            action="search", filters="research_topic_area=Vega", limit=10
        )
        data = json.loads(out)
        titles = {d["metadata"]["title"] for d in data["documents"]}
        # Alpha ("Vega, Tooling") and Gamma ("Vega") match; Beta ("Pricing") does not.
        assert titles == {"Alpha Report", "Gamma Study"}

    def test_bodies_fetched_only_for_matched_candidates(self, bucket_env, fake_s3):
        DovetailCorpusTool()._run(
            action="search", filters="research_topic_area=Pricing", limit=10
        )
        # Only Beta matched the metadata filter, so only Beta's body may be GET'd.
        body_gets = [k for k in fake_s3.get_keys if k.endswith(".md")]
        assert body_gets == ["data/beta_ID002.md"]
        assert "data/alpha_ID001.md" not in body_gets
        assert "data/gamma_ID003.md" not in body_gets

    def test_combined_filter_and_keyword(self, bucket_env, fake_s3):
        # Vega docs are Alpha + Gamma; keyword "onboarding" is only in Gamma's body.
        out = DovetailCorpusTool()._run(
            action="search", filters="research_topic_area=Vega", query="onboarding", limit=10
        )
        data = json.loads(out)
        titles = {d["metadata"]["title"] for d in data["documents"]}
        assert titles == {"Gamma Study"}

    def test_no_match_returns_message_not_error(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(
            action="search", filters="research_topic_area=Nonexistent", limit=10
        )
        assert "no dovetail corpus documents matched" in out.lower()

    def test_non_filterable_key_is_ignored(self, bucket_env, fake_s3):
        # 'author' is not a filterable field; a filter on it is dropped, so the
        # search behaves as if unfiltered (all 3 returned, capped by limit).
        out = DovetailCorpusTool()._run(
            action="search", filters="author=internal-user-id-should-not-surface-as-filter", limit=10
        )
        data = json.loads(out)
        assert data["filters"] == {}
        assert data["matched"] == 3

    def test_limit_caps_results(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="search", limit=1)
        data = json.loads(out)
        assert data["matched"] == 1


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------
class TestGet:
    def test_get_by_dovetail_id(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="get", doc_id="ID002")
        data = json.loads(out)
        assert data["key"] == "data/beta_ID002.md"
        assert "Beta body" in data["content"]

    def test_get_by_full_key(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="get", doc_id="data/alpha_ID001.md")
        data = json.loads(out)
        assert data["metadata"]["title"] == "Alpha Report"

    def test_get_missing_id(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="get", doc_id="ID999")
        assert "no dovetail corpus document found" in out.lower()

    def test_get_requires_doc_id(self, bucket_env, fake_s3):
        out = DovetailCorpusTool()._run(action="get", doc_id="")
        assert "requires a 'doc_id'" in out


# ---------------------------------------------------------------------------
# Bedrock KB branch (dormant scaffold — mock only, not live-verified)
# ---------------------------------------------------------------------------
class _FakeBedrock:
    def __init__(self):
        self.called = False

    def retrieve(self, **kwargs):
        self.called = True
        self.kwargs = kwargs
        return {
            "retrievalResults": [
                {"content": {"text": "KB chunk about vega"}, "location": {"type": "S3"}, "score": 0.9},
            ]
        }


class TestKBBranch:
    def test_kb_id_routes_to_retrieve_not_s3(self, bucket_env, fake_s3, monkeypatch):
        monkeypatch.setenv("DOVETAIL_KB_ID", "kb-placeholder-123")
        fake_bedrock = _FakeBedrock()
        monkeypatch.setattr(dc, "_bedrock_agent_client", lambda: fake_bedrock)

        out = DovetailCorpusTool()._run(action="search", query="vega", limit=5)
        data = json.loads(out)
        assert data["source"] == "bedrock_kb"
        assert fake_bedrock.called is True
        assert fake_bedrock.kwargs["knowledgeBaseId"] == "kb-placeholder-123"
        # KB branch must NOT scan S3 bodies.
        assert not fake_s3.get_keys

    def test_kb_search_requires_query(self, bucket_env, fake_s3, monkeypatch):
        monkeypatch.setenv("DOVETAIL_KB_ID", "kb-placeholder-123")
        monkeypatch.setattr(dc, "_bedrock_agent_client", lambda: _FakeBedrock())
        out = DovetailCorpusTool()._run(action="search", query="  ", limit=5)
        assert "requires a non-empty 'query'" in out

    def test_s3_path_used_when_kb_unset(self, bucket_env, fake_s3, monkeypatch):
        monkeypatch.delenv("DOVETAIL_KB_ID", raising=False)
        out = DovetailCorpusTool()._run(action="search", filters="research_topic_area=Vega")
        data = json.loads(out)
        # S3 path returns the {matched, filters, documents} shape, not KB shape.
        assert "documents" in data and "source" not in data


# ---------------------------------------------------------------------------
# Call logging
# ---------------------------------------------------------------------------
class TestCallLogging:
    def test_logs_invocation_and_response(self, bucket_env, fake_s3, monkeypatch, tmp_path):
        log_file = tmp_path / "dovetail_corpus_calls.log"
        monkeypatch.setattr(dc, "_CALL_LOG_PATH", log_file)
        DovetailCorpusTool()._run(action="list", limit=5)
        assert log_file.exists()
        events = [json.loads(line) for line in log_file.read_text().strip().splitlines()]
        types = [e["event"] for e in events]
        assert types[0] == "invocation"
        assert "response" in types
