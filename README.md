# NeuralKB — 多用户 RAG 知识库系统

基于检索增强生成（RAG）的企业级知识库系统，支持多用户/多部门隔离、混合向量检索、多轮对话问答。

## 架构

```
┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  Vue 3 前端   │────▶│  Gateway     │────▶│  LLM Service  │   Gitee AI
│  (Vite:5173)  │     │  (FastAPI)   │     │  (Qwen3-235B) │──▶ Qwen3
└──────────────┘     │  :8005       │     │  :8004        │
                     │              │     ├──────────────┤
                     │  Auth / KB   │     │  Reranker     │   bge-reranker
                     │  Chat / SSE  │────▶│  :8003        │──▶ -v2-m3
                     │              │     ├──────────────┤
                     │  Upload      │     │  Vector       │   bge-m3
                     │              │────▶│  :8002        │──▶ Dense+Sparse
                     │              │     ├──────────────┤   + ChromaDB
                     │              │     │  Doc Service  │   MinerU Cloud
                     │              │────▶│  :8001        │──▶ (PDF/DOCX/...)
                     └──────────────┘     └──────────────┘
```

**6 个微服务**，PM2 管理，FastAPI + httpx 服务间通信，X-Request-ID 全链路追踪。

## 特性

- **多格式文档解析** — PDF/DOC/DOCX/PPT/PPTX/XLS/XLSX/图片/HTML/Markdown，通过 MinerU Cloud VLM 引擎
- **混合向量检索** — bge-m3 Dense + Sparse 双路召回，ChromaDB (sqlite-vec) 存储
- **Cross-Encoder 精排** — bge-reranker-v2-m3 对初检结果重排序
- **Query Rewriting** — LLM 检索前自动修正拼写错误、扩展语义
- **多用户/多知识库** — 部门级隔离，SQLite 管理用户、知识库、成员权限
- **多轮对话** — SSE 流式输出，对话历史持久化，自动摘要压缩
- **Dify 集成** — 标准外部知识库接口 (`/api/dify/retrieval`)
- **赛博朋克风格 UI** — Vue 3 + GSAP 动画，上传 / 检索 / 问答一体化

## 项目结构

```
minerU_local/
├── rag/                       # RAG 核心引擎
│   ├── config.py              #   统一配置（支持 .env 覆盖）
│   ├── parser.py              #   文件解析（MinerU Cloud + 本地 Markdown）
│   ├── chunker.py             #   语义切块
│   ├── embedder.py            #   bge-m3 向量化 (Dense + Sparse)
│   ├── store.py               #   ChromaDB 向量库
│   ├── reranker.py            #   bge-reranker-v2-m3 精排
│   ├── llm.py                 #   OpenAI 兼容 LLM 客户端
│   ├── pipeline.py            #   编排层（解析→切块→向量化→检索→问答）
│   ├── database.py            #   SQLite 业务数据库
│   ├── auth.py                #   用户认证（JWT / Dev Mode）
│   ├── kb_manager.py          #   知识库 CRUD（跨 DB + ChromaDB）
│   ├── main.py                #   CLI 入口
│   └── __init__.py
├── services/                  # 微服务
│   ├── gateway.py             #   API 网关 (:8005)
│   ├── doc_service.py         #   文档解析 + 切块 (:8001)
│   ├── vector_service.py      #   向量化 + 检索 (:8002)
│   ├── reranker_service.py    #   重排序 (:8003)
│   ├── llm_service.py         #   LLM 生成 (:8004)
│   ├── client.py              #   服务间 HTTP 客户端
│   └── logger.py              #   结构化日志 + X-Request-ID
├── frontend/                  # Vue 3 前端 (Vite:5173)
│   └── src/
│       ├── App.vue            #   根组件
│       ├── components/        #   聊天/文档/知识库/上传面板
│       └── api.js             #   API 客户端
├── models/                    # 本地模型 (~4.2 GB)
│   ├── bge-m3/                #   嵌入模型 (2.1 GB)
│   └── bge-reranker-v2-m3/    #   重排模型 (2.1 GB)
├── test/                      # 测试文件 + 对比脚本
├── chroma_db/                 # ChromaDB 持久化
├── data/                      # SQLite 数据库
├── uploads/                   # 上传文件
├── logs/                      # PM2 日志
├── ecosystem.config.cjs       # PM2 配置
├── start-pm2.bat              # Windows 启动脚本
├── .env.example               # 环境变量模板
└── README.md
```

## 快速上手

### 1. 环境要求

- **Python 3.10+** (推荐 3.13)
- **Node.js 18+** (前端)
- **PM2** (进程管理, `npm i -g pm2`)
- **GPU** (可选, bge-m3 和 reranker 自动使用 CUDA)

### 2. 安装

```bash
# 克隆项目
git clone <repo-url>
cd minerU_local

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装 Python 依赖
pip install fastapi uvicorn httpx python-dotenv openai chromadb sqlite-vec \
            numpy Pillow tqdm orjson sentencepiece transformers torch \
            python-docx openpyxl python-pptx beautifulsoup4

# 安装前端依赖
cd frontend && npm install && cd ..

# 下载模型 (可选，本地嵌入/重排需要)
# 将 bge-m3 和 bge-reranker-v2-m3 放入 models/ 目录
```

### 3. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入必要配置：

```env
# LLM API (必填)
RAG_LLM_API_KEY=your-api-key
RAG_LLM_URL=https://ai.gitee.com/v1
RAG_LLM_MODEL=Qwen3-235B-A22B

# MinerU 云端 API (文档解析，必填)
RAG_MINERU_MODE=api
RAG_MINERU_API_TOKEN=你的mineru-token    # 从 https://mineru.net/apiManage/token 获取
RAG_MINERU_MODEL_VERSION=vlm

# JWT 密钥 (生产环境务必修改)
RAG_JWT_SECRET=change-me-in-production
```

### 4. 初始化数据库

```bash
python -m rag.main init-db
```

创建默认用户：

| 用户名 | 密码 | 部门 | 角色 |
|--------|------|------|------|
| admin | admin123 | dev | admin |
| dev_user | dev123 | dev | user |
| test_user | test123 | test | user |
| product_user | product123 | product | user |

### 5. 启动

```bash
# 一键启动所有服务
start-pm2.bat

# 或手动启动单个服务
pm2 start ecosystem.config.cjs --only rag-gateway
```

启动后访问：

| 服务 | 地址 |
|------|------|
| 前端界面 | http://localhost:5173 |
| API 网关 | http://localhost:8005 |
| API 文档 | http://localhost:8005/docs |

### 6. 使用

**Web UI**: 打开 http://localhost:5173，登录后上传文档，开始问答。

**CLI**:

```bash
# 创建知识库
python -m rag.main kb create "我的知识库" 1 --dept dev

# 入库文档
python -m rag.main ingest test/国家突发公共事件总体应急预案.docx --kb 1

# 搜索
python -m rag.main search "应急预案分类" --kb 1

# 问答
python -m rag.main ask "电力网络安全事件如何分级" --kb 1

# 交互式对话
python -m rag.main chat --kb 1
```

## API 端点

### 认证

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录 |
| POST | `/api/auth/register` | 用户注册 |
| GET | `/api/users/me` | 当前用户信息 |

### 知识库

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/kb` | 创建知识库 |
| GET | `/api/kb` | 列出知识库 |
| GET | `/api/kb/{id}` | 知识库详情 |
| PUT | `/api/kb/{id}` | 更新知识库 |
| DELETE | `/api/kb/{id}` | 删除知识库 |
| POST | `/api/kb/{id}/members` | 添加成员 |
| GET | `/api/kb/{id}/members` | 列出成员 |

### 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/kb/{id}/upload` | 上传文档（异步解析+入库） |
| GET | `/api/upload/{task_id}` | 上传任务状态 |
| GET | `/api/kb/{id}/documents` | 列出知识库文档 |
| DELETE | `/api/documents/{id}` | 删除文档 |
| GET | `/api/documents/{id}/preview` | 文档预览 |

### 对话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/conversations` | 创建对话 |
| GET | `/api/conversations` | 列出对话 |
| POST | `/api/chat` | 多轮对话 (SSE 流式) |

### Dify 集成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/dify/retrieval` | 外部知识库检索 |
| POST | `/api/dify/search` | 快速搜索 |
| POST | `/api/dify/ingest` | 文本入库 |

### 系统

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 聚合健康检查 |
| GET | `/api/info` | 系统概览 |
| GET | `/api/stats` | 统计信息 |
| GET | `/api/supported-formats` | 支持的文件格式 |
| GET | `/api/departments` | 部门列表 |

## 支持的文件格式

| 格式 | 解析引擎 |
|------|---------|
| PDF | MinerU Cloud VLM |
| Word (.doc/.docx) | MinerU Cloud VLM |
| PowerPoint (.ppt/.pptx) | MinerU Cloud VLM |
| Excel (.xls/.xlsx) | MinerU Cloud VLM |
| 图片 (.jpg/.png/.gif/.bmp/.webp) | MinerU Cloud VLM (OCR) |
| HTML | MinerU Cloud VLM |
| Markdown (.md) | 本地正则解析 |
| 纯文本 (.txt) | 本地正则解析 |

## 配置参考

所有可配环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_LLM_API_KEY` | — | LLM API 密钥 (**必填**) |
| `RAG_LLM_URL` | `https://ai.gitee.com/v1` | LLM API 地址 |
| `RAG_LLM_MODEL` | `Qwen3-235B-A22B` | 模型名称 |
| `RAG_LLM_TEMPERATURE` | `0.3` | 生成温度 |
| `RAG_LLM_MAX_TOKENS` | `2048` | 最大生成 token |
| `RAG_MINERU_MODE` | `local` | MinerU 模式: `local` / `api` |
| `RAG_MINERU_API_TOKEN` | — | MinerU 云端 token ([获取](https://mineru.net/apiManage/token)) |
| `RAG_MINERU_MODEL_VERSION` | `vlm` | 云模型: `pipeline` / `vlm` / `MinerU-HTML` |
| `RAG_JWT_SECRET` | — | JWT 签名密钥 (**生产必改**) |
| `RAG_TOP_K` | `15` | 检索返回条数 |
| `RAG_ALPHA` | `0.5` | Dense/Sparse 融合权重 |
| `RAG_MODEL_DIR` | `./models/bge-m3` | 嵌入模型路径 |
| `RAG_CHROMA_DIR` | `./chroma_db` | ChromaDB 路径 |
| `RAG_DB_PATH` | `./data/rag.db` | SQLite 路径 |
| `RAG_OUTPUT_DIR` | `./output` | MinerU 解析输出 |
| `RAG_DEVICE` | 自动 | 推理设备 (cuda/cpu) |
| `RAG_AUTH_DEV_MODE` | `true` | 开发模式 (跳过 JWT) |

## 技术栈

| 层 | 技术 |
|----|------|
| 后端框架 | FastAPI + Uvicorn |
| 前端 | Vue 3 + Vite + GSAP |
| LLM 客户端 | OpenAI SDK |
| 嵌入模型 | BAAI/bge-m3 (Dense + Sparse) |
| 重排模型 | BAAI/bge-reranker-v2-m3 |
| 向量库 | ChromaDB + sqlite-vec |
| 业务数据库 | SQLite (WAL mode) |
| 文档解析 | MinerU Cloud API |
| 进程管理 | PM2 |
| 服务间通信 | httpx |
