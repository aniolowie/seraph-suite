"""Knowledge base layer — vector store, graph store, retrieval.

Import graph components directly from their modules to avoid circular imports:

    from seraph.knowledge.graphstore import Neo4jStore
    from seraph.knowledge.graph_retriever import GraphRAGRetriever
    from seraph.knowledge.entity_extractor import EntityExtractor
"""

from __future__ import annotations

from seraph.knowledge.embeddings import DenseEmbedder, SparseEmbedder
from seraph.knowledge.entity_extractor import EntityExtractor
from seraph.knowledge.reranker import CrossEncoderReranker
from seraph.knowledge.retriever import HybridRetriever
from seraph.knowledge.vectorstore import QdrantStore

__all__ = [
    "CrossEncoderReranker",
    "DenseEmbedder",
    "EntityExtractor",
    "HybridRetriever",
    "QdrantStore",
    "SparseEmbedder",
]
