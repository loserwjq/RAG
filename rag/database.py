"""
关系型数据库模块 — SQLite 存储用户、知识库、文档上传记录、Chunk 映射、对话历史。

职责：
    - 建表 / 迁移
    - CRUD 操作（同步，适合单机场景）
    - 连接管理（WAL 模式，读写并发）

表结构：
    users            - 用户表（部门: dev / test / se）
    knowledge_bases  - 知识库（每个绑定一个 ChromaDB collection）
    kb_members       - 知识库成员（支持共享）
    documents        - 文档上传记录（含状态追踪）
    chunks           - chunk → chroma_id 映射（精确删除用）
    conversations    - 对话会话（多轮上下文持久化）
    messages         - 对话消息（支持分页 + 摘要压缩）

用法:
    from rag.database import Database
    db = Database()
    db.add_user("zhangsan", "hash...", "张三", "dev")
    kbid = db.create_kb("开发文档", owner_id=1, department="dev")
    doc_id = db.create_document(kbid, 1, "test.pdf", 1024, "pdf")
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── SQL 建表语句 ────────────────────────────────────────────

SCHEMA_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    display_name  TEXT    NOT NULL DEFAULT '',
    department    TEXT    NOT NULL CHECK(department IN ('dev', 'test', 'product')),
    role          TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('admin', 'user')),
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 知识库表
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL,
    collection_name TEXT    NOT NULL UNIQUE,
    owner_id        INTEGER NOT NULL REFERENCES users(id),
    department      TEXT    NOT NULL CHECK(department IN ('dev', 'test', 'product')),
    description     TEXT    NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_kb_owner ON knowledge_bases(owner_id);
CREATE INDEX IF NOT EXISTS idx_kb_dept  ON knowledge_bases(department);

-- 知识库成员表
CREATE TABLE IF NOT EXISTS kb_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id       INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    permission  TEXT    NOT NULL DEFAULT 'read' CHECK(permission IN ('read', 'write', 'admin')),
    joined_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(kb_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_kbm_user ON kb_members(user_id);
CREATE INDEX IF NOT EXISTS idx_kbm_kb   ON kb_members(kb_id);

-- 文档上传记录表
CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kb_id           INTEGER NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    uploader_id     INTEGER NOT NULL REFERENCES users(id),
    file_name       TEXT    NOT NULL,
    file_path       TEXT    NOT NULL,
    file_size       INTEGER NOT NULL DEFAULT 0,
    file_type       TEXT    NOT NULL DEFAULT '',
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT    NOT NULL DEFAULT 'uploading'
                        CHECK(status IN ('uploading', 'parsing', 'vectorizing', 'done', 'error')),
    error_message   TEXT,
    uploaded_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    processed_at    TEXT,
    deleted_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_docs_kb     ON documents(kb_id);
CREATE INDEX IF NOT EXISTS idx_docs_uploader ON documents(uploader_id);
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);

-- Chunk 映射表
CREATE TABLE IF NOT EXISTS chunks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chroma_id     TEXT    NOT NULL,
    chunk_index   INTEGER NOT NULL DEFAULT 0,
    content_hash  TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc   ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_chunks_chroma ON chunks(chroma_id);

-- 对话会话表
CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id),
    kb_id           INTEGER REFERENCES knowledge_bases(id) ON DELETE SET NULL,
    title           TEXT    NOT NULL DEFAULT '新对话',
    summary         TEXT    NOT NULL DEFAULT '',
    message_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_time ON conversations(updated_at DESC);

-- 对话消息表
CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
    content         TEXT    NOT NULL DEFAULT '',
    sources         TEXT    NOT NULL DEFAULT '[]',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
"""


class Database:
    """SQLite 数据库管理（单例 + 线程安全）。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, db_path: str = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        self._db_path = db_path or str(
            Path(__file__).parent.parent / "data" / "rag.db"
        )
        self._conn: Optional[sqlite3.Connection] = None
        self._local = threading.local()
        self._init_db()
        self._initialized = True

    # ── 连接管理 ──────────────────────────────────────────

    def _init_db(self):
        """创建数据库文件、启用 WAL、建表。"""
        db_file = Path(self._db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(db_file), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA_SQL)
        conn.commit()
        self._conn = conn

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接。"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def close(self):
        """关闭所有连接。"""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── 工具方法 ──────────────────────────────────────────

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        conn = self._get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur

    def _fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        cur = self._execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def _fetch_all(self, sql: str, params: tuple = ()) -> List[Dict]:
        cur = self._execute(sql, params)
        return [dict(row) for row in cur.fetchall()]

    # ══════════════════════════════════════════════════════
    #  用户操作
    # ══════════════════════════════════════════════════════

    def add_user(
        self,
        username: str,
        password_hash: str,
        display_name: str = "",
        department: str = "dev",
        role: str = "user",
    ) -> int:
        """创建用户，返回 user_id。"""
        cur = self._execute(
            """INSERT INTO users (username, password_hash, display_name, department, role)
               VALUES (?, ?, ?, ?, ?)""",
            (username, password_hash, display_name, department, role),
        )
        return cur.lastrowid

    def get_user(self, user_id: int = None, username: str = None) -> Optional[Dict]:
        """按 id 或用户名查找用户。"""
        if user_id:
            return self._fetch_one("SELECT * FROM users WHERE id = ?", (user_id,))
        if username:
            return self._fetch_one("SELECT * FROM users WHERE username = ?", (username,))
        return None

    def list_users(self, department: str = None) -> List[Dict]:
        """列出用户，可按部门筛选。"""
        if department:
            return self._fetch_all("SELECT * FROM users WHERE department = ? ORDER BY id", (department,))
        return self._fetch_all("SELECT * FROM users ORDER BY department, id")

    def update_user(self, user_id: int, **kwargs) -> bool:
        """更新用户字段。"""
        allowed = {"display_name", "department", "role", "password_hash"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        updates["updated_at"] = "datetime('now')"  # special handling below
        now_included = "updated_at" in updates
        set_parts = []
        params = []
        for k, v in updates.items():
            if k == "updated_at":
                set_parts.append(f"{k} = datetime('now')")
            else:
                set_parts.append(f"{k} = ?")
                params.append(v)
        params.append(user_id)
        self._execute(f"UPDATE users SET {', '.join(set_parts)} WHERE id = ?", tuple(params))
        return True

    def delete_user(self, user_id: int) -> bool:
        """删除用户。"""
        self._execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True

    # ══════════════════════════════════════════════════════
    #  知识库操作
    # ══════════════════════════════════════════════════════

    def create_kb(
        self,
        name: str,
        owner_id: int,
        department: str,
        collection_name: str,
        description: str = "",
    ) -> int:
        """创建知识库，返回 kb_id。"""
        cur = self._execute(
            """INSERT INTO knowledge_bases (name, collection_name, owner_id, department, description)
               VALUES (?, ?, ?, ?, ?)""",
            (name, collection_name, owner_id, department, description),
        )
        # 自动将 owner 添加为 admin 成员
        kb_id = cur.lastrowid
        self._execute(
            "INSERT INTO kb_members (kb_id, user_id, permission) VALUES (?, ?, 'admin')",
            (kb_id, owner_id),
        )
        return kb_id

    def get_kb(self, kb_id: int = None, collection_name: str = None) -> Optional[Dict]:
        """查询知识库。"""
        if kb_id:
            return self._fetch_one("SELECT * FROM knowledge_bases WHERE id = ?", (kb_id,))
        if collection_name:
            return self._fetch_one(
                "SELECT * FROM knowledge_bases WHERE collection_name = ?",
                (collection_name,),
            )
        return None

    def list_kbs(
        self,
        user_id: int = None,
        department: str = None,
        active_only: bool = True,
    ) -> List[Dict]:
        """列出知识库。

        若指定 user_id，返回该用户有权限的知识库（owner + 成员）。
        若指定 department，仅返回该部门的知识库。
        """
        if user_id:
            extra = "AND kb.is_active = 1" if active_only else ""
            return self._fetch_all(
                f"""SELECT DISTINCT kb.*
                    FROM knowledge_bases kb
                    LEFT JOIN kb_members m ON kb.id = m.kb_id
                    WHERE (kb.owner_id = ? OR m.user_id = ?) {extra}
                    ORDER BY kb.updated_at DESC""",
                (user_id, user_id),
            )

        conditions = []
        params = []
        if department:
            conditions.append("kb.department = ?")
            params.append(department)
        if active_only:
            conditions.append("kb.is_active = 1")
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return self._fetch_all(
            f"SELECT * FROM knowledge_bases kb {where} ORDER BY kb.updated_at DESC",
            tuple(params),
        )

    def update_kb(self, kb_id: int, **kwargs) -> bool:
        """更新知识库字段。"""
        allowed = {"name", "description", "is_active"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_parts = [f"{k} = ?" for k in updates]
        set_parts.append("updated_at = datetime('now')")
        params = list(updates.values()) + [kb_id]
        self._execute(
            f"UPDATE knowledge_bases SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        return True

    def delete_kb(self, kb_id: int) -> bool:
        """删除知识库（级联删除文档、chunks、成员）。"""
        self._execute("DELETE FROM knowledge_bases WHERE id = ?", (kb_id,))
        return True

    # ══════════════════════════════════════════════════════
    #  知识库成员操作
    # ══════════════════════════════════════════════════════

    def add_kb_member(self, kb_id: int, user_id: int, permission: str = "read") -> bool:
        """添加知识库成员。"""
        try:
            self._execute(
                "INSERT INTO kb_members (kb_id, user_id, permission) VALUES (?, ?, ?)",
                (kb_id, user_id, permission),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def remove_kb_member(self, kb_id: int, user_id: int) -> bool:
        """移除知识库成员。"""
        self._execute(
            "DELETE FROM kb_members WHERE kb_id = ? AND user_id = ?",
            (kb_id, user_id),
        )
        return True

    def list_kb_members(self, kb_id: int) -> List[Dict]:
        """列出知识库成员。"""
        return self._fetch_all(
            """SELECT u.id, u.username, u.display_name, u.department, m.permission, m.joined_at
               FROM kb_members m
               JOIN users u ON m.user_id = u.id
               WHERE m.kb_id = ?
               ORDER BY u.department, u.username""",
            (kb_id,),
        )

    def get_user_kb_permission(self, kb_id: int, user_id: int) -> Optional[str]:
        """获取用户对某知识库的权限级别（None = 无权限）。"""
        row = self._fetch_one(
            """SELECT permission FROM kb_members WHERE kb_id = ? AND user_id = ?""",
            (kb_id, user_id),
        )
        return row["permission"] if row else None

    # ══════════════════════════════════════════════════════
    #  文档操作
    # ══════════════════════════════════════════════════════

    def create_document(
        self,
        kb_id: int,
        uploader_id: int,
        file_name: str,
        file_size: int,
        file_type: str,
        file_path: str = "",
        status: str = "uploading",
    ) -> int:
        """创建文档记录，返回 doc_id。"""
        cur = self._execute(
            """INSERT INTO documents (kb_id, uploader_id, file_name, file_path, file_size, file_type, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (kb_id, uploader_id, file_name, file_path, file_size, file_type, status),
        )
        return cur.lastrowid

    def get_document(self, doc_id: int) -> Optional[Dict]:
        """获取文档详情。"""
        return self._fetch_one(
            """SELECT d.*, u.display_name AS uploader_name
               FROM documents d
               JOIN users u ON d.uploader_id = u.id
               WHERE d.id = ?""",
            (doc_id,),
        )

    def list_documents(
        self,
        kb_id: int = None,
        uploader_id: int = None,
        status: str = None,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """列出文档记录。"""
        conditions = []
        params = []

        if kb_id:
            conditions.append("d.kb_id = ?")
            params.append(kb_id)
        if uploader_id:
            conditions.append("d.uploader_id = ?")
            params.append(uploader_id)
        if status:
            conditions.append("d.status = ?")
            params.append(status)
        if not include_deleted:
            conditions.append("d.deleted_at IS NULL")

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        params.extend([limit, offset])
        return self._fetch_all(
            f"""SELECT d.*, u.display_name AS uploader_name
                FROM documents d
                JOIN users u ON d.uploader_id = u.id
                {where}
                ORDER BY d.uploaded_at DESC
                LIMIT ? OFFSET ?""",
            tuple(params),
        )

    def update_document(self, doc_id: int, **kwargs) -> bool:
        """更新文档字段。"""
        allowed = {"status", "chunk_count", "error_message", "processed_at"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_parts = [f"{k} = ?" for k in updates]
        params = list(updates.values()) + [doc_id]
        self._execute(
            f"UPDATE documents SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        return True

    def soft_delete_document(self, doc_id: int) -> bool:
        """软删除文档（标记 deleted_at）。"""
        self._execute(
            "UPDATE documents SET deleted_at = datetime('now') WHERE id = ?",
            (doc_id,),
        )
        return True

    def hard_delete_document(self, doc_id: int) -> bool:
        """硬删除文档及其 chunks。"""
        self._execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        return True

    def get_document_count(self, kb_id: int, include_deleted: bool = False) -> int:
        """统计知识库中的文档数。"""
        sql = "SELECT COUNT(*) AS cnt FROM documents WHERE kb_id = ?"
        if not include_deleted:
            sql += " AND deleted_at IS NULL"
        row = self._fetch_one(sql, (kb_id,))
        return row["cnt"] if row else 0

    # ══════════════════════════════════════════════════════
    #  Chunk 操作
    # ══════════════════════════════════════════════════════

    def add_chunks(self, doc_id: int, chunk_entries: List[Dict]) -> int:
        """批量添加 chunk 映射。

        chunk_entries: [{"chroma_id": "chunk_0", "chunk_index": 0, "content_hash": "sha256"}, ...]
        返回添加数量。
        """
        rows = [
            (doc_id, c["chroma_id"], c.get("chunk_index", 0), c.get("content_hash", ""))
            for c in chunk_entries
        ]
        conn = self._get_conn()
        conn.executemany(
            "INSERT INTO chunks (doc_id, chroma_id, chunk_index, content_hash) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        return len(rows)

    def get_chunks_by_doc(self, doc_id: int) -> List[Dict]:
        """获取文档的所有 chunk 映射。"""
        return self._fetch_all(
            "SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index",
            (doc_id,),
        )

    def delete_chunks_by_doc(self, doc_id: int) -> int:
        """删除文档的所有 chunk 映射，返回删除数。"""
        cur = self._execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        return cur.rowcount

    def get_chunk_count(self, kb_id: int = None) -> int:
        """统计 chunk 数。"""
        if kb_id:
            row = self._fetch_one(
                """SELECT COUNT(*) AS cnt FROM chunks c
                   JOIN documents d ON c.doc_id = d.id
                   WHERE d.kb_id = ? AND d.deleted_at IS NULL""",
                (kb_id,),
            )
        else:
            row = self._fetch_one("SELECT COUNT(*) AS cnt FROM chunks")
        return row["cnt"] if row else 0

    # ══════════════════════════════════════════════════════
    #  对话历史操作
    # ══════════════════════════════════════════════════════

    def create_conversation(self, user_id: int, kb_id: int = None, title: str = "新对话") -> int:
        """创建新对话，返回 conversation_id。"""
        cur = self._execute(
            """INSERT INTO conversations (user_id, kb_id, title)
               VALUES (?, ?, ?)""",
            (user_id, kb_id, title),
        )
        return cur.lastrowid

    def get_conversation(self, conv_id: int) -> Optional[Dict]:
        """获取对话信息。"""
        return self._fetch_one(
            "SELECT * FROM conversations WHERE id = ?", (conv_id,),
        )

    def list_conversations(self, user_id: int, limit: int = 50) -> List[Dict]:
        """列出用户最近的对话列表。"""
        return self._fetch_all(
            """SELECT id, title, kb_id, message_count, summary, created_at, updated_at
               FROM conversations
               WHERE user_id = ?
               ORDER BY updated_at DESC
               LIMIT ?""",
            (user_id, limit),
        )

    def update_conversation(self, conv_id: int, **kwargs) -> bool:
        """更新对话字段（title, summary, message_count, kb_id）。"""
        allowed = {"title", "summary", "message_count", "kb_id"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return False
        set_parts = [f"{k} = ?" for k in updates]
        set_parts.append("updated_at = datetime('now')")
        params = list(updates.values()) + [conv_id]
        self._execute(
            f"UPDATE conversations SET {', '.join(set_parts)} WHERE id = ?",
            tuple(params),
        )
        return True

    def delete_conversation(self, conv_id: int) -> bool:
        """删除对话（级联删除消息）。"""
        self._execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        return True

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        sources: str = "[]",
    ) -> int:
        """添加一条消息，返回 message_id。同时更新对话的 message_count 和时间。"""
        cur = self._execute(
            """INSERT INTO messages (conversation_id, role, content, sources)
               VALUES (?, ?, ?, ?)""",
            (conversation_id, role, content, sources),
        )
        msg_id = cur.lastrowid
        # 更新计数和修改时间
        self._execute(
            """UPDATE conversations
               SET message_count = (SELECT COUNT(*) FROM messages WHERE conversation_id = ?),
                   updated_at = datetime('now')
               WHERE id = ?""",
            (conversation_id, conversation_id),
        )
        return msg_id

    def add_user_message(self, conv_id: int, content: str) -> int:
        """添加用户消息（便捷方法）。"""
        return self.add_message(conv_id, "user", content, "[]")

    def add_assistant_message(self, conv_id: int, content: str, sources: str = "[]") -> int:
        """添加助手消息（便捷方法）。"""
        return self.add_message(conv_id, "assistant", content, sources)

    def get_messages(
        self,
        conversation_id: int,
        before_id: int = None,
        limit: int = 50,
    ) -> List[Dict]:
        """分页获取消息列表。

        参数:
            conversation_id: 对话 ID
            before_id: 获取此 ID 之前的消息（向上翻页）
            limit: 每页数量
        """
        if before_id:
            return self._fetch_all(
                """SELECT id, conversation_id, role, content, sources, created_at
                   FROM messages
                   WHERE conversation_id = ? AND id < ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (conversation_id, before_id, limit),
            )[::-1]  # 反转回正序
        else:
            return self._fetch_all(
                """SELECT id, conversation_id, role, content, sources, created_at
                   FROM messages
                   WHERE conversation_id = ?
                   ORDER BY id DESC
                   LIMIT ?""",
                (conversation_id, limit),
            )[::-1]

    def get_last_messages(self, conversation_id: int, count: int) -> List[Dict]:
        """获取最近 N 条消息（用于构建 LLM 上下文）。"""
        rows = self._fetch_all(
            """SELECT role, content FROM messages
               WHERE conversation_id = ?
               ORDER BY id DESC
               LIMIT ?""",
            (conversation_id, count),
        )
        return rows[::-1]

    def delete_messages_by_conversation(self, conv_id: int) -> int:
        """删除对话下所有消息。"""
        cur = self._execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        return cur.rowcount

    # ══════════════════════════════════════════════════════
    #  统计与工具
    # ══════════════════════════════════════════════════════

    def get_stats(self, kb_id: int = None) -> Dict:
        """获取统计信息。"""
        stats = {
            "users": self._fetch_one("SELECT COUNT(*) AS cnt FROM users")["cnt"],
            "knowledge_bases": self._fetch_one(
                "SELECT COUNT(*) AS cnt FROM knowledge_bases WHERE is_active = 1"
            )["cnt"],
        }
        if kb_id:
            stats["documents"] = self.get_document_count(kb_id)
            stats["chunks"] = self.get_chunk_count(kb_id)
        else:
            stats["documents"] = self._fetch_one(
                "SELECT COUNT(*) AS cnt FROM documents WHERE deleted_at IS NULL"
            )["cnt"]
            stats["chunks"] = self._fetch_one("SELECT COUNT(*) AS cnt FROM chunks")["cnt"]
        return stats


# ── 便捷工厂 ──────────────────────────────────────────────

def get_db(db_path: str = None) -> Database:
    """获取 Database 单例。"""
    return Database(db_path)
