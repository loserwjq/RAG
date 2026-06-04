"""
用户认证模块 — 密码哈希 + JWT / Dev Mode。

两种模式：
    1. Dev Mode（默认）: 前端传 X-User-Id header，直接识别用户。方便开发调试。
    2. JWT Mode: 标准 JWT Bearer token 认证。

用法:
    from rag.auth import AuthManager, hash_password, verify_password

    am = AuthManager()
    user = am.get_current_user(request)        # FastAPI Request
    token = am.create_token(user_id=1)         # JWT 模式
"""

import hashlib
import hmac
import os
import time
from typing import Optional

try:
    from fastapi import Request, HTTPException
    _has_fastapi = True
except ImportError:
    _has_fastapi = False

from rag.config import AuthConfig
from rag.database import get_db


# ── 密码哈希（SHA-256 + salt，轻量无外部依赖） ────────────

def _generate_salt(length: int = 16) -> str:
    return os.urandom(length).hex()


def hash_password(password: str, salt: str = None) -> str:
    """生成密码哈希。格式: hex_salt:hex_hash"""
    if salt is None:
        salt = _generate_salt()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return f"{salt}:{hashed.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """验证密码。"""
    try:
        salt, hashed = stored.split(":", 1)
        return hmac.compare_digest(
            hash_password(password, salt),
            stored,
        )
    except (ValueError, AttributeError):
        return False


# ── 简易 JWT（无外部依赖，HS256） ─────────────────────────

try:
    import jwt as _pyjwt

    _has_pyjwt = True
except ImportError:
    _has_pyjwt = False


def _encode_jwt(payload: dict, secret: str, algorithm: str = "HS256") -> str:
    """编码 JWT token。"""
    if _has_pyjwt:
        return _pyjwt.encode(payload, secret, algorithm=algorithm)

    # 简易实现（不依赖 PyJWT）
    import base64
    import json

    header = base64.urlsafe_b64encode(
        json.dumps({"alg": algorithm, "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    payload_b64 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    signature = hmac.new(
        secret.encode(),
        f"{header}.{payload_b64}".encode(),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload_b64}.{sig_b64}"


def _decode_jwt(token: str, secret: str, algorithm: str = "HS256") -> Optional[dict]:
    """解码 JWT token，失败返回 None。"""
    if _has_pyjwt:
        try:
            return _pyjwt.decode(token, secret, algorithms=[algorithm])
        except Exception:
            return None

    # 简易实现
    import base64
    import json

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        # 验证签名
        expected_sig = hmac.new(
            secret.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        padding = 4 - len(sig_b64) % 4
        if padding != 4:
            sig_b64 += "=" * padding
        actual_sig = base64.urlsafe_b64decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            return None

        # 解码 payload
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))

        # 检查过期
        if payload.get("exp", 0) < int(time.time()):
            return None

        return payload
    except Exception:
        return None


# ── AuthManager ──────────────────────────────────────────

class AuthManager:
    """认证管理器。"""

    def __init__(self, config: AuthConfig = None):
        self._config = config or AuthConfig()

    @property
    def dev_mode(self) -> bool:
        return self._config.dev_mode

    # ── Token 操作 ───────────────────────────────────────

    def create_token(self, user_id: int, username: str = "") -> str:
        """创建 JWT token。"""
        now = int(time.time())
        payload = {
            "sub": str(user_id),
            "username": username,
            "iat": now,
            "exp": now + self._config.jwt_expire_hours * 3600,
        }
        return _encode_jwt(payload, self._config.jwt_secret, self._config.jwt_algorithm)

    def decode_token(self, token: str) -> Optional[dict]:
        """解码 JWT token。"""
        return _decode_jwt(token, self._config.jwt_secret, self._config.jwt_algorithm)

    # ── 用户识别 ─────────────────────────────────────────

    def get_current_user(self, request) -> dict:
        """从 Request 中提取当前用户信息。

        Dev Mode: 读 X-User-Id + X-Username + X-Department headers
        JWT Mode: 读 Authorization: Bearer <token>

        返回: {"user_id": int, "username": str, "department": str, "role": str}
        """
        if not _has_fastapi:
            raise RuntimeError("get_current_user 需要 FastAPI 依赖")
        if self._config.dev_mode:
            return self._resolve_dev_user(request)
        return self._resolve_jwt_user(request)

    def _resolve_dev_user(self, request) -> dict:
        """Dev Mode：从 header 读取当前用户。"""
        user_id_str = request.headers.get("X-User-Id", "")
        if not user_id_str:
            raise HTTPException(
                status_code=401,
                detail="Dev Mode: 缺少 X-User-Id header",
            )

        try:
            user_id = int(user_id_str)
        except ValueError:
            raise HTTPException(status_code=401, detail="无效的 X-User-Id")

        db = get_db()
        user = db.get_user(user_id=user_id)
        if not user:
            raise HTTPException(status_code=401, detail=f"用户 {user_id} 不存在")

        return {
            "user_id": user["id"],
            "username": user["username"],
            "department": user["department"],
            "role": user["role"],
        }

    def _resolve_jwt_user(self, request) -> dict:
        """JWT Mode：从 Authorization header 读取 JWT。"""
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail="缺少 Authorization: Bearer <token>",
            )

        token = auth[7:]
        payload = self.decode_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Token 无效或已过期")

        user_id = int(payload.get("sub", 0))
        if not user_id:
            raise HTTPException(status_code=401, detail="Token 中缺少 sub 字段")

        db = get_db()
        user = db.get_user(user_id=user_id)
        if not user:
            raise HTTPException(status_code=401, detail=f"用户 {user_id} 不存在")

        return {
            "user_id": user["id"],
            "username": user["username"],
            "department": user["department"],
            "role": user["role"],
        }

    # ── 权限检查 ─────────────────────────────────────────

    @staticmethod
    def require_kb_access(user: dict, kb: dict, min_permission: str = "read"):
        """检查用户对知识库的访问权限。

        权限级别: read < write < admin

        无权限时抛出 PermissionError（CLI 模式）或 HTTPException（FastAPI 模式）。
        """
        if user.get("role") == "admin":
            return True

        # owner 拥有 admin 权限
        if kb.get("owner_id") == user["user_id"]:
            return True

        # 检查 kb_members
        db = get_db()
        perm = db.get_user_kb_permission(kb["id"], user["user_id"])
        if not perm:
            msg = "无权访问该知识库"
            if _has_fastapi:
                raise HTTPException(status_code=403, detail=msg)
            raise PermissionError(msg)

        levels = {"read": 0, "write": 1, "admin": 2}
        if levels.get(perm, 0) < levels.get(min_permission, 0):
            msg = f"权限不足: 需要 {min_permission}，当前 {perm}"
            if _has_fastapi:
                raise HTTPException(status_code=403, detail=msg)
            raise PermissionError(msg)
        return True


# ── 便捷函数 ────────────────────────────────────────────

def get_auth_manager(config: AuthConfig = None) -> AuthManager:
    """获取 AuthManager 实例。"""
    return AuthManager(config)
