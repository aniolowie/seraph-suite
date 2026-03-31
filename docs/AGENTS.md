# Seraph Suite — Agent Reference

> Work in progress. Updated as Phase 3 ships.

## Agent Overview

| Agent | Phase | LLM | Tools |
|-------|-------|-----|-------|
| Orchestrator | all | Opus 4 | none (reasoning only) |
| Recon | recon | Sonnet 4.6 | nmap, curl |
| Enumerate | enumerate | Sonnet 4.6 | nmap, gobuster, ffuf, nikto, curl |
| Exploit | exploit | Sonnet 4.6 | metasploit, sqlmap, hydra, curl |
| Privesc | privesc | Sonnet 4.6 | linpeas, winpeas, metasploit |
| CTF | all | Sonnet 4.6 | all |
| Tagger | all | Sonnet 4.6 | none |
| Memorist | all | Haiku 4.5 | none |

## EngagementState

All agents share a single `EngagementState` Pydantic model (see `src/seraph/agents/state.py`).
State is immutable — each agent returns an updated copy via `model_copy(update={...})`.

## Tool Selection

When the tool count exceeds 20, the agent uses RAG-based tool selection:
1. Embed the current task description
2. Retrieve top-K tool descriptions from Qdrant
3. Only pass the top-K tools to the LLM — not the full registry

This prevents context bloat and improves tool selection accuracy.

## Prompts

All prompts live in `src/seraph/agents/prompts/` as `.jinja2` files.
Never inline long prompts in Python source.
