"""
统一配置管理 — 所有可调参数集中于此。

支持环境变量覆盖，方便部署时调整而无需改代码。
"""

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ParserConfig:
    """文件解析配置。"""
    output_dir: str = "./output"
    lang: str = "ch"
    backend: str = "pipeline"
    parse_method: str = "auto"
    formula_enable: bool = True
    table_enable: bool = True


@dataclass
class ChunkerConfig:
    """切块配置。"""
    max_chunk_chars: int = 800
    # 可合并的文本块类型
    mergeable_types: set = field(default_factory=lambda: {
        "text", "header", "footer", "page_number",
        "aside_text", "ref_text", "abstract", "list",
    })
    # 独立类型（挂载标题后整体输出）
    standalone_types: set = field(default_factory=lambda: {
        "table", "equation", "code", "algorithm",
    })
    # 透传类型（不参与切块）
    passthrough_types: set = field(default_factory=lambda: {
        "image", "chart", "seal",
    })


@dataclass
class EmbedderConfig:
    """向量化配置。"""
    model_dir: str = str(Path(__file__).parent.parent / "models" / "bge-m3")
    model_name: str = "BAAI/bge-m3"
    batch_size: int = 32
    max_length: int = 8192
    sparse_top_k: int = 256
    device: str = ""  # 空字符串表示自动选择


@dataclass
class StoreConfig:
    """向量库配置。"""
    persist_dir: str = "./chroma_db"
    collection_name: str = "documents"
    hnsw_space: str = "cosine"


@dataclass
class SearchConfig:
    """检索配置。"""
    top_k: int = 15
    alpha: float = 0.5  # dense 权重，1-alpha 为 sparse 权重
    candidate_multiplier: int = 3  # 候选集倍数


@dataclass
class RerankerConfig:
    """Reranker 重排配置。"""
    model_dir: str = str(Path(__file__).parent.parent / "models" / "bge-reranker-v2-m3")
    model_name: str = "BAAI/bge-reranker-v2-m3"
    batch_size: int = 16
    max_length: int = 512
    device: str = ""  # 空字符串表示自动选择
    enabled: bool = False  # 内存不足时设为 False（模型约 2.2GB）


@dataclass
class LLMConfig:
    """LLM 配置（Gitee AI / OpenAI 兼容 API）。"""
    base_url: str = "https://ai.gitee.com/v1"       # API 地址
    api_key: str = "4GAJXWCGWLBBXRJAFLYPBDGB6TRXTP9ZUQHIPOOY"  # API Key
    model: str = "Qwen3-235B-A22B"                   # 模型名称
    temperature: float = 0.3                          # 生成温度（低温更精确）
    max_tokens: int = 2048                            # 最大生成 token 数
    timeout: int = 120                                # 请求超时（秒）
    extra_headers: dict = field(default_factory=lambda: {
        "X-Failover-Enabled": "true",
    })
    system_prompt: str = (
        "你是一个专业的企业知识库助手。请基于提供的参考文档准确回答用户问题。"
        "如果文档中没有相关信息，请明确说明无法从现有资料中找到答案。"
        "回答要简洁、准确、有条理。"
    )
    # Query Rewriting 配置
    rewrite_enabled: bool = True                     # 是否启用检索前问题改写
    rewrite_temperature: float = 0.1                 # 改写温度（极低，近乎确定性）
    rewrite_max_tokens: int = 128                    # 改写输出很短，不需要太多 token
    rewrite_prompt: str = (
        "你是一个查询纠错器。修正用户输入中明显的拼写错误，输出修正后的查询。"
        "只输出修正后的查询文本，不要任何解释、引号或额外内容。\n"
        "规则（按优先级）：\n"
        "1. 仅修正明显的拼写/打字错误（如多打、漏打、错打一个字），不要改写语义\n"
        "2. 不要将英文单词翻译为中文，不要将中文翻译为英文\n"
        "3. 如果查询本身没有明显拼写错误，原样返回\n"
        "4. 保持原始语言和格式不变\n"
        "示例：\n"
        "输入: Tonala是什么 → 输出: Tonale是什么\n"
        "输入: 什么是AI → 输出: 什么是AI\n"
        "输入: 王家钦是谁 → 输出: 王家卿是谁"
    )


@dataclass
class DatabaseConfig:
    """关系型数据库配置（SQLite）。"""
    db_path: str = ""  # 空字符串表示使用默认路径 data/rag.db


@dataclass
class AuthConfig:
    """认证配置。"""
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 24
    # 简易模式（开发环境）：使用 X-User-Id header 跳过 JWT
    dev_mode: bool = True


@dataclass
class RAGConfig:
    """顶层配置，聚合所有子配置。"""
    parser: ParserConfig = field(default_factory=ParserConfig)
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    store: StoreConfig = field(default_factory=StoreConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    reranker: RerankerConfig = field(default_factory=RerankerConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    auth: AuthConfig = field(default_factory=AuthConfig)

    @classmethod
    def from_env(cls) -> "RAGConfig":
        """从环境变量加载配置覆盖。"""
        cfg = cls()

        # Parser
        if v := os.getenv("RAG_OUTPUT_DIR"):
            cfg.parser.output_dir = v
        if v := os.getenv("RAG_LANG"):
            cfg.parser.lang = v

        # Chunker
        if v := os.getenv("RAG_MAX_CHUNK_CHARS"):
            cfg.chunker.max_chunk_chars = int(v)

        # Embedder
        if v := os.getenv("RAG_MODEL_DIR"):
            cfg.embedder.model_dir = v
        if v := os.getenv("RAG_DEVICE"):
            cfg.embedder.device = v

        # Store
        if v := os.getenv("RAG_CHROMA_DIR"):
            cfg.store.persist_dir = v
        if v := os.getenv("RAG_COLLECTION"):
            cfg.store.collection_name = v

        # Search
        if v := os.getenv("RAG_TOP_K"):
            cfg.search.top_k = int(v)
        if v := os.getenv("RAG_ALPHA"):
            cfg.search.alpha = float(v)

        # LLM
        if v := os.getenv("RAG_LLM_URL"):
            cfg.llm.base_url = v
        if v := os.getenv("RAG_LLM_MODEL"):
            cfg.llm.model = v
        if v := os.getenv("RAG_LLM_TEMPERATURE"):
            cfg.llm.temperature = float(v)
        if v := os.getenv("RAG_LLM_MAX_TOKENS"):
            cfg.llm.max_tokens = int(v)

        # Database
        if v := os.getenv("RAG_DB_PATH"):
            cfg.database.db_path = v

        # Auth
        if v := os.getenv("RAG_JWT_SECRET"):
            cfg.auth.jwt_secret = v
        if v := os.getenv("RAG_AUTH_DEV_MODE"):
            cfg.auth.dev_mode = v.lower() in ("1", "true", "yes")

        return cfg
