"""Local BM25 retrieval over closed knowledge assets and design freezes (WP-11).

Single source of truth for knowledge-reuse retrieval. The runtime is pack-level
(``scripts/``, beside ``constraint_role.py``) and deliberately does NOT belong to
any skill: consuming preflights import it through the same probe pattern used
for the constraint-role resolver, and the installer deploys a copy beside a
skill's own scripts via ``SHARED_MODULES``.

Plan two questions, answered up front (WP-11 opening questions):

1. Index source = already-CLOSED projects only: ``knowledge_asset`` artifacts
   with ``asset_status == "CLOSED_KNOWLEDGE"`` and ``design_freeze`` artifacts
   with ``stage == "FROZEN"``. Nothing currently produces ``knowledge_asset``,
   so an empty index is the normal state; retrieval over an empty set must
   never block a preflight (fail-open applies here and ONLY here).
2. Embedding = local BM25 over stdlib tokenization only. No online API, no
   network access; the module must run with the network unplugged.

Scoring: Okapi BM25 (k1=1.5, b=0.75) with the ``ln(1 + (N-df+0.5)/(df+0.5))``
idf variant so unseen query terms cannot produce negative scores. Tokens are
lowercased ASCII alnum runs; CJK text is covered by character bigrams (single
CJK characters are too ambiguous for term matching).
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

INDEXABLE_TYPES = ("knowledge_asset", "design_freeze")

BACKEND = "local_bm25"
HISTORY_ROOTS_ENV = "LUBRICANT_KNOWLEDGE_ROOTS"
TOP_K_DEFAULT = 3
BM25_K1 = 1.5
BM25_B = 0.75

_ASCII_TOKEN = re.compile(r"[a-z0-9]+")
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")

# Only documents proving real closure are indexed: a knowledge asset must have
# reached CLOSED_KNOWLEDGE, a design freeze must have reached FROZEN.
_CLOSURE_FILTER = {
    "knowledge_asset": lambda artifact: artifact.get("asset_status") == "CLOSED_KNOWLEDGE",
    "design_freeze": lambda artifact: artifact.get("stage") == "FROZEN",
}

SNIPPET_LENGTH = 120


def describe_backend() -> str:
    """Backend label used in preflight summaries and ``reuse_index`` records."""
    return BACKEND


def tokenize(text: str) -> list[str]:
    """ASCII word tokens plus CJK character bigrams, all lowercased."""
    if not isinstance(text, str):
        return []
    lowered = text.casefold()
    tokens = _ASCII_TOKEN.findall(lowered)
    for run in _CJK_RUN.findall(lowered):
        tokens.extend(run[index:index + 2] for index in range(max(len(run) - 1, 0)))
        if len(run) == 1:
            tokens.append(run)
    return tokens


def artifact_text(artifact: dict) -> str:
    """Stable full-text rendering of one artifact for indexing."""
    return json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str)


def _closed_document(path: Path) -> dict | None:
    """Load one candidate file; keep it only if it proves closure."""
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(artifact, dict):
        return None
    kind = artifact.get("artifact_type")
    if kind not in _CLOSURE_FILTER or not _CLOSURE_FILTER[kind](artifact):
        return None
    text = artifact_text(artifact)
    return {
        "source": str(path),
        "artifact_type": kind,
        "project_id": artifact.get("project_id", ""),
        "stage": artifact.get("stage", ""),
        "text": text,
        "tokens": tokenize(text),
    }


def collect_documents(roots: object) -> list[dict]:
    """Collect indexable closed documents from files/directories.

    ``roots`` accepts an iterable of path-like values (or a single one). Files
    that cannot be read or parsed are skipped; retrieval is advisory and must
    never raise for messy history directories.
    """
    if roots is None:
        return []
    if isinstance(roots, (str, Path)):
        roots = [roots]
    documents: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        try:
            path = Path(root)
            candidates = sorted(path.rglob("*.json")) if path.is_dir() else ([path] if path.is_file() else [])
        except OSError:
            continue
        for candidate in candidates:
            resolved = str(candidate.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            document = _closed_document(candidate)
            if document is not None:
                documents.append(document)
    return documents


class BM25Index:
    """Minimal Okapi BM25 over pre-collected documents."""

    def __init__(self, documents: list[dict], k1: float = BM25_K1, b: float = BM25_B) -> None:
        self.k1 = k1
        self.b = b
        self.documents = documents
        self.term_counts: list[dict[str, int]] = []
        self.document_frequency: dict[str, int] = {}
        for document in documents:
            counts: dict[str, int] = {}
            for token in document["tokens"]:
                counts[token] = counts.get(token, 0) + 1
            self.term_counts.append(counts)
            for term in counts:
                self.document_frequency[term] = self.document_frequency.get(term, 0) + 1
        lengths = [len(document["tokens"]) for document in documents]
        self.total_length = sum(lengths)
        self.average_length = (sum(lengths) / len(lengths)) if lengths else 0.0

    def _idf(self, term: str) -> float:
        document_count = len(self.documents)
        frequency = self.document_frequency.get(term, 0)
        return math.log(1.0 + (document_count - frequency + 0.5) / (frequency + 0.5))

    def search(self, query: str, top_k: int = TOP_K_DEFAULT) -> list[dict]:
        """Return the best-scoring documents whose score is strictly positive."""
        if not self.documents or top_k <= 0:
            return []
        scores = [0.0] * len(self.documents)
        for term, count in _term_counts(query).items():
            idf = self._idf(term)
            if idf <= 0.0:
                continue
            for position, counts in enumerate(self.term_counts):
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                length = len(self.documents[position]["tokens"])
                average = self.average_length if self.average_length else 0.0
                normalizer = frequency + self.k1 * (1.0 - self.b + self.b * (length / average if average else 0.0))
                scores[position] += idf * ((frequency * (self.k1 + 1.0)) / normalizer)
        hits = [
            {"document": self.documents[position], "score": score}
            for position, score in enumerate(scores)
            if score > 0.0
        ]
        hits.sort(key=lambda hit: (-hit["score"], hit["document"]["source"]))
        return hits[:top_k]


def _term_counts(query: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for token in tokenize(query):
        counts[token] = counts.get(token, 0) + 1
    return counts


def _hit_record(hit: dict) -> dict:
    document = hit["document"]
    text = document["text"]
    return {
        "source": document["source"],
        "artifact_type": document["artifact_type"],
        "project_id": document["project_id"],
        "stage": document["stage"],
        "score": round(hit["score"], 6),
        "snippet": text[:SNIPPET_LENGTH],
    }


def search_history(query: str, roots: object, top_k: int = TOP_K_DEFAULT) -> list[dict]:
    """Search closed history; NEVER raises and NEVER returns zero-score noise.

    This is the single fail-open boundary mandated by the plan: an empty index
    (the normal state today) or any read/parse error returns ``[]`` so calling
    preflights cannot be blocked by retrieval problems.
    """
    try:
        documents = collect_documents(roots)
        if not documents:
            return []
        index = BM25Index(documents)
        return [_hit_record(hit) for hit in index.search(query, top_k=top_k) if hit["score"] > 0.0]
    except Exception:  # noqa: BLE001 - fail-open is the contract at this boundary
        return []


def history_roots(value: object, input_path: Path | None = None) -> list[Path]:
    """Normalize a ``history_roots`` value from preflight input JSON.

    Accepts a single path-like or a list. Relative paths resolve against the
    preflight input file's directory (same rule as artifact references).
    """
    if value is None:
        return []
    if isinstance(value, (str, Path)):
        value = [value]
    if not isinstance(value, list):
        return []
    roots: list[Path] = []
    for item in value:
        if not isinstance(item, (str, Path)) or not str(item).strip():
            continue
        path = Path(item)
        if input_path is not None and not path.is_absolute():
            path = input_path.parent / path
        roots.append(path)
    return roots


def history_roots_from_env(environ: object = None) -> list[Path]:
    """History roots declared through ``LUBRICANT_KNOWLEDGE_ROOTS`` (os.pathsep)."""
    source = os.environ if environ is None else environ
    raw = source.get(HISTORY_ROOTS_ENV, "") if hasattr(source, "get") else ""
    return [Path(part) for part in raw.split(os.pathsep) if part.strip()]
