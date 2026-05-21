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
    top_k: int = 10
    alpha: float = 0.5  # dense 权重，1-alpha 为 sparse 权重
    candidate_multiplier: int = 3  # 候选集倍数


@dataclass
class RAGConfig:
    """顶层配置，聚合所有子配置。"""
    parser: ParserConfig = field(default_factory=ParserConfig)
    chunker: ChunkerConfig = field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    store: StoreConfig = field(default_factory=StoreConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

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

        return cfg
