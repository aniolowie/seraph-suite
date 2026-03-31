# Seraph Suite — Knowledge Base Reference

> Work in progress. Updated as Phase 1 & 2 ship.

## Sources

| Source | Ingestion script | Collection |
|--------|-----------------|------------|
| NVD CVE feed | `seraph ingest nvd` | `seraph_kb` |
| ExploitDB | `seraph ingest exploitdb` | `seraph_kb` |
| MITRE ATT&CK | `seraph ingest mitre` | Neo4j graph |
| HTB writeups | `seraph ingest writeups <path>` | `seraph_kb` |

## Retrieval Pipeline

Every query goes through:
1. BM25 sparse search (FastEmbed/Qdrant)
2. Dense semantic search (nomic-embed-text-v1.5)
3. RRF fusion
4. Optional Neo4j graph traversal
5. Cross-encoder rerank (bge-reranker-v2-m3)

## Chunking Rules

- CVE descriptions: single chunk
- Writeups: 200–500 tokens, never split code blocks
- Prepend source tag: `[CVE-2021-44228] ...` or `[writeup:machine-name] ...`
- CVSS scores, dates → Qdrant payload (not embedded)
