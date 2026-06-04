"""
知识库管理器 — 跨层编排 Database + ChromaDB。

职责：
    - 知识库生命周期（创建/删除 → 同时操作 ChromaDB collection）
    - 文档生命周期（上传记录 + chunk 映射）
    - 成员与权限管理
    - 跨层删除（文档删除 → 清理 ChromaDB 向量 + chunks 映射）

用法:
    from rag.kb_manager import KBManager
    mgr = KBManager()
    kb = mgr.create_kb("开发部文档", owner_user, department="dev")
    doc = mgr.register_upload(kb_id, user, file_name, file_size, file_type)
    mgr.finish_upload(doc_id, chunk_ids=[...])
    mgr.delete_document(doc_id, user)
"""

import hashlib
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from rag.config import RAGConfig
from rag.database import get_db, Database


def _generate_collection_name(name: str) -> str:
    """为知识库生成唯一的 ChromaDB collection 名称。

    格式: kb_{short_uuid}（避免与手动创建的 collection 冲突）
    """
    short = uuid.uuid4().hex[:12]
    return f"kb_{short}"


def _hash_content(text: str) -> str:
    """计算文本 SHA256 哈希（用于去重）。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KBManager:
    """知识库管理器 — 协调 Database 与 VectorStore。"""

    def __init__(self, config: RAGConfig = None):
        self._config = config or RAGConfig.from_env()
        self._db: Optional[Database] = None

    @property
    def db(self) -> Database:
        if self._db is None:
            self._db = get_db(self._config.database.db_path or None)
        return self._db

    @property
    def store(self):
        """懒加载 VectorStore。"""
        from rag.store import VectorStore
        return VectorStore(self._config.store)

    # ══════════════════════════════════════════════════════
    #  知识库操作
    # ══════════════════════════════════════════════════════

    def create_kb(
        self,
        name: str,
        owner: dict,
        department: str = "",
        description: str = "",
    ) -> Dict:
        """
        创建知识库。

        参数:
            name: 知识库显示名称
            owner: 创建者用户信息 {"user_id": 1, "department": "dev", ...}
            department: 归属部门（默认使用 owner 的部门）
            description: 描述

        返回: 知识库完整信息
        """
        dept = department or owner.get("department", "dev")
        collection_name = _generate_collection_name(name)

        kb_id = self.db.create_kb(
            name=name,
            owner_id=owner["user_id"],
            department=dept,
            collection_name=collection_name,
            description=description,
        )

        # 确保 ChromaDB collection 存在（可选，vector 服务实际管理）
        try:
            self.store._ensure_client()
            self.store._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine", "rag_kb_name": name},
            )
        except ImportError as e:
            # ChromaDB/numpy 未安装（CLI 场景），collection 会在首次 add 时创建
            print(f"[KBManager] 注意: ChromaDB 未就绪，collection 将在向量服务启动时创建 ({e})")
        except Exception as e:
            # 其他错误不阻塞创建（collection 可能已存在或将在向量服务中创建）
            print(f"[KBManager] 警告: ChromaDB collection 创建失败（可能已存在）: {e}")

        return self.db.get_kb(kb_id=kb_id)

    def get_kb(self, kb_id: int, user: dict = None, check_access: bool = True) -> Optional[Dict]:
        """获取知识库信息（可选权限检查）。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            return None
        if check_access and user:
            from rag.auth import AuthManager
            AuthManager.require_kb_access(user, kb, "read")
        return kb

    def list_user_kbs(self, user: dict) -> List[Dict]:
        """列出用户有权访问的所有知识库。"""
        kbs = self.db.list_kbs(user_id=user["user_id"])
        # 管理员可看所有
        if user.get("role") == "admin":
            kbs = self.db.list_kbs(user_id=None)
        # 附加统计信息
        for kb in kbs:
            kb["doc_count"] = self.db.get_document_count(kb["id"])
            kb["member_count"] = len(self.db.list_kb_members(kb["id"]))
        return kbs

    def update_kb(self, kb_id: int, user: dict, **kwargs) -> bool:
        """更新知识库信息。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(user, kb, "admin")
        return self.db.update_kb(kb_id, **kwargs)

    def delete_kb(self, kb_id: int, user: dict) -> bool:
        """
        删除知识库（清空 ChromaDB collection + 删除所有元数据）。
        """
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(user, kb, "admin")

        collection_name = kb["collection_name"]

        # 1. 删除所有文档的 ChromaDB 向量
        docs = self.db.list_documents(kb_id=kb_id, include_deleted=True, limit=99999)
        for doc in docs:
            self._remove_chroma_vectors(doc["id"])

        # 2. 删除 ChromaDB collection
        try:
            self.store.drop_collection(collection_name)
        except Exception:
            pass

        # 3. 删除数据库记录（级联删除 documents, chunks, members）
        self.db.delete_kb(kb_id)
        return True

    # ══════════════════════════════════════════════════════
    #  成员操作
    # ══════════════════════════════════════════════════════

    def add_member(self, kb_id: int, user_id: int, permission: str, operator: dict) -> bool:
        """添加知识库成员（需 admin 权限）。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(operator, kb, "admin")
        return self.db.add_kb_member(kb_id, user_id, permission)

    def remove_member(self, kb_id: int, user_id: int, operator: dict) -> bool:
        """移除知识库成员。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        # owner 不能被移除
        if kb["owner_id"] == user_id:
            raise ValueError("不能移除知识库的创建者")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(operator, kb, "admin")
        return self.db.remove_kb_member(kb_id, user_id)

    def list_members(self, kb_id: int, user: dict) -> List[Dict]:
        """列出知识库成员。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(user, kb, "read")
        return self.db.list_kb_members(kb_id)

    # ══════════════════════════════════════════════════════
    #  文档操作
    # ══════════════════════════════════════════════════════

    def register_upload(
        self,
        kb_id: int,
        uploader: dict,
        file_name: str,
        file_size: int,
        file_type: str,
        file_path: str = "",
    ) -> int:
        """
        注册上传任务，返回 doc_id。

        状态: uploading → (外部处理) → done
        """
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(uploader, kb, "write")

        return self.db.create_document(
            kb_id=kb_id,
            uploader_id=uploader["user_id"],
            file_name=file_name,
            file_size=file_size,
            file_type=file_type,
            file_path=file_path,
            status="uploading",
        )

    def update_doc_status(self, doc_id: int, status: str, **kwargs):
        """更新文档处理状态。"""
        self.db.update_document(doc_id, status=status, **kwargs)

    def finish_upload(
        self,
        doc_id: int,
        texts: List[str],
        chroma_ids: List[str],
    ) -> int:
        """
        文档入库完成：写入 chunk 映射 + 更新状态。

        参数:
            doc_id: 文档 ID
            texts: chunk 文本列表
            chroma_ids: ChromaDB 返回的 chunk ID 列表

        返回: chunk 数量
        """
        # 写入 chunk 映射
        entries = []
        for i, (text, cid) in enumerate(zip(texts, chroma_ids)):
            entries.append({
                "chroma_id": cid,
                "chunk_index": i,
                "content_hash": _hash_content(text),
            })
        self.db.add_chunks(doc_id, entries)

        # 更新文档状态
        import datetime
        self.db.update_document(
            doc_id,
            status="done",
            chunk_count=len(entries),
            processed_at=datetime.datetime.now().isoformat(),
        )
        return len(entries)

    def fail_upload(self, doc_id: int, error: str):
        """标记上传失败。"""
        self.db.update_document(doc_id, status="error", error_message=error)

    def get_document(self, doc_id: int) -> Optional[Dict]:
        """获取文档详情。"""
        return self.db.get_document(doc_id)

    def list_documents(
        self,
        kb_id: int,
        user: dict,
        include_deleted: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict]:
        """列出知识库中的文档。"""
        kb = self.db.get_kb(kb_id=kb_id)
        if not kb:
            raise ValueError(f"知识库 {kb_id} 不存在")
        from rag.auth import AuthManager
        AuthManager.require_kb_access(user, kb, "read")
        return self.db.list_documents(
            kb_id=kb_id,
            include_deleted=include_deleted,
            limit=limit,
            offset=offset,
        )

    def delete_document(self, doc_id: int, user: dict) -> bool:
        """
        删除文档（清理向量 + 软删除记录）。

        流程:
            1. 权限检查（文档上传者或 kb admin）
            2. 获取所有关联 chroma_id
            3. 从 ChromaDB 删除向量
            4. 从 SQLite 删除 sparse 向量
            5. 删除 chunk 映射
            6. 软删除 documents 记录
        """
        doc = self.db.get_document(doc_id)
        if not doc:
            raise ValueError(f"文档 {doc_id} 不存在")

        kb = self.db.get_kb(kb_id=doc["kb_id"])
        if not kb:
            raise ValueError(f"知识库 {doc['kb_id']} 不存在")

        # 权限：上传者或 kb admin 可删
        if doc["uploader_id"] != user["user_id"]:
            from rag.auth import AuthManager
            AuthManager.require_kb_access(user, kb, "admin")

        # 清理 ChromaDB 向量
        self._remove_chroma_vectors(doc_id)

        # 软删除
        self.db.soft_delete_document(doc_id)
        return True

    def _remove_chroma_vectors(self, doc_id: int):
        """从 ChromaDB 和 SQLite 中移除文档的所有向量。"""
        chunks = self.db.get_chunks_by_doc(doc_id)
        if not chunks:
            return

        chroma_ids = [c["chroma_id"] for c in chunks]

        # 切换到文档所属的 collection 并删除
        try:
            doc = self.db.get_document(doc_id)
            if doc:
                kb = self.db.get_kb(kb_id=doc["kb_id"])
                if kb:
                    self.store.get_collection(kb["collection_name"])
                    self.store.delete(chroma_ids)
        except Exception as e:
            print(f"[KBManager] 警告: ChromaDB 向量删除失败: {e}")

        # 删除 chunk 映射
        self.db.delete_chunks_by_doc(doc_id)

    # ══════════════════════════════════════════════════════
    #  跨层检索（内部用）
    # ══════════════════════════════════════════════════════

    def get_collection_name(self, kb_id: int) -> Optional[str]:
        """获取知识库对应的 ChromaDB collection 名称。"""
        kb = self.db.get_kb(kb_id=kb_id)
        return kb["collection_name"] if kb else None

    def get_user_default_collection(self, user_id: int) -> Optional[str]:
        """获取用户第一个知识库的 collection 名称（默认选择）。"""
        kbs = self.db.list_kbs(user_id=user_id)
        if kbs:
            return kbs[0]["collection_name"]
        return None
