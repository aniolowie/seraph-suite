"""Root conftest — sets required environment variables before any seraph imports.

The Settings singleton is created at module import time, so required fields
(anthropic_api_key, neo4j_password) must be present in the environment even
during unit tests. These test values are never used for real API calls.
"""

from __future__ import annotations

import os

# Set required env vars before any seraph module is imported.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-sk-ant-placeholder")
os.environ.setdefault("NEO4J_PASSWORD", "test-password")
