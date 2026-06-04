from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ACTIVE_PHASES, ApprovalState, GitHubIssue, LoopState, utc_now_iso


class StateStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loops (
                    loop_id TEXT PRIMARY KEY,
                    repo TEXT NOT NULL,
                    issue_number INTEGER NOT NULL,
                    issue_title TEXT NOT NULL,
                    issue_body TEXT NOT NULL DEFAULT '',
                    issue_labels TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    executor TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    approval_intent TEXT,
                    approval_status TEXT,
                    approval_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_loops_repo_phase ON loops(repo, phase)")

    def save_loop(self, loop: LoopState) -> None:
        updated_at = utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO loops (
                    loop_id, repo, issue_number, issue_title, issue_body, issue_labels,
                    branch, executor, phase, approval_intent, approval_status, approval_id,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(loop_id) DO UPDATE SET
                    repo=excluded.repo,
                    issue_number=excluded.issue_number,
                    issue_title=excluded.issue_title,
                    issue_body=excluded.issue_body,
                    issue_labels=excluded.issue_labels,
                    branch=excluded.branch,
                    executor=excluded.executor,
                    phase=excluded.phase,
                    approval_intent=excluded.approval_intent,
                    approval_status=excluded.approval_status,
                    approval_id=excluded.approval_id,
                    updated_at=excluded.updated_at
                """,
                (
                    loop.loop_id,
                    loop.repo,
                    loop.issue.number,
                    loop.issue.title,
                    loop.issue.body,
                    json.dumps(loop.issue.labels),
                    loop.branch,
                    loop.executor,
                    loop.phase,
                    loop.approval.intent,
                    loop.approval.status,
                    loop.approval.approval_id,
                    loop.created_at,
                    updated_at,
                ),
            )

    def get_loop(self, loop_id: str) -> LoopState | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM loops WHERE loop_id = ?", (loop_id,)).fetchone()
        return self._row_to_loop(row) if row else None

    def get_active_loop(self, repo: str) -> LoopState | None:
        placeholders = ",".join("?" for _ in ACTIVE_PHASES)
        query = f"SELECT * FROM loops WHERE repo = ? AND phase IN ({placeholders}) ORDER BY updated_at DESC LIMIT 1"
        with self._connect() as conn:
            row = conn.execute(query, (repo, *ACTIVE_PHASES)).fetchone()
        return self._row_to_loop(row) if row else None

    @staticmethod
    def _row_to_loop(row: sqlite3.Row) -> LoopState:
        issue = GitHubIssue(
            number=int(row["issue_number"]),
            title=row["issue_title"],
            body=row["issue_body"],
            labels=json.loads(row["issue_labels"]),
        )
        approval = ApprovalState(
            intent=row["approval_intent"],
            status=row["approval_status"],
            approval_id=row["approval_id"],
        )
        return LoopState(
            loop_id=row["loop_id"],
            repo=row["repo"],
            issue=issue,
            branch=row["branch"],
            executor=row["executor"],
            phase=row["phase"],
            approval=approval,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
