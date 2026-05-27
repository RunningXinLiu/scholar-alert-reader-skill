"""Local semantic reranking helpers.

The default backend is dependency-free sparse TF-IDF. A sentence-transformers
backend is available only when the optional dependency is installed.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EmbeddingEncoder = Callable[[list[str], str, int], list[list[float]]]


class EmbeddingBackendUnavailable(RuntimeError):
    """Raised when an optional embedding backend cannot be used."""


STOPWORDS = {
    "about",
    "across",
    "after",
    "among",
    "analysis",
    "and",
    "based",
    "between",
    "case",
    "data",
    "during",
    "earth",
    "effects",
    "evidence",
    "for",
    "from",
    "global",
    "into",
    "large",
    "method",
    "model",
    "models",
    "new",
    "paper",
    "regional",
    "results",
    "study",
    "system",
    "that",
    "the",
    "their",
    "this",
    "through",
    "toward",
    "towards",
    "under",
    "using",
    "with",
}


@dataclass
class SemanticRerankRow:
    base_rank: int
    rank: int
    record: dict[str, Any]
    base_score: int
    semantic_score: int
    delta: int
    profile_similarity: float
    positive_similarity: float
    negative_similarity: float
    profile_overlap: list[str]
    positive_overlap: list[str]
    negative_overlap: list[str]
    backend: str = "local-sparse-tfidf"


def text(value: Any) -> str:
    return str(value or "").strip()


def stem_token(value: str) -> str:
    token = value.lower().strip("-_")
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ing", "ers")):
        return token[:-3]
    if len(token) > 3 and token.endswith(("ed", "es")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def base_tokens(value: str) -> list[str]:
    raw = re.findall(r"[a-z0-9]+", value.lower())
    tokens = [stem_token(token) for token in raw]
    return [token for token in tokens if len(token) > 2 and token not in STOPWORDS]


def sparse_terms(value: str) -> list[str]:
    tokens = base_tokens(value)
    terms = list(tokens)
    terms.extend(f"{left}_{right}" for left, right in zip(tokens, tokens[1:]) if left != right)
    return terms


def record_text(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    metadata_texts: list[str] = []
    for provider in ["openalex", "crossref", "web", "bibtex", "ris"]:
        item = metadata.get(provider)
        if not isinstance(item, dict):
            continue
        for key in ["title", "source", "container_title", "journal", "keywords"]:
            value = item.get(key)
            if isinstance(value, list):
                metadata_texts.extend(text(entry) for entry in value)
            elif value:
                metadata_texts.append(text(value))
    return " ".join(
        [
            text(record.get("title")),
            text(record.get("title")),
            text(record.get("snippet")),
            text(record.get("authors_source")),
            " ".join(text(alert) for alert in record.get("alerts", []) if text(alert)),
            " ".join(text(term) for term in record.get("matched_terms", []) if text(term)),
            " ".join(text(tag) for tag in record.get("tags", []) if text(tag)),
            " ".join(metadata_texts),
        ]
    )


def build_idf(documents: list[list[str]]) -> dict[str, float]:
    doc_count = max(1, len(documents))
    document_frequency: Counter[str] = Counter()
    for terms in documents:
        document_frequency.update(set(terms))
    return {
        term: math.log((1 + doc_count) / (1 + count)) + 1.0
        for term, count in document_frequency.items()
    }


def vectorize(terms: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts = Counter(terms)
    vector: dict[str, float] = {}
    for term, count in counts.items():
        vector[term] = (1.0 + math.log(count)) * idf.get(term, 1.0)
    return vector


def cosine(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[term] * right[term] for term in common)
    if numerator <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def dense_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    length = min(len(left), len(right))
    if length <= 0:
        return 0.0
    numerator = sum(left[index] * right[index] for index in range(length))
    if numerator <= 0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left[:length]))
    right_norm = math.sqrt(sum(value * value for value in right[:length]))
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def coerce_dense_vector(value: Any) -> list[float]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)):
        raise EmbeddingBackendUnavailable("embedding backend returned a non-vector value")
    return [float(item) for item in value]


def sentence_transformers_encoder(texts: list[str], model_name: str, batch_size: int) -> list[list[float]]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - exercised through CLI error path.
        raise EmbeddingBackendUnavailable(
            "sentence-transformers is not installed. From a source checkout, install optional embedding "
            "extras with `python3 -m pip install '.[embedding]'`; otherwise install `sentence-transformers` "
            "in the active environment or rerun with `--backend sparse`."
        ) from exc
    try:
        model = SentenceTransformer(model_name)
        vectors = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
    except Exception as exc:  # pragma: no cover - depends on external model/runtime state.
        raise EmbeddingBackendUnavailable(
            f"Could not load or run embedding model `{model_name}`. Use a locally available "
            "sentence-transformers model, pre-cache the model, or rerun with `--backend sparse`."
        ) from exc
    return [coerce_dense_vector(vector) for vector in vectors]


def best_similarity(
    target_terms: list[str],
    target_vector: dict[str, float],
    seed_terms: list[list[str]],
    seed_vectors: list[dict[str, float]],
    limit: int = 8,
) -> tuple[float, list[str]]:
    best_score = 0.0
    best_overlap: list[str] = []
    target_set = set(target_terms)
    for terms, vector in zip(seed_terms, seed_vectors):
        score = cosine(target_vector, vector)
        if score <= best_score:
            continue
        overlap = sorted(target_set & set(terms), key=lambda term: (term.count("_"), term))
        best_score = score
        best_overlap = [term.replace("_", " ") for term in overlap[:limit]]
    return best_score, best_overlap


def best_dense_similarity(
    target_terms: list[str],
    target_vector: list[float],
    seed_terms: list[list[str]],
    seed_vectors: list[list[float]],
    limit: int = 8,
) -> tuple[float, list[str]]:
    best_score = 0.0
    best_index = -1
    for index, vector in enumerate(seed_vectors):
        score = dense_cosine(target_vector, vector)
        if score <= best_score:
            continue
        best_score = score
        best_index = index
    if best_index < 0:
        return best_score, []
    target_set = set(target_terms)
    overlap = sorted(target_set & set(seed_terms[best_index]), key=lambda term: (term.count("_"), term))
    return best_score, [term.replace("_", " ") for term in overlap[:limit]]


def semantic_rerank_records(
    records: list[dict[str, Any]],
    profile_texts: list[str],
    positive_seed_texts: list[str],
    negative_seed_texts: list[str],
    profile_weight: int = 16,
    positive_weight: int = 14,
    negative_weight: int = 18,
    backend: str = "sparse",
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_batch_size: int = 32,
    embedding_encoder: EmbeddingEncoder | None = None,
) -> list[SemanticRerankRow]:
    if backend in {"sparse", "local-sparse-tfidf"}:
        return sparse_semantic_rerank_records(
            records,
            profile_texts,
            positive_seed_texts,
            negative_seed_texts,
            profile_weight=profile_weight,
            positive_weight=positive_weight,
            negative_weight=negative_weight,
        )
    if backend in {"sentence-transformers", "embedding"}:
        return embedding_semantic_rerank_records(
            records,
            profile_texts,
            positive_seed_texts,
            negative_seed_texts,
            profile_weight=profile_weight,
            positive_weight=positive_weight,
            negative_weight=negative_weight,
            embedding_model=embedding_model,
            embedding_batch_size=embedding_batch_size,
            embedding_encoder=embedding_encoder,
        )
    raise ValueError(f"Unknown semantic rerank backend: {backend}")


def sparse_semantic_rerank_records(
    records: list[dict[str, Any]],
    profile_texts: list[str],
    positive_seed_texts: list[str],
    negative_seed_texts: list[str],
    profile_weight: int = 16,
    positive_weight: int = 14,
    negative_weight: int = 18,
) -> list[SemanticRerankRow]:
    record_terms = [sparse_terms(record_text(record)) for record in records]
    profile_terms = [sparse_terms(value) for value in profile_texts if text(value)]
    positive_terms = [sparse_terms(value) for value in positive_seed_texts if text(value)]
    negative_terms = [sparse_terms(value) for value in negative_seed_texts if text(value)]
    idf = build_idf(record_terms + profile_terms + positive_terms + negative_terms)
    record_vectors = [vectorize(terms, idf) for terms in record_terms]
    profile_vectors = [vectorize(terms, idf) for terms in profile_terms]
    positive_vectors = [vectorize(terms, idf) for terms in positive_terms]
    negative_vectors = [vectorize(terms, idf) for terms in negative_terms]

    rows: list[SemanticRerankRow] = []
    for base_rank, (record, terms, vector) in enumerate(zip(records, record_terms, record_vectors), 1):
        profile_similarity, profile_overlap = best_similarity(terms, vector, profile_terms, profile_vectors)
        positive_similarity, positive_overlap = best_similarity(terms, vector, positive_terms, positive_vectors)
        negative_similarity, negative_overlap = best_similarity(terms, vector, negative_terms, negative_vectors)
        delta = round(
            profile_similarity * profile_weight
            + positive_similarity * positive_weight
            - negative_similarity * negative_weight
        )
        base_score = int(record.get("score", 0) or 0)
        rows.append(
            SemanticRerankRow(
                base_rank=base_rank,
                rank=0,
                record=record,
                base_score=base_score,
                semantic_score=base_score + delta,
                delta=delta,
                profile_similarity=profile_similarity,
                positive_similarity=positive_similarity,
                negative_similarity=negative_similarity,
                profile_overlap=profile_overlap,
                positive_overlap=positive_overlap,
                negative_overlap=negative_overlap,
                backend="local-sparse-tfidf",
            )
        )
    return ranked_rows(rows)


def embedding_semantic_rerank_records(
    records: list[dict[str, Any]],
    profile_texts: list[str],
    positive_seed_texts: list[str],
    negative_seed_texts: list[str],
    profile_weight: int = 16,
    positive_weight: int = 14,
    negative_weight: int = 18,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_batch_size: int = 32,
    embedding_encoder: EmbeddingEncoder | None = None,
) -> list[SemanticRerankRow]:
    encoder = embedding_encoder or sentence_transformers_encoder
    record_texts = [record_text(record) for record in records]
    profile_seed_texts = [value for value in profile_texts if text(value)]
    positive_texts = [value for value in positive_seed_texts if text(value)]
    negative_texts = [value for value in negative_seed_texts if text(value)]
    all_texts = record_texts + profile_seed_texts + positive_texts + negative_texts
    if not all_texts:
        return []
    vectors = encoder(all_texts, embedding_model, embedding_batch_size)
    expected = len(all_texts)
    if len(vectors) != expected:
        raise EmbeddingBackendUnavailable(f"embedding backend returned {len(vectors)} vectors for {expected} texts")
    record_vectors = vectors[: len(record_texts)]
    profile_start = len(record_texts)
    positive_start = profile_start + len(profile_seed_texts)
    negative_start = positive_start + len(positive_texts)
    profile_vectors = vectors[profile_start:positive_start]
    positive_vectors = vectors[positive_start:negative_start]
    negative_vectors = vectors[negative_start:]
    record_terms = [sparse_terms(value) for value in record_texts]
    profile_terms = [sparse_terms(value) for value in profile_seed_texts]
    positive_terms = [sparse_terms(value) for value in positive_texts]
    negative_terms = [sparse_terms(value) for value in negative_texts]

    rows: list[SemanticRerankRow] = []
    backend_label = f"sentence-transformers:{embedding_model}"
    for base_rank, (record, terms, vector) in enumerate(zip(records, record_terms, record_vectors), 1):
        profile_similarity, profile_overlap = best_dense_similarity(terms, vector, profile_terms, profile_vectors)
        positive_similarity, positive_overlap = best_dense_similarity(terms, vector, positive_terms, positive_vectors)
        negative_similarity, negative_overlap = best_dense_similarity(terms, vector, negative_terms, negative_vectors)
        delta = round(
            profile_similarity * profile_weight
            + positive_similarity * positive_weight
            - negative_similarity * negative_weight
        )
        base_score = int(record.get("score", 0) or 0)
        rows.append(
            SemanticRerankRow(
                base_rank=base_rank,
                rank=0,
                record=record,
                base_score=base_score,
                semantic_score=base_score + delta,
                delta=delta,
                profile_similarity=profile_similarity,
                positive_similarity=positive_similarity,
                negative_similarity=negative_similarity,
                profile_overlap=profile_overlap,
                positive_overlap=positive_overlap,
                negative_overlap=negative_overlap,
                backend=backend_label,
            )
        )
    return ranked_rows(rows)


def ranked_rows(rows: list[SemanticRerankRow]) -> list[SemanticRerankRow]:
    rows.sort(
        key=lambda row: (
            -row.semantic_score,
            {"Must read": 0, "Skim": 1, "Archive": 2}.get(text(row.record.get("tier")), 9),
            row.base_rank,
            text(row.record.get("title")).lower(),
        )
    )
    for rank, row in enumerate(rows, 1):
        row.rank = rank
    return rows


def semantic_backend_description(backend: str, embedding_model: str = DEFAULT_EMBEDDING_MODEL) -> str:
    if backend in {"sparse", "local-sparse-tfidf"}:
        return "local sparse TF-IDF over title/snippet/source/terms/tags"
    if backend in {"sentence-transformers", "embedding"}:
        return f"optional local sentence-transformers embeddings (`{embedding_model}`)"
    return backend
