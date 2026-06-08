from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import ACTIVE_PHASES, ApprovalState, GatewayConversationState, GitHubIssue, GodmodeSession, LoopState, utc_now_iso


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
        conn = self._connect()
        try:
            with conn:
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS godmode_sessions (
                        conversation_id TEXT PRIMARY KEY,
                        repo TEXT NOT NULL,
                        status TEXT NOT NULL,
                        iterations INTEGER NOT NULL,
                        failures INTEGER NOT NULL,
                        last_issue_number INTEGER,
                        last_issue_title TEXT,
                        stop_reason TEXT,
                        evidence TEXT NOT NULL DEFAULT '[]',
                        started_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS gateway_conversations (
                        conversation_id TEXT PRIMARY KEY,
                        platform TEXT NOT NULL,
                        guild_id TEXT,
                        channel_id TEXT,
                        thread_id TEXT,
                        repo TEXT,
                        latest_user_goal TEXT,
                        latest_summary TEXT,
                        active_issue_number INTEGER,
                        active_issue_title TEXT,
                        active_issue_labels TEXT NOT NULL DEFAULT '[]',
                        compaction_count INTEGER NOT NULL DEFAULT 0,
                        continuation_of TEXT,
                        continuation_conversation_id TEXT,
                        continuation_thread_id TEXT,
                        original_conversation_name TEXT,
                        continuation_sequence INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                self._ensure_gateway_conversation_column(
                    conn,
                    name="original_conversation_name",
                    definition="TEXT",
                )
                self._ensure_gateway_conversation_column(
                    conn,
                    name="continuation_sequence",
                    definition="INTEGER NOT NULL DEFAULT 1",
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_gateway_conversations_platform_updated "
                    "ON gateway_conversations(platform, updated_at)"
                )
        finally:
            conn.close()

    @staticmethod
    def _ensure_gateway_conversation_column(conn: sqlite3.Connection, *, name: str, definition: str) -> None:
        try:
            conn.execute(f"ALTER TABLE gateway_conversations ADD COLUMN {name} {definition}")
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise

    def save_loop(self, loop: LoopState) -> None:
        updated_at = utc_now_iso()
        conn = self._connect()
        try:
            with conn:
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
        finally:
            conn.close()

    def get_loop(self, loop_id: str) -> LoopState | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM loops WHERE loop_id = ?", (loop_id,)).fetchone()
        finally:
            conn.close()
        return self._row_to_loop(row) if row else None

    def get_active_loop(self, repo: str) -> LoopState | None:
        placeholders = ",".join("?" for _ in ACTIVE_PHASES)
        query = f"SELECT * FROM loops WHERE repo = ? AND phase IN ({placeholders}) ORDER BY updated_at DESC LIMIT 1"
        conn = self._connect()
        try:
            row = conn.execute(query, (repo, *ACTIVE_PHASES)).fetchone()
        finally:
            conn.close()
        return self._row_to_loop(row) if row else None

    def save_godmode_session(self, session: GodmodeSession) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO godmode_sessions (
                        conversation_id, repo, status, iterations, failures, last_issue_number,
                        last_issue_title, stop_reason, evidence, started_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(conversation_id) DO UPDATE SET
                        repo=excluded.repo,
                        status=excluded.status,
                        iterations=excluded.iterations,
                        failures=excluded.failures,
                        last_issue_number=excluded.last_issue_number,
                        last_issue_title=excluded.last_issue_title,
                        stop_reason=excluded.stop_reason,
                        evidence=excluded.evidence,
                        updated_at=excluded.updated_at
                    """,
                    (
                        session.conversation_id,
                        session.repo,
                        session.status,
                        session.iterations,
                        session.failures,
                        session.last_issue_number,
                        session.last_issue_title,
                        session.stop_reason,
                        json.dumps(session.evidence),
                        session.started_at,
                        session.updated_at,
                    ),
                )
        finally:
            conn.close()

    def get_godmode_session(self, conversation_id: str) -> GodmodeSession | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT * FROM godmode_sessions WHERE conversation_id = ?", (conversation_id,)).fetchone()
        finally:
            conn.close()
        return self._row_to_godmode_session(row) if row else None

    def increment_gateway_compaction(
        self,
        *,
        conversation_id: str,
        platform: str,
        guild_id: str | None = None,
        channel_id: str | None = None,
        thread_id: str | None = None,
        conversation_name: str | None = None,
        repo: str | None = None,
        latest_user_goal: str | None = None,
        latest_summary: str | None = None,
        active_issue_number: int | None = None,
        active_issue_title: str | None = None,
        active_issue_labels: list[str] | None = None,
    ) -> GatewayConversationState:
        updated_at = utc_now_iso()
        labels = active_issue_labels or []
        conn = self._connect()
        try:
            with conn:
                existing = conn.execute(
                    "SELECT * FROM gateway_conversations WHERE conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                if existing is None:
                    state = GatewayConversationState(
                        conversation_id=conversation_id,
                        platform=platform,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        thread_id=thread_id,
                        repo=repo,
                        latest_user_goal=latest_user_goal,
                        latest_summary=latest_summary,
                        active_issue_number=active_issue_number,
                        active_issue_title=active_issue_title,
                        active_issue_labels=labels,
                        compaction_count=1,
                        original_conversation_name=conversation_name,
                        created_at=updated_at,
                        updated_at=updated_at,
                    )
                else:
                    previous = self._row_to_gateway_conversation(existing)
                    state = GatewayConversationState(
                        conversation_id=previous.conversation_id,
                        platform=platform,
                        guild_id=guild_id or previous.guild_id,
                        channel_id=channel_id or previous.channel_id,
                        thread_id=thread_id or previous.thread_id,
                        repo=repo or previous.repo,
                        latest_user_goal=latest_user_goal or previous.latest_user_goal,
                        latest_summary=latest_summary or previous.latest_summary,
                        active_issue_number=active_issue_number or previous.active_issue_number,
                        active_issue_title=active_issue_title or previous.active_issue_title,
                        active_issue_labels=labels or previous.active_issue_labels,
                        compaction_count=previous.compaction_count + 1,
                        continuation_of=previous.continuation_of,
                        continuation_conversation_id=previous.continuation_conversation_id,
                        continuation_thread_id=previous.continuation_thread_id,
                        original_conversation_name=previous.original_conversation_name or conversation_name,
                        continuation_sequence=previous.continuation_sequence,
                        created_at=previous.created_at,
                        updated_at=updated_at,
                    )
                self._save_gateway_conversation(conn, state)
        finally:
            conn.close()
        return state

    def get_gateway_conversation(self, conversation_id: str) -> GatewayConversationState | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM gateway_conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
        finally:
            conn.close()
        return self._row_to_gateway_conversation(row) if row else None

    def create_gateway_continuation(
        self,
        *,
        old_conversation_id: str,
        new_state: GatewayConversationState,
        continuation_thread_id: str | None = None,
    ) -> None:
        updated_at = utc_now_iso()
        conn = self._connect()
        try:
            with conn:
                self._save_gateway_conversation(conn, new_state)
                conn.execute(
                    """
                    UPDATE gateway_conversations
                    SET continuation_conversation_id = ?,
                        continuation_thread_id = ?,
                        updated_at = ?
                    WHERE conversation_id = ?
                    """,
                    (new_state.conversation_id, continuation_thread_id, updated_at, old_conversation_id),
                )
        finally:
            conn.close()

    @staticmethod
    def _row_to_godmode_session(row: sqlite3.Row) -> GodmodeSession:
        return GodmodeSession(
            conversation_id=row["conversation_id"],
            repo=row["repo"],
            status=row["status"],
            iterations=int(row["iterations"]),
            failures=int(row["failures"]),
            last_issue_number=row["last_issue_number"],
            last_issue_title=row["last_issue_title"],
            stop_reason=row["stop_reason"],
            evidence=json.loads(row["evidence"]),
            started_at=row["started_at"],
            updated_at=row["updated_at"],
        )

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

    @staticmethod
    def _save_gateway_conversation(conn: sqlite3.Connection, state: GatewayConversationState) -> None:
        conn.execute(
            """
            INSERT INTO gateway_conversations (
                conversation_id, platform, guild_id, channel_id, thread_id, repo,
                latest_user_goal, latest_summary, active_issue_number, active_issue_title,
                active_issue_labels, compaction_count, continuation_of,
                continuation_conversation_id, continuation_thread_id, original_conversation_name,
                continuation_sequence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                platform=excluded.platform,
                guild_id=excluded.guild_id,
                channel_id=excluded.channel_id,
                thread_id=excluded.thread_id,
                repo=excluded.repo,
                latest_user_goal=excluded.latest_user_goal,
                latest_summary=excluded.latest_summary,
                active_issue_number=excluded.active_issue_number,
                active_issue_title=excluded.active_issue_title,
                active_issue_labels=excluded.active_issue_labels,
                compaction_count=excluded.compaction_count,
                continuation_of=excluded.continuation_of,
                continuation_conversation_id=excluded.continuation_conversation_id,
                continuation_thread_id=excluded.continuation_thread_id,
                original_conversation_name=excluded.original_conversation_name,
                continuation_sequence=excluded.continuation_sequence,
                updated_at=excluded.updated_at
            """,
            (
                state.conversation_id,
                state.platform,
                state.guild_id,
                state.channel_id,
                state.thread_id,
                state.repo,
                state.latest_user_goal,
                state.latest_summary,
                state.active_issue_number,
                state.active_issue_title,
                json.dumps(state.active_issue_labels),
                state.compaction_count,
                state.continuation_of,
                state.continuation_conversation_id,
                state.continuation_thread_id,
                state.original_conversation_name,
                state.continuation_sequence,
                state.created_at,
                state.updated_at,
            ),
        )

    @staticmethod
    def _row_to_gateway_conversation(row: sqlite3.Row) -> GatewayConversationState:
        return GatewayConversationState(
            conversation_id=row["conversation_id"],
            platform=row["platform"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            thread_id=row["thread_id"],
            repo=row["repo"],
            latest_user_goal=row["latest_user_goal"],
            latest_summary=row["latest_summary"],
            active_issue_number=row["active_issue_number"],
            active_issue_title=row["active_issue_title"],
            active_issue_labels=json.loads(row["active_issue_labels"]),
            compaction_count=row["compaction_count"],
            continuation_of=row["continuation_of"],
            continuation_conversation_id=row["continuation_conversation_id"],
            continuation_thread_id=row["continuation_thread_id"],
            original_conversation_name=row["original_conversation_name"],
            continuation_sequence=int(row["continuation_sequence"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
