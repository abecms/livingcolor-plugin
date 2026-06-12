"""Shadow evaluation workspace cleanup."""

from __future__ import annotations

import shutil
from pathlib import Path

from delivery_runtime.shadow.mode import should_keep_workspace
from delivery_runtime.shadow.paths import get_work_order_artifact_root


def cleanup_work_order_workspace(work_order_id: str) -> bool:
    if should_keep_workspace():
        return False
    workspace = get_work_order_artifact_root(work_order_id) / "workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
        return True
    return False
