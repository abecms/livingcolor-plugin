"""Persistence for Scope Contracts (Phase 3E)."""

from __future__ import annotations

from typing import Any

from delivery_runtime.development.scope_contract import ScopeContract, build_scope_contract
from delivery_runtime.persistence.db import connect, json_dumps, json_loads, next_public_id, utc_now_iso


def save_scope_contract(contract: ScopeContract) -> ScopeContract:
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM scope_contracts WHERE work_order_id = ?",
            (contract.work_order_id,),
        ).fetchone()
        payload = contract.to_dict()
        if existing:
            conn.execute(
                """
                UPDATE scope_contracts
                SET allowed_files_json = ?,
                    allowed_directories_json = ?,
                    forbidden_paths_json = ?,
                    max_files_touched = ?,
                    max_lines_changed = ?
                WHERE work_order_id = ?
                """,
                (
                    json_dumps(payload["allowedFiles"]),
                    json_dumps(payload["allowedDirectories"]),
                    json_dumps(payload["forbiddenPaths"]),
                    payload["maxFilesTouched"],
                    payload["maxLinesChanged"],
                    contract.work_order_id,
                ),
            )
            return contract

        contract_id = next_public_id(conn, "SC")
        conn.execute(
            """
            INSERT INTO scope_contracts (
                id, work_order_id, allowed_files_json, allowed_directories_json,
                forbidden_paths_json, max_files_touched, max_lines_changed, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contract_id,
                contract.work_order_id,
                json_dumps(payload["allowedFiles"]),
                json_dumps(payload["allowedDirectories"]),
                json_dumps(payload["forbiddenPaths"]),
                payload["maxFilesTouched"],
                payload["maxLinesChanged"],
                utc_now_iso(),
            ),
        )
    return contract


def load_scope_contract(work_order_id: str) -> ScopeContract | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM scope_contracts WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
    if not row:
        return None
    return ScopeContract(
        work_order_id=str(row["work_order_id"]),
        allowed_files=json_loads(row["allowed_files_json"], []),
        allowed_directories=json_loads(row["allowed_directories_json"], []),
        forbidden_paths=json_loads(row["forbidden_paths_json"], []),
        max_files_touched=int(row["max_files_touched"]),
        max_lines_changed=int(row["max_lines_changed"]),
    )


def create_scope_contract_for_gate_approval(
    work_order_id: str,
    approved_plan: dict[str, Any],
) -> ScopeContract:
    contract = build_scope_contract(work_order_id, approved_plan)
    return save_scope_contract(contract)
