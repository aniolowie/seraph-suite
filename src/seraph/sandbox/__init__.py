"""Docker sandbox — Manus-style isolated agent containers.

Public API::

    from seraph.sandbox import (
        ContainerManager,
        ContainerPool,
        SandboxExecutor,
        SandboxNetworkManager,
    )
"""

from __future__ import annotations

from seraph.sandbox.executor import SandboxExecutor
from seraph.sandbox.manager import ContainerManager
from seraph.sandbox.network import SandboxNetworkManager
from seraph.sandbox.pool import ContainerPool

__all__ = [
    "ContainerManager",
    "ContainerPool",
    "SandboxExecutor",
    "SandboxNetworkManager",
]
