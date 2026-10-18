"""Retrieval: chunking + BM25 keyword ranking + an explainable 'coverage' evidence check.

Why BM25 and not embeddings? Embeddings need a provider key (Anthropic does not offer an
embeddings endpoint). BM25 works offline, is deterministic, and is easy to explain.
`Retriever` is the single place to plug in embeddings later.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .db import Database

STOP = set("""a an the and or but if of to in on at for with from by is are was were be been being do does did
how what when where which who why can could should would will i you we they it this that these those my your our
me us as about into than then so not no yes any some there here have has had get set use using need want please
""".split())
TOKEN_RE = re.compile(r"[a-z0-9]+")


def stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def tokenize(text: str, keep_stop: bool = False) -> list[str]:
    toks = TOKEN_RE.findall(text.lower())
    return [stem(t) for t in toks if keep_stop or t not in STOP]


def chunk_text(title: str, content: str, max_chars: int = 600) -> list[str]:
    """Greedy paragraph packing. Each chunk is prefixed with the title so it stays self-describing."""
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", content) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if cur and len(cur) + len(p) > max_chars:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{p}".strip()
        while len(cur) > max_chars * 2:  # very long paragraph: hard split
            chunks.append(cur[:max_chars * 2])
            cur = cur[max_chars * 2:]
    if cur:
        chunks.append(cur)
    return [f"{title}\n{c}" for c in chunks] or [title]


@dataclass
class Passage:
    chunk_id: int
    article_id: int
    title: str
    url: str
    source: str
    text: str
    score: float
    coverage: float  # fraction of the question's content words found in the passage


class Retriever:
    K1, B = 1.5, 0.75

    def __init__(self, db: Database):
        self.db = db

    def _load(self) -> list[dict]:
        # Only ACTIVE articles are searchable: removed articles can never appear in answers.
        return self.db.all(
            """SELECT c.id chunk_id, c.text, a.id article_id, a.title, a.url, a.source
               FROM chunks c JOIN articles a ON a.id=c.article_id WHERE a.active=1""")

    def search(self, query: str, top_k: int = 4) -> list[Passage]:
        q_tokens = list(dict.fromkeys(tokenize(query)))
        if not q_tokens:
            return []
        rows = self._load()
        if not rows:
            return []
        docs = [tokenize(r["text"], keep_stop=True) for r in rows]
        n = len(docs)
        avgdl = sum(len(d) for d in docs) / n or 1
        df = Counter(t for d in docs for t in set(d))
        out: list[Passage] = []
        for r, d in zip(rows, docs):
            tf = Counter(d)
            score = 0.0
            for t in q_tokens:
                if t in tf:
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    score += idf * tf[t] * (self.K1 + 1) / (tf[t] + self.K1 * (1 - self.B + self.B * len(d) / avgdl))
            if score <= 0:
                continue
            if r["source"] == "expert":
                score *= 1.15  # human-approved answers win ties against crawled text
            cov = sum(1 for t in q_tokens if t in tf) / len(q_tokens)
            out.append(Passage(r["chunk_id"], r["article_id"], r["title"], r["url"], r["source"],
                               r["text"], round(score, 4), round(cov, 3)))
        out.sort(key=lambda p: (-p.score, p.chunk_id))
        # keep at most 2 chunks per article so sources are diverse
        picked, per = [], Counter()
        for p in out:
            if per[p.article_id] < 2:
                picked.append(p)
                per[p.article_id] += 1
            if len(picked) >= top_k:
                break
        return picked


def evidence_status(passages: list[Passage], supported: float, partial: float) -> str:
    """supported | partial | insufficient, based only on word coverage of the best passage."""
    if not passages:
        return "insufficient"
    best = max(p.coverage for p in passages)
    if best >= supported:
        return "supported"
    if best >= partial:
        return "partial"
    return "insufficient"
