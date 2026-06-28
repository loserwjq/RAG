"""
API 网关 — 多用户知识库系统。

端口: 8005
功能:
    - 用户认证（Dev Mode / JWT）
    - 知识库 CRUD（用户隔离 + 部门可见）
    - 文档上传 / 列表 / 删除
    - 多轮对话（SSE 流式 + 知识库隔离）
    - 健康检查 / 服务状态
"""

import sys
import os
import re
import json
import asyncio
import uuid
import mimetypes
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, Request, UploadFile, File, Form, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Dict

from services.logger import setup_service
from services.client import ServiceClient
from rag.config import RAGConfig
from rag.database import get_db
from rag.auth import AuthManager, hash_password, verify_password, get_auth_manager
from rag.kb_manager import KBManager

app = FastAPI(title="RAG Gateway - Multi-User Knowledge Base")
dify_security = HTTPBearer(scheme_name="Dify API Key", description="输入 Dify API Key，默认: dify-rag-secret-key")
logger = setup_service(app, "gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 全局服务 ────────────────────────────────────────────────

config = RAGConfig.from_env()
client = ServiceClient(logger)
auth_mgr = get_auth_manager(config.auth)
kb_mgr = KBManager(config)

# ── 上传任务状态存储 ────────────────────────────────────────

task_store: Dict[str, dict] = {}
task_lock = asyncio.Lock()

# ── 上传配置 ────────────────────────────────────────────────

BASE_DIR = Path(os.path.dirname(os.path.dirname(__file__)))
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_DIR = BASE_DIR / "output" / "_previews"
PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".html", ".htm",
    ".md", ".markdown", ".txt",
}
PREVIEWABLE_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
OFFICE_EXTENSIONS = {".docx", ".ppt", ".pptx", ".xlsx", ".xls"}


# ═══════════════════════════════════════════════════════════
#  请求模型
# ═══════════════════════════════════════════════════════════

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    top_k: Optional[int] = 10
    kb_id: Optional[int] = None  # 指定知识库
    conversation_id: Optional[int] = None  # 对话 ID（持久化 + 上下文管理）


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    department: str = "dev"


class CreateKBRequest(BaseModel):
    name: str
    department: str = ""
    description: str = ""


class UpdateKBRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class AddMemberRequest(BaseModel):
    user_id: int
    permission: str = "read"  # read / write / admin


# ═══════════════════════════════════════════════════════════
#  工具函数
# ═══════════════════════════════════════════════════════════

def _get_user(request: Request) -> dict:
    """从请求中提取当前用户。"""
    return auth_mgr.get_current_user(request)


def _build_context(results: List[Dict]) -> str:
    """将检索结果拼接为 LLM 上下文。"""
    parts = []
    for i, r in enumerate(results, 1):
        doc_name = r.get("metadata", {}).get("doc_name", f"文档{i}")
        parts.append(f"[参考文档: {doc_name}] (相关度: {r['score']:.3f})\n{r['content']}")
    return "\n\n---\n\n".join(parts)


def _to_int(value) -> Optional[int]:
    """宽松转换 metadata 中的数字字段。"""
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _page_number(metadata: Dict) -> Optional[int]:
    page_idx = _to_int(metadata.get("page_idx"))
    if page_idx is None or page_idx < 0:
        return None
    return page_idx + 1


def _find_source_document(db, metadata: Dict, fallback_kb_id: Optional[int], cache: Dict):
    """根据检索 metadata 找回 documents 表记录，用于生成原文链接。"""
    doc_id = _to_int(metadata.get("doc_id"))
    if doc_id:
        key = ("id", doc_id)
        if key not in cache:
            cache[key] = db.get_document(doc_id)
        return cache[key]

    doc_name = metadata.get("doc_name")
    kb_id = _to_int(metadata.get("kb_id")) or fallback_kb_id
    if not doc_name or not kb_id:
        return None

    key = ("name", kb_id, doc_name)
    if key in cache:
        return cache[key]

    doc_stem = Path(str(doc_name)).stem
    matched = None
    for doc in db.list_documents(kb_id=kb_id, include_deleted=False, limit=1000):
        file_name = doc.get("file_name", "")
        if file_name == doc_name or Path(file_name).stem in (doc_name, doc_stem):
            matched = doc
            break

    cache[key] = matched
    return matched


def _document_file_url(doc: Dict, metadata: Dict) -> str:
    """生成前端可直接打开的原文 URL。PDF 附带页码锚点。"""
    url = f"/api/documents/{doc['id']}/file"
    page = _page_number(metadata)
    if doc.get("file_type") == "pdf" and page:
        url += f"#page={page}"
    return url


def _document_preview_url(doc: Dict, metadata: Dict) -> str:
    """生成统一预览 URL。PDF 附带页码锚点。"""
    url = f"/api/documents/{doc['id']}/preview"
    page = _page_number(metadata)
    if doc.get("file_type") == "pdf" and page:
        url += f"#page={page}"
    return url


def _build_sources(results: List[Dict], db, fallback_kb_id: Optional[int], top_k: int) -> List[Dict]:
    """将检索结果转成前端来源卡片数据，并补充原文跳转信息。"""
    sources = []
    doc_cache = {}

    for r in results[:top_k]:
        metadata = dict(r.get("metadata") or {})
        doc = _find_source_document(db, metadata, fallback_kb_id, doc_cache)
        page = _page_number(metadata)

        item = {
            "content": r.get("content", "")[:800],
            "score": r.get("score", 0),
            "dense_score": r.get("dense_score"),
            "sparse_score": r.get("sparse_score"),
            "rerank_score": r.get("rerank_score"),
            "original_rank": r.get("original_rank"),
            "metadata": metadata,
        }

        if doc:
            metadata.update({
                "doc_id": doc["id"],
                "file_name": doc.get("file_name", ""),
                "file_type": doc.get("file_type", ""),
            })
            item.update({
                "file_url": _document_file_url(doc, metadata),
                "preview_url": _document_preview_url(doc, metadata),
                "file_name": doc.get("file_name", ""),
            })
            if page:
                item["page_number"] = page

        sources.append(item)

    return sources


def _resolve_document_file(doc_id: int, request: Request):
    """校验权限并解析上传文件路径。"""
    user = _get_user(request)
    doc = kb_mgr.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb = kb_mgr.get_kb(doc["kb_id"], user, check_access=True)
    if not kb:
        raise HTTPException(status_code=403, detail="无权访问该文档")

    file_path = Path(doc.get("file_path") or "")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="原文件不存在或已被移动")

    resolved = file_path.resolve()
    upload_root = UPLOAD_DIR.resolve()
    try:
        resolved.relative_to(upload_root)
    except ValueError:
        raise HTTPException(status_code=403, detail="文件路径不在上传目录")

    return doc, resolved


def _content_disposition(mode: str, filename: str) -> str:
    return f"{mode}; filename*=UTF-8''{quote(filename)}"


def _file_response(path: Path, filename: str, disposition: str = "inline", extra_headers: Dict = None):
    media_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    headers = {
        "Content-Disposition": _content_disposition(disposition, filename),
    }
    if extra_headers:
        headers.update(extra_headers)
    return FileResponse(path=str(path), media_type=media_type, headers=headers)


def _find_office_converter() -> Optional[str]:
    for exe in ("soffice", "libreoffice"):
        found = shutil.which(exe)
        if found:
            return found
    return None


def _convert_office_to_pdf(source: Path, doc_id: int) -> Optional[Path]:
    """尝试用 LibreOffice/soffice 转 PDF，失败返回 None。"""
    converter = _find_office_converter()
    if not converter:
        return None

    target_dir = PREVIEW_DIR / str(doc_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_pdf = target_dir / f"doc_{doc_id}.pdf"

    if target_pdf.exists() and target_pdf.stat().st_mtime >= source.stat().st_mtime:
        return target_pdf

    for old_pdf in target_dir.glob("*.pdf"):
        try:
            old_pdf.unlink()
        except OSError:
            pass

    try:
        result = subprocess.run(
            [
                converter,
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(target_dir),
                str(source),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except Exception as e:
        logger.warning(f"Office 转 PDF 失败: {source.name}: {e}")
        return None

    generated = target_dir / f"{source.stem}.pdf"
    if result.returncode != 0 or not generated.exists():
        detail = (result.stderr or result.stdout or "").strip()
        logger.warning(f"Office 转 PDF 失败: {source.name}: {detail[:300]}")
        return None

    if generated != target_pdf:
        shutil.move(str(generated), str(target_pdf))
    return target_pdf


# ═══════════════════════════════════════════════════════════
#  认证接口
# ═══════════════════════════════════════════════════════════

@app.post("/api/auth/login")
async def login(req: LoginRequest):
    """用户登录。

    返回: {user_id, username, display_name, department, role, token?}
    """
    db = get_db()
    user = db.get_user(username=req.username)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    result = {
        "user_id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "department": user["department"],
        "role": user["role"],
    }

    # JWT 模式：返回 token
    if not config.auth.dev_mode:
        result["token"] = auth_mgr.create_token(user["id"], user["username"])

    return result


@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """注册新用户（仅 Dev Mode 或管理员可调用）。"""
    db = get_db()

    # 检查重名
    existing = db.get_user(username=req.username)
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    if req.department not in ("dev", "test", "product"):
        raise HTTPException(status_code=400, detail="部门必须是 dev / test / se")

    pw_hash = hash_password(req.password)
    user_id = db.add_user(
        username=req.username,
        password_hash=pw_hash,
        display_name=req.display_name or req.username,
        department=req.department,
    )

    logger.info(f"新用户注册: {req.username} (id={user_id}, dept={req.department})")

    return {
        "user_id": user_id,
        "username": req.username,
        "display_name": req.display_name or req.username,
        "department": req.department,
        "role": "user",
    }


# ═══════════════════════════════════════════════════════════
#  用户管理接口
# ═══════════════════════════════════════════════════════════

@app.get("/api/users")
async def list_users(request: Request, department: str = None):
    """列出所有用户（按部门筛选）。"""
    user = _get_user(request)
    db = get_db()

    # 非管理员只能看本部门
    if user["role"] != "admin" and department is None:
        department = user["department"]

    return {"users": db.list_users(department=department)}


@app.get("/api/users/{user_id}")
async def get_user(user_id: int, request: Request):
    """获取用户详情。"""
    _get_user(request)
    db = get_db()
    u = db.get_user(user_id=user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 移除密码哈希
    u.pop("password_hash", None)
    return u


@app.get("/api/users/me")
async def get_me(request: Request):
    """获取当前用户信息。"""
    user = _get_user(request)
    db = get_db()
    u = db.get_user(user_id=user["user_id"])
    if u:
        u.pop("password_hash", None)
        u.update(user)
    return u


# ═══════════════════════════════════════════════════════════
#  知识库管理接口
# ═══════════════════════════════════════════════════════════

@app.post("/api/kb")
async def create_kb(req: CreateKBRequest, request: Request):
    """创建知识库。"""
    user = _get_user(request)

    kb = kb_mgr.create_kb(
        name=req.name,
        owner=user,
        department=req.department or user["department"],
        description=req.description,
    )

    logger.info(f"知识库创建: id={kb['id']} name={kb['name']} "
                f"collection={kb['collection_name']} owner={user['user_id']}")

    return {
        "id": kb["id"],
        "name": kb["name"],
        "collection_name": kb["collection_name"],
        "department": kb["department"],
        "description": kb["description"],
        "owner_id": kb["owner_id"],
        "created_at": kb["created_at"],
    }


@app.get("/api/kb")
async def list_kbs(request: Request):
    """列出当前用户有权访问的知识库。"""
    user = _get_user(request)
    kbs = kb_mgr.list_user_kbs(user)

    # 附加成员列表
    for kb in kbs:
        kb["members"] = kb_mgr.list_members(kb["id"], user)

    return {"knowledge_bases": kbs}


@app.get("/api/kb/{kb_id}")
async def get_kb(kb_id: int, request: Request):
    """获取知识库详情。"""
    user = _get_user(request)
    kb = kb_mgr.get_kb(kb_id, user, check_access=True)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    kb["members"] = kb_mgr.list_members(kb_id, user)
    kb["doc_count"] = kb_mgr.db.get_document_count(kb_id)
    return kb


@app.put("/api/kb/{kb_id}")
async def update_kb(kb_id: int, req: UpdateKBRequest, request: Request):
    """更新知识库信息。"""
    user = _get_user(request)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        kb_mgr.update_kb(kb_id, user, **updates)
    return {"status": "ok"}


@app.delete("/api/kb/{kb_id}")
async def delete_kb(kb_id: int, request: Request):
    """删除知识库（同时清理所有向量数据）。"""
    user = _get_user(request)
    kb = kb_mgr.get_kb(kb_id, user, check_access=False)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    logger.info(f"删除知识库: id={kb_id} name={kb['name']} operator={user['user_id']}")

    # 1. 通过 vector-service 删除 collection（删除所有向量）
    try:
        await client.call("vector", f"/collection/{kb['collection_name']}", method="DELETE")
    except Exception as e:
        logger.warning(f"删除 vector collection 失败（可能不存在）: {e}")

    # 2. 清理本地数据库（级联删除 documents、chunks、members）
    kb_mgr.db.delete_kb(kb_id)

    return {"status": "ok", "deleted": kb_id}


# ── 知识库成员 ─────────────────────────────────────────────

@app.post("/api/kb/{kb_id}/members")
async def add_member(kb_id: int, req: AddMemberRequest, request: Request):
    """添加知识库成员。"""
    user = _get_user(request)
    if req.permission not in ("read", "write", "admin"):
        raise HTTPException(status_code=400, detail="权限必须是 read / write / admin")

    ok = kb_mgr.add_member(kb_id, req.user_id, req.permission, user)
    if not ok:
        raise HTTPException(status_code=400, detail="该用户已是成员")
    return {"status": "ok"}


@app.delete("/api/kb/{kb_id}/members/{member_id}")
async def remove_member(kb_id: int, member_id: int, request: Request):
    """移除知识库成员。"""
    user = _get_user(request)
    kb_mgr.remove_member(kb_id, member_id, user)
    return {"status": "ok"}


@app.get("/api/kb/{kb_id}/members")
async def list_members(kb_id: int, request: Request):
    """列出知识库成员。"""
    user = _get_user(request)
    return {"members": kb_mgr.list_members(kb_id, user)}


# ═══════════════════════════════════════════════════════════
#  文档管理接口
# ═══════════════════════════════════════════════════════════

@app.get("/api/kb/{kb_id}/documents")
async def list_documents(
    kb_id: int,
    request: Request,
    limit: int = 100,
    offset: int = 0,
):
    """列出知识库中的文档上传记录。"""
    user = _get_user(request)
    docs = kb_mgr.list_documents(kb_id, user, limit=limit, offset=offset)
    return {"documents": docs, "total": len(docs)}


@app.get("/api/documents/{doc_id}")
async def get_document(doc_id: int, request: Request):
    """获取文档详情（含 chunk 信息）。"""
    user = _get_user(request)
    doc = kb_mgr.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 权限检查
    kb = kb_mgr.get_kb(doc["kb_id"], user, check_access=True)
    if not kb:
        raise HTTPException(status_code=403, detail="无权访问该文档")

    # 附加 chunk 列表
    doc["chunks"] = kb_mgr.db.get_chunks_by_doc(doc_id)
    return doc


@app.get("/api/documents/{doc_id}/file")
async def open_document_file(doc_id: int, request: Request):
    """打开原始上传文件。"""
    doc, resolved = _resolve_document_file(doc_id, request)
    file_name = doc.get("file_name") or resolved.name
    return _file_response(resolved, file_name, disposition="inline")


@app.get("/api/documents/{doc_id}/preview")
async def preview_document_file(doc_id: int, request: Request):
    """打开统一预览：PDF/TXT/图片直接预览，Office 尝试转 PDF，失败则下载原文件。"""
    doc, resolved = _resolve_document_file(doc_id, request)
    file_name = doc.get("file_name") or resolved.name
    ext = resolved.suffix.lower()

    if ext in PREVIEWABLE_EXTENSIONS:
        return _file_response(
            resolved,
            file_name,
            disposition="inline",
            extra_headers={"X-Preview-Mode": "preview"},
        )

    if ext in OFFICE_EXTENSIONS:
        pdf_path = _convert_office_to_pdf(resolved, doc_id)
        if pdf_path:
            preview_name = f"{Path(file_name).stem}.pdf"
            return _file_response(
                pdf_path,
                preview_name,
                disposition="inline",
                extra_headers={"X-Preview-Mode": "preview"},
            )

    return _file_response(
        resolved,
        file_name,
        disposition="attachment",
        extra_headers={"X-Preview-Mode": "download"},
    )


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: int, request: Request):
    """删除文档（清理向量 + 软删除记录）。"""
    user = _get_user(request)
    doc = kb_mgr.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    kb = kb_mgr.get_kb(doc["kb_id"], user, check_access=False)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")

    logger.info(f"删除文档: id={doc_id} name={doc['file_name']} "
                f"operator={user['user_id']}")

    # 1. 删除向量
    chunks = kb_mgr.db.get_chunks_by_doc(doc_id)
    if chunks:
        chroma_ids = [c["chroma_id"] for c in chunks]
        try:
            await client.call(
                "vector",
                "/delete",
                json={"ids": chroma_ids, "collection": kb["collection_name"]},
            )
        except Exception as e:
            logger.warning(f"删除向量失败（可能已删除）: {e}")

    # 2. 清理本地 DB
    kb_mgr.db.delete_chunks_by_doc(doc_id)
    kb_mgr.db.soft_delete_document(doc_id)

    return {"status": "ok", "deleted": doc_id}


# ═══════════════════════════════════════════════════════════
#  文件上传（异步）
# ═══════════════════════════════════════════════════════════

async def _process_upload(
    task_id: str,
    save_path: str,
    filename: str,
    doc_id: int,
    kb: dict,
    uploader_id: int,
):
    """后台处理上传文件：解析 → 向量化 → 存储。"""
    doc_name = Path(filename).stem
    try:
        # 1. 更新状态 → parsing
        kb_mgr.update_doc_status(doc_id, "parsing")
        logger.info(f"[{task_id}] 开始解析: {filename}")

        doc_resp = await client.call("doc", "/parse", json={
            "file_path": save_path,
            "doc_name": doc_name,
        }, timeout=600.0)

        if "error" in doc_resp:
            kb_mgr.fail_upload(doc_id, f"文档解析失败: {doc_resp['error']}")
            task_store[task_id] = {
                "status": "error",
                "filename": filename,
                "error": doc_resp["error"],
            }
            return

        chunks = doc_resp.get("chunks", [])
        if not chunks:
            kb_mgr.fail_upload(doc_id, "文档解析后无有效内容")
            task_store[task_id] = {
                "status": "error",
                "filename": filename,
                "error": "文档解析后无有效内容",
            }
            return

        # 2. 更新状态 → vectorizing
        kb_mgr.update_doc_status(doc_id, "vectorizing")
        texts = [c["text"] for c in chunks]
        metadatas = [{
            **c.get("metadata", {}),
            "doc_id": doc_id,
            "doc_name": doc_name,
            "file_name": filename,
            "file_type": Path(filename).suffix.lower().lstrip("."),
            "kb_id": kb["id"],
            "uploader_id": uploader_id,
        } for c in chunks]

        vec_resp = await client.call("vector", "/add", json={
            "texts": texts,
            "metadatas": metadatas,
            "collection": kb["collection_name"],
        }, timeout=600.0)

        if "error" in vec_resp:
            kb_mgr.fail_upload(doc_id, f"向量存储失败: {vec_resp['error']}")
            task_store[task_id] = {
                "status": "error",
                "filename": filename,
                "error": vec_resp["error"],
            }
            return

        # 3. 完成：写入 chunk 映射
        chroma_ids = vec_resp.get("ids", [])
        chunk_count = kb_mgr.finish_upload(doc_id, texts, chroma_ids)

        task_store[task_id] = {
            "status": "done",
            "filename": filename,
            "doc_name": doc_name,
            "kb_id": kb["id"],
            "kb_name": kb["name"],
            "chunks": chunk_count,
        }
        logger.info(f"[{task_id}] 处理完成: {filename} → KB[{kb['name']}] {chunk_count} chunks")

    except Exception as e:
        logger.error(f"[{task_id}] 处理失败: {filename}: {e}", exc_info=True)
        kb_mgr.fail_upload(doc_id, str(e))
        task_store[task_id] = {
            "status": "error",
            "filename": filename,
            "error": str(e),
        }


@app.post("/api/kb/{kb_id}/upload")
async def upload_file(
    kb_id: int,
    request: Request,
    file: UploadFile = File(...),
):
    """上传文件到指定知识库并异步入库。"""
    user = _get_user(request)

    # 权限检查
    kb = kb_mgr.get_kb(kb_id, user, check_access=False)
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    from rag.auth import AuthManager
    AuthManager.require_kb_access(user, kb, "write")

    # 文件类型检查
    filename = file.filename or "unknown"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}，支持: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # 保存文件
    kb_upload_dir = UPLOAD_DIR / str(kb_id)
    kb_upload_dir.mkdir(parents=True, exist_ok=True)
    # 添加时间戳防重名
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    saved_name = f"{ts}_{filename}"
    save_path = kb_upload_dir / saved_name

    content = await file.read()
    save_path.write_bytes(content)

    # 创建上传记录
    doc_id = kb_mgr.register_upload(
        kb_id=kb_id,
        uploader=user,
        file_name=filename,
        file_size=len(content),
        file_type=ext.lstrip("."),
        file_path=str(save_path),
    )

    # 启动后台任务
    task_id = uuid.uuid4().hex[:12]
    task_store[task_id] = {
        "status": "processing",
        "filename": filename,
        "kb_id": kb_id,
        "doc_id": doc_id,
    }

    logger.info(f"[{task_id}] 文件已保存: {save_path} → KB[{kb['name']}] "
                f"({len(content)/1024:.0f} KB) user={user['user_id']}")
    asyncio.create_task(_process_upload(task_id, str(save_path), filename, doc_id, kb, user["user_id"]))

    return {
        "task_id": task_id,
        "doc_id": doc_id,
        "filename": filename,
        "kb_id": kb_id,
        "kb_name": kb["name"],
        "status": "processing",
    }


@app.get("/api/upload/{task_id}")
async def get_upload_status(task_id: str):
    """查询上传任务状态。"""
    task = task_store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


# ═══════════════════════════════════════════════════════════
#  对话历史接口
# ═══════════════════════════════════════════════════════════

class CreateConvRequest(BaseModel):
    kb_id: Optional[int] = None
    title: str = "新对话"


class UpdateConvRequest(BaseModel):
    title: Optional[str] = None
    kb_id: Optional[int] = None


@app.post("/api/conversations")
async def create_conversation(req: CreateConvRequest, request: Request):
    """创建新对话。"""
    user = _get_user(request)
    db = get_db()
    conv_id = db.create_conversation(user["user_id"], req.kb_id, req.title)
    return {"id": conv_id, "title": req.title}


@app.get("/api/conversations")
async def list_conversations(request: Request, limit: int = 50):
    """列出当前用户的对话列表。"""
    user = _get_user(request)
    db = get_db()
    convs = db.list_conversations(user["user_id"], limit)
    return {"conversations": convs}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: int, request: Request):
    """获取对话详情（含最近消息）。"""
    user = _get_user(request)
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv["user_id"] != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权访问")
    messages = db.get_messages(conv_id, limit=50)
    conv["messages"] = messages
    return conv


@app.patch("/api/conversations/{conv_id}")
async def update_conversation(conv_id: int, req: UpdateConvRequest, request: Request):
    """更新对话信息（标题等）。"""
    user = _get_user(request)
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv["user_id"] != user["user_id"]:
        raise HTTPException(status_code=403, detail="无权修改")
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        db.update_conversation(conv_id, **updates)
    return {"status": "ok"}


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: int, request: Request):
    """删除对话及其所有消息。"""
    user = _get_user(request)
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv["user_id"] != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权删除")
    db.delete_conversation(conv_id)
    return {"status": "ok"}


@app.get("/api/conversations/{conv_id}/messages")
async def list_messages(conv_id: int, request: Request, before: int = None, limit: int = 50):
    """分页获取消息。"""
    user = _get_user(request)
    db = get_db()
    conv = db.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="对话不存在")
    if conv["user_id"] != user["user_id"] and user["role"] != "admin":
        raise HTTPException(status_code=403, detail="无权访问")
    messages = db.get_messages(conv_id, before_id=before, limit=limit)
    return {"messages": messages, "has_more": len(messages) >= limit}


# ═══════════════════════════════════════════════════════════
#  对话接口（多用户 + 知识库隔离）
# ═══════════════════════════════════════════════════════════

@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """多轮对话（SSE 流式响应）。

    支持知识库隔离：
        - 指定 kb_id → 仅在该知识库中检索
        - 未指定 → 使用用户第一个知识库
    """
    user = _get_user(request)
    question = req.messages[-1].content if req.messages else ""
    db = get_db()

    # 解析 / 创建对话
    conv_id = req.conversation_id
    if conv_id:
        conv = db.get_conversation(conv_id)
        if not conv or (conv["user_id"] != user["user_id"] and user["role"] != "admin"):
            raise HTTPException(status_code=404, detail="对话不存在或无权限")
    else:
        # 自动创建新对话
        title = question[:50] if question else "新对话"
        conv_id = db.create_conversation(user["user_id"], req.kb_id, title)
        conv = db.get_conversation(conv_id)

    # 保存用户消息
    db.add_user_message(conv_id, question)
    # 自动设标题（仅首条消息时）
    if conv["title"] == "新对话" and question:
        db.update_conversation(conv_id, title=question[:80])

    # 解析 knowledge base（优先用对话绑定的 kb_id）
    kb_id = req.kb_id or conv.get("kb_id")
    if kb_id:
        kb = kb_mgr.get_kb(kb_id, user, check_access=True)
        if not kb:
            raise HTTPException(status_code=404, detail="知识库不存在或无权限")
        collection_name = kb["collection_name"]
        # 更新对话绑定的 kb_id
        if not conv.get("kb_id"):
            db.update_conversation(conv_id, kb_id=kb_id)
    else:
        collection_name = kb_mgr.get_user_default_collection(user["user_id"])
        kb = None

    # 加载对话历史摘要
    conv_summary = conv.get("summary", "")

    SUMMARY_THRESHOLD = 20  # 超过 20 条消息时触发摘要
    KEEP_RECENT = 10         # 保留最近 10 条原文

    # 加载最近的消息用于构建上下文
    recent_msgs = db.get_last_messages(conv_id, KEEP_RECENT * 2)

    async def generate():
        try:
            # 0. Query Rewriting
            search_question = question
            if config.llm.rewrite_enabled:
                try:
                    rewrite_resp = await client.call("llm", "/rewrite", json={
                        "query": question,
                    }, retries=0)
                    if "error" not in rewrite_resp and rewrite_resp.get("rewritten"):
                        rewritten = rewrite_resp["rewritten"]
                        if rewritten and rewritten != question:
                            search_question = rewritten
                            logger.info(f"Query rewritten: '{question[:50]}' -> '{rewritten[:50]}'")
                except Exception as e:
                    logger.warning(f"Query rewriting failed, using original: {e}")

            # 1. 向量检索
            search_payload = {"query": search_question, "top_k": req.top_k}
            if collection_name:
                search_payload["collection"] = collection_name

            search_resp = await client.call("vector", "/search", json=search_payload)

            if "error" in search_resp:
                err = search_resp["error"]
                yield "data: " + json.dumps({"type": "token", "content": "[检索错误] " + err}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done", "conversation_id": conv_id}) + "\n\n"
                return

            results = search_resp.get("results", [])
            if not results:
                yield "data: " + json.dumps({"type": "token", "content": "未找到相关文档，无法回答。如果您还没有上传文档，请先在知识库中上传文档。"}, ensure_ascii=False) + "\n\n"
                yield "data: " + json.dumps({"type": "done", "conversation_id": conv_id}) + "\n\n"
                return

            # 2. 重排
            try:
                rerank_resp = await client.call("reranker", "/rerank", json={
                    "query": search_question, "documents": results, "top_k": req.top_k,
                })
                if "error" not in rerank_resp:
                    results = rerank_resp.get("results", results)
            except Exception:
                pass

            # 3. 构建上下文（摘要 + 最近消息 + 检索结果）
            context = _build_context(results[:req.top_k])

            history_parts = []
            if conv_summary:
                history_parts.append(f"[之前对话摘要] {conv_summary}")
            for msg in recent_msgs:
                role = "用户" if msg["role"] == "user" else "助手"
                history_parts.append(f"{role}: {msg['content'][:300]}")
            history_text = "\n".join(history_parts)

            prompt = f"""请基于以下参考文档回答用户的问题。

要求：
1. 只使用参考文档中的信息来回答
2. 如果文档中没有相关信息，明确说明\"根据现有资料无法回答该问题\"
3. 回答要简洁准确，必要时分点列出
4. 如果涉及具体数字、日期、流程，请准确引用
5. 回答正文中不要提及\"参考文档1\"\"文档9\"等编号，直接陈述事实即可

参考文档：
{context}"""

            if history_text:
                prompt += f"\n\n对话历史：\n{history_text}"
            prompt += f"\n\n用户问题：{question}"

            # 4. 流式调用 LLM
            full_answer = ""
            async for line in client.stream("llm", "/stream", json={"prompt": prompt}):
                if line.startswith("data: "):
                    # 收集完整答案用于保存
                    try:
                        payload = json.loads(line[6:])
                        if payload.get("type") == "token":
                            full_answer += payload.get("content", "")
                    except Exception:
                        pass
                    yield line + "\n"
                else:
                    yield f"data: {line}\n\n"

            # 5. 保存助手消息
            sources = _build_sources(
                results=results,
                db=db,
                fallback_kb_id=kb["id"] if kb else None,
                top_k=req.top_k,
            )
            db.add_assistant_message(conv_id, full_answer, json.dumps(sources, ensure_ascii=False))

            # 6. 触发摘要压缩
            msg_count = conv["message_count"] + 2  # +user +assistant
            if msg_count > SUMMARY_THRESHOLD:
                # 异步触发摘要（不阻塞响应）
                asyncio.create_task(_maybe_summarize(conv_id, conv_summary))
                logger.info(f"[conv={conv_id}] 消息数 {msg_count} > {SUMMARY_THRESHOLD}，触发摘要")

            # 7. 发送参考来源 + conversation_id
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"

        except Exception as e:
            logger.error(f"对话流程异常: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'token', 'content': f'[系统错误] {e}'}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id})}\n\n"

    async def _maybe_summarize(cid: int, existing_summary: str):
        """后台异步：压缩早期消息为摘要。"""
        try:
            all_msgs = db.get_last_messages(cid, SUMMARY_THRESHOLD)
            if len(all_msgs) <= KEEP_RECENT * 2:
                return
            # 只压缩超过 KEEP_RECENT 轮的部分
            old_msgs = all_msgs[:-(KEEP_RECENT * 2)]
            if not old_msgs:
                return
            from rag.llm import LLM
            llm = LLM(config.llm)
            new_summary = llm.summarize_conversation(
                [{"role": m["role"], "content": m["content"]} for m in old_msgs],
                existing_summary=existing_summary,
            )
            if new_summary:
                db.update_conversation(cid, summary=new_summary)
                logger.info(f"[conv={cid}] 摘要已更新 ({len(new_summary)} 字)")
        except Exception as e:
            logger.warning(f"[conv={cid}] 摘要生成失败: {e}")

    return StreamingResponse(generate(), media_type="text/event-stream")


# ═══════════════════════════════════════════════════════════
#  系统信息
# ═══════════════════════════════════════════════════════════

@app.get("/api/info")
async def info(request: Request):
    """获取系统概览（含用户知识库统计）。"""
    user = _get_user(request)
    db = get_db()

    kbs = kb_mgr.list_user_kbs(user)
    total_docs = sum(kb.get("doc_count", 0) for kb in kbs)

    try:
        vec_info = await client.call("vector", "/info", method="GET")
    except Exception:
        vec_info = {}

    return {
        "user": user,
        "knowledge_bases": len(kbs),
        "total_documents": total_docs,
        "vector_store": vec_info.get("collection", "unknown"),
    }


@app.get("/api/health")
async def health():
    """聚合所有服务健康状态。"""
    services_status = {}
    for svc in ["doc", "vector", "reranker", "llm"]:
        try:
            resp = await client.call(svc, "/health", method="GET", retries=0)
            services_status[svc] = resp.get("status", "ok")
        except Exception as e:
            services_status[svc] = f"error: {e}"

    all_ok = all(v == "ok" for v in services_status.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "services": services_status,
    }


@app.get("/api/departments")
async def list_departments():
    """返回可用部门列表。"""
    return {
        "departments": [
            {"id": "dev", "name": "开发部"},
            {"id": "test", "name": "测试部"},
            {"id": "product", "name": "产品部"},
        ]
    }


@app.get("/api/supported-formats")
async def supported_formats():
    """返回支持的文件格式列表。"""
    return {
        "formats": sorted(ALLOWED_EXTENSIONS),
        "description": {
            ".pdf": "PDF 文档（MinerU Cloud 解析）",
            ".doc": "Word 文档（旧版，MinerU Cloud 解析）",
            ".docx": "Word 文档（MinerU Cloud 解析）",
            ".ppt": "PowerPoint 演示文稿（旧版，MinerU Cloud 解析）",
            ".pptx": "PowerPoint 演示文稿（MinerU Cloud 解析）",
            ".xls": "Excel 表格（旧版，MinerU Cloud 解析）",
            ".xlsx": "Excel 表格（MinerU Cloud 解析）",
            ".jpg": "图片（MinerU Cloud OCR）",
            ".jpeg": "图片（MinerU Cloud OCR）",
            ".png": "图片（MinerU Cloud OCR）",
            ".gif": "图片（MinerU Cloud OCR）",
            ".bmp": "图片（MinerU Cloud OCR）",
            ".webp": "图片（MinerU Cloud OCR）",
            ".html": "网页（MinerU Cloud 解析）",
            ".htm": "网页（MinerU Cloud 解析）",
            ".md": "Markdown 文档（本地解析）",
            ".txt": "纯文本文件（本地解析）",
            ".markdown": "Markdown 文档（本地解析）",
        }
    }


@app.get("/api/stats")
async def stats(request: Request):
    """获取系统统计信息。"""
    user = _get_user(request)
    db = get_db()
    stats = db.get_stats()
    stats["user_kbs"] = len(kb_mgr.list_user_kbs(user))
    return stats


# ═══════════════════════════════════════════════════════════
#  Dify 对接接口（无需认证，通过 API Key 鉴权）
# ═══════════════════════════════════════════════════════════

DIFY_API_KEY = os.environ.get("DIFY_API_KEY", "dify-rag-secret-key")


def _verify_dify_key(credentials: HTTPAuthorizationCredentials = Depends(dify_security)):
    """验证 Dify 请求的 API Key。"""
    if credentials.credentials != DIFY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")


class DifyIngestRequest(BaseModel):
    """Dify 写入请求 — 把文本存入向量库。"""
    text: str
    metadata: Optional[Dict] = None
    collection: Optional[str] = None  # 不指定则用默认 collection


class DifySearchRequest(BaseModel):
    """Dify 检索请求 — 从向量库召回。"""
    query: str
    top_k: Optional[int] = 5
    collection: Optional[str] = None


class DifyRetrievalRequest(BaseModel):
    """Dify 外部知识库标准格式。"""
    knowledge_id: str
    query: str
    retrieval_setting: Optional[Dict] = None


@app.post("/api/dify/ingest")
async def dify_ingest(req: DifyIngestRequest, request: Request, _: None = Depends(_verify_dify_key)):
    """Dify 调用：把文本切块后存入向量库。

    用法：Dify 工作流中用 HTTP 请求节点，把 LLM 输出写入这里。
    """

    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    # 简单按段落切块（适合 Dify 输出的结构化文本）
    chunks = _split_text_for_dify(text)

    metadata_base = req.metadata or {}
    metadata_base.setdefault("source", "dify")
    metadata_base.setdefault("ingested_at", datetime.now().isoformat())

    metadatas = []
    for i, chunk in enumerate(chunks):
        m = {**metadata_base, "chunk_index": i}
        metadatas.append(m)

    collection = req.collection or _default_dify_collection()

    # 调用 vector service 写入
    resp = await client.call("vector", "/add", json={
        "texts": chunks,
        "metadatas": metadatas,
        "collection": collection,
    })

    if "error" in resp:
        raise HTTPException(status_code=500, detail=resp["error"])

    return {
        "success": True,
        "chunks_stored": len(chunks),
        "collection": collection,
        "ids": resp.get("ids", []),
    }


@app.post("/api/dify/search")
async def dify_search(req: DifySearchRequest, request: Request, _: None = Depends(_verify_dify_key)):
    """Dify 调用：从向量库检索相关内容。

    用法：Dify Agent/Workflow 中作为自定义工具调用。
    """

    collection = req.collection or _default_dify_collection()

    resp = await client.call("vector", "/search", json={
        "query": req.query,
        "top_k": req.top_k,
        "collection": collection,
    })

    if "error" in resp:
        raise HTTPException(status_code=500, detail=resp["error"])

    results = resp.get("results", [])

    # 可选重排
    if results:
        try:
            rerank_resp = await client.call("reranker", "/rerank", json={
                "query": req.query,
                "documents": results,
                "top_k": req.top_k,
            })
            if "error" not in rerank_resp:
                results = rerank_resp.get("results", results)
        except Exception:
            pass

    return {
        "results": [
            {
                "text": r.get("content", "") or r.get("text", ""),
                "score": r.get("score", 0),
                "metadata": r.get("metadata", {}),
            }
            for r in results[:req.top_k]
        ]
    }


@app.post("/api/dify/retrieval")
async def dify_retrieval(req: DifyRetrievalRequest, request: Request, _: None = Depends(_verify_dify_key)):
    """Dify 外部知识库标准接口。

    符合 Dify External Knowledge Base API 规范。
    Dify 会按此格式调用来做知识检索。
    """

    top_k = 5
    if req.retrieval_setting:
        top_k = req.retrieval_setting.get("top_k", 5)

    collection = req.knowledge_id or _default_dify_collection()

    resp = await client.call("vector", "/search", json={
        "query": req.query,
        "top_k": top_k,
        "collection": collection,
    })

    if "error" in resp:
        raise HTTPException(status_code=500, detail=resp["error"])

    results = resp.get("results", [])

    # Dify 外部知识库要求的返回格式
    records = []
    for r in results[:top_k]:
        records.append({
            "content": r.get("content", "") or r.get("text", ""),
            "score": r.get("score", 0),
            "title": r.get("metadata", {}).get("doc_name", ""),
            "metadata": r.get("metadata", {}),
        })

    return {"records": records}


def _default_dify_collection() -> str:
    """Dify 专用的默认 collection 名称。"""
    return os.environ.get("DIFY_COLLECTION", "dify_knowledge")


def _split_text_for_dify(text: str, max_chunk: int = 800) -> List[str]:
    """简单切块：按双换行分段，超长段按句子拆分。"""
    paragraphs = re.split(r'\n{2,}', text)
    chunks = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chunk:
            chunks.append(para)
        else:
            # 按句子拆分
            sentences = re.split(r'(?<=[。！？.!?\n])', para)
            current = ""
            for sent in sentences:
                if len(current) + len(sent) > max_chunk and current:
                    chunks.append(current.strip())
                    current = sent
                else:
                    current += sent
            if current.strip():
                chunks.append(current.strip())

    if not chunks:
        chunks = [text[:max_chunk]]

    return chunks


@app.on_event("shutdown")
async def shutdown():
    await client.close()
    kb_mgr.db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
