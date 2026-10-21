"""Vector store tests with a deterministic fake embedder (no model download)."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.chunking import Chunk
from app.rag.vector_store import VectorStore

WORDS = ["markov", "poisson", "variance", "queue", "bayes", "entropy", "gamma", "chain"]


class BagEmbedder:
    """One dimension per vocabulary word; unit-length like the real embedder."""

    def encode(self, texts):
        out = np.zeros((len(texts), len(WORDS)), dtype=np.float32)
        for i, t in enumerate(texts):
            for j, w in enumerate(WORDS):
                out[i, j] = t.lower().count(w)
            n = np.linalg.norm(out[i])
            out[i] /= n if n else 1.0
        return out


def chunk(doc, i, text, page=None):
    return Chunk(f"{doc}-{i}", doc, text, page, page, "Sec", i)


class VectorStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "vectors.db"
        self.store = VectorStore(self.path, BagEmbedder())

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_store_returns_nothing(self):
        self.assertEqual(self.store.query("markov chain", 5), [])
        self.assertEqual(self.store.count(), 0)

    def test_ranks_by_cosine_and_returns_metadata(self):
        self.store.add_chunks([chunk("a", 0, "markov chain transitions", 3),
                               chunk("a", 1, "poisson queue arrivals"),
                               chunk("a", 2, "bayes entropy gamma")], "Notes")
        hits = self.store.query("markov chain", 3)
        self.assertEqual(hits[0].chunk_id, "a-0")
        self.assertAlmostEqual(hits[0].score, 1.0, places=5)
        self.assertEqual((hits[0].doc_title, hits[0].page_start, hits[0].page_end, hits[0].section),
                         ("Notes", 3, 3, "Sec"))
        self.assertIsNone(hits[1].page_start)  # -1 sentinel maps back to None
        self.assertEqual([h.score for h in hits], sorted((h.score for h in hits), reverse=True))

    def test_k_larger_than_store(self):
        self.store.add_chunks([chunk("a", 0, "markov"), chunk("a", 1, "poisson")], "N")
        self.assertEqual(len(self.store.query("markov", 50)), 2)

    def test_delete_document_removes_only_that_document(self):
        self.store.add_chunks([chunk("a", 0, "markov chain")], "A")
        self.store.add_chunks([chunk("b", 0, "markov chain")], "B")
        self.store.query("markov", 5)  # warm the cache
        self.store.delete_document("a")
        self.assertEqual({h.doc_id for h in self.store.query("markov", 5)}, {"b"})
        self.assertEqual(self.store.count(), 1)

    def test_reindexing_same_chunk_ids_replaces_rows(self):
        self.store.add_chunks([chunk("a", 0, "markov")], "Old title")
        self.store.add_chunks([chunk("a", 0, "poisson")], "New title")
        self.assertEqual(self.store.count(), 1)
        hit = self.store.query("poisson", 1)[0]
        self.assertEqual((hit.doc_title, hit.text), ("New title", "poisson"))

    def test_persists_across_instances(self):
        self.store.add_chunks([chunk("a", 0, "variance gamma")], "N")
        again = VectorStore(self.path, BagEmbedder())
        self.assertEqual(again.query("gamma", 1)[0].chunk_id, "a-0")

    def test_chunks_from_other_embedding_dimension_are_ignored(self):
        class Tiny:
            def encode(self, texts):
                return np.ones((len(texts), 3), dtype=np.float32) / np.sqrt(3)

        VectorStore(self.path, Tiny()).add_chunks([chunk("old", 0, "legacy")], "Old")
        self.store.add_chunks([chunk("a", 0, "markov")], "N")
        self.assertEqual([h.doc_id for h in self.store.query("markov", 5)], ["a"])


if __name__ == "__main__":
    unittest.main()
