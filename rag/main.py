"""
RAG Pipeline CLI 入口。

用法:
    # 系统初始化
    python -m rag.main init-db                   # 初始化数据库 + 创建默认用户

    # 用户管理
    python -m rag.main user add <username> <password> <display_name> <dept>
    python -m rag.main user list [--dept dev]

    # 知识库管理
    python -m rag.main kb create <name> <owner_id> [--dept dev] [--desc "描述"]
    python -m rag.main kb list [--user 1]
    python -m rag.main kb delete <kb_id>
    python -m rag.main kb docs <kb_id>

    # 文档操作
    python -m rag.main ingest <file> [--kb <kb_id>]    # 入库到指定知识库
    python -m rag.main search <query> [--kb <kb_id>]    # 检索
    python -m rag.main ask <question> [--kb <kb_id>]    # 回答
    python -m rag.main chat                              # 交互式问答
    python -m rag.main info                              # 查看状态

前置条件（问答功能）:
    1. Gitee AI API Key（已配置在 config.py）
    2. 本地模型: bge-m3, bge-reranker-v2-m3
"""

import sys
import os

# Windows 控制台 UTF-8
if sys.platform == "win32":
    os.system("chcp 65001 >nul 2>&1")
    # 确保 stdout/stderr 使用 UTF-8，但不破坏 input()
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except Exception:
            pass

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def cmd_ingest(args):
    """入库文档。"""
    from rag.pipeline import Pipeline

    pipe = Pipeline()
    for file_path in args:
        try:
            result = pipe.ingest(file_path)
            print(f"\n✓ {result['doc_name']}: "
                  f"{result['n_stored']} chunks 入库 ({result['elapsed']}s)")
        except Exception as e:
            print(f"\n✗ {file_path}: {e}")


def cmd_search(args):
    """检索。"""
    from rag.pipeline import Pipeline

    if not args:
        print("用法: python -m rag.main search <query>")
        return

    query = " ".join(args)
    pipe = Pipeline()

    print(f"查询: {query}\n")
    results = pipe.search(query, top_k=5)

    if not results:
        print("未找到相关结果。请先使用 ingest 命令入库文档。")
        return

    for i, r in enumerate(results, 1):
        lines = r["content"].split("\n")
        headings = [l.strip("# ").strip() for l in lines if l.startswith("#")]
        section = " > ".join(headings[-2:]) if headings else ""

        print(f"{'─' * 60}")
        # 显示分数（rerank 分数优先）
        rerank_score = r.get("rerank_score")
        if rerank_score is not None:
            score_str = f"rerank: {rerank_score:.3f} (初检rank: #{r.get('original_rank', '?')})"
        else:
            score_str = f"score: {r['score']:+.3f}"
        print(f"[{i}] {score_str}  "
              f"来源: {r['metadata'].get('doc_name', '?')} "
              f"page={r['metadata'].get('page_idx', '?')}")
        if section:
            print(f"    章节: {section}")
        # 显示正文内容（去掉标题前缀，只显示实际内容）
        content_lines = [l for l in lines if not l.startswith("#") and l.strip()]
        content = "\n".join(content_lines).strip()
        if content:
            print(f"\n    {content[:500]}")
        print()


def cmd_ask(args):
    """问答（流式输出）。"""
    from rag.pipeline import Pipeline

    if not args:
        print("用法: python -m rag.main ask <question>")
        return

    question = " ".join(args)
    pipe = Pipeline()

    # 先检查 LLM 状态
    health = pipe.check_llm()
    if health["status"] != "ok":
        print(f"⚠ Ollama 未就绪: {health.get('error', '未知错误')}")
        print(f"  提示: {health.get('hint', '')}")
        print(f"\n  安装: https://ollama.com")
        print(f"  启动: ollama serve")
        print(f"  拉取模型: ollama pull qwen2.5:7b")
        return

    print(f"问题: {question}\n")
    print("回答: ", end="", flush=True)

    # 流式输出
    result = pipe.ask(question, stream=True)
    answer_gen = result["answer"]

    if isinstance(answer_gen, str):
        print(answer_gen)
    else:
        for chunk in answer_gen:
            print(chunk, end="", flush=True)
        print()

    # 显示来源
    if result["sources"]:
        print(f"\n参考来源 ({len(result['sources'])} 条):")
        for i, s in enumerate(result["sources"], 1):
            print(f"  [{i}] score={s['score']:.3f} "
                  f"doc={s['metadata'].get('doc_name', '?')}")


def cmd_chat(args):
    """交互式问答（多轮对话，支持上下文记忆）。"""
    from rag.pipeline import Pipeline
    from rag.llm import LLMError

    print("正在初始化...", flush=True)
    pipe = Pipeline()
    print("初始化完成.", flush=True)

    # 对话历史（用于多轮上下文）
    chat_history = []
    max_history = 10  # 保留最近 N 轮对话

    print("=" * 55, flush=True)
    print("  RAG 交互式问答", flush=True)
    print("=" * 55, flush=True)
    print(f"  模型: {pipe._llm.model}", flush=True)
    print(f"  Reranker: {'启用' if pipe._reranker else '未启用'}", flush=True)
    print("-" * 55, flush=True)
    print("  命令:", flush=True)
    print("    /help     - 显示帮助", flush=True)
    print("    /clear    - 清除对话历史", flush=True)
    print("    /history  - 查看对话历史", flush=True)
    print("    /sources  - 显示上次回答的参考来源", flush=True)
    print("    /search   - 仅检索不生成答案", flush=True)
    print("    quit/exit - 退出", flush=True)
    print("=" * 55, flush=True)

    last_sources = []

    while True:
        try:
            question = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n再见!")
            break

        if not question:
            continue

        # ── 命令处理 ──
        if question.lower() in ("quit", "exit", "q", "/quit", "/exit"):
            print("再见!")
            break

        if question == "/help":
            print("  /help     - 显示帮助")
            print("  /clear    - 清除对话历史")
            print("  /history  - 查看对话历史")
            print("  /sources  - 显示上次回答的参考来源")
            print("  /search <query> - 仅检索不生成答案")
            print("  quit/exit - 退出")
            continue

        if question == "/clear":
            chat_history.clear()
            print("  ✓ 对话历史已清除")
            continue

        if question == "/history":
            if not chat_history:
                print("  (暂无对话历史)")
            else:
                print(f"  对话历史 ({len(chat_history)//2} 轮):")
                for msg in chat_history:
                    role = "你" if msg["role"] == "user" else "助手"
                    content = msg["content"][:80]
                    print(f"    [{role}] {content}{'...' if len(msg['content']) > 80 else ''}")
            continue

        if question == "/sources":
            if not last_sources:
                print("  (暂无参考来源)")
            else:
                print(f"  上次回答参考来源 ({len(last_sources)} 条):")
                for i, s in enumerate(last_sources, 1):
                    meta = s.get("metadata", {})
                    print(f"    [{i}] score={s.get('score', 0):.3f} "
                          f"doc={meta.get('doc_name', '?')}")
                    # 显示内容摘要
                    content = s.get("content", "")[:100]
                    print(f"        {content}...")
            continue

        if question.startswith("/search "):
            query = question[8:].strip()
            if query:
                print(f"  检索: {query}\n")
                results = pipe.search(query, top_k=5)
                for i, r in enumerate(results, 1):
                    lines = r["content"].split("\n")
                    headings = [l.strip("# ").strip() for l in lines if l.startswith("#")]
                    section = " > ".join(headings[-2:]) if headings else ""
                    rerank_score = r.get("rerank_score")
                    if rerank_score is not None:
                        score_str = f"rerank={rerank_score:.3f}"
                    else:
                        score_str = f"score={r['score']:+.3f}"
                    print(f"  [{i}] {score_str} {section[:60]}")
            continue

        # ── 正常问答 ──
        print("")
        print("[检索中，首次加载模型需要约20秒...]", flush=True)

        try:
            import time as _time
            _t_start = _time.time()

            # 检索相关文档
            results = pipe.search(question, top_k=5)
            _t_after_search = _time.time()
            print(f"[[timer]检索完成: {_t_after_search - _t_start:.2f}s]", flush=True)
            print("助手: ", end="", flush=True)
            last_sources = [{
                "content": r["content"][:200],
                "score": r["score"],
                "metadata": r["metadata"],
            } for r in results]

            if not results:
                print("未找到相关文档，无法回答。")
                continue

            # 构建上下文（包含检索结果 + 对话历史）
            context = pipe._build_context(results)

            # 构建带历史的 prompt
            history_text = ""
            if chat_history:
                recent = chat_history[-max_history * 2:]  # 最近 N 轮
                history_parts = []
                for msg in recent:
                    role = "用户" if msg["role"] == "user" else "助手"
                    history_parts.append(f"{role}: {msg['content'][:300]}")
                history_text = "\n".join(history_parts)

            prompt = f"""请基于以下参考文档回答用户的问题。

要求：
1. 只使用参考文档中的信息来回答
2. 如果文档中没有相关信息，明确说明"根据现有资料无法回答该问题"
3. 回答要简洁准确，必要时分点列出
4. 如果涉及具体数字、日期、流程，请准确引用
5. 回答中引用来源时使用文档的实际名称，不要用"文档1""文档9"等编号
6. 结合对话历史理解用户意图

参考文档：
{context}"""

            if history_text:
                prompt += f"""

对话历史：
{history_text}"""

            prompt += f"""

用户问题：{question}"""

            # 流式生成
            full_answer = ""
            _t_llm_start = _time.time()
            _first_token = True
            for chunk in pipe._llm.stream(prompt):
                if _first_token:
                    _t_first_token = _time.time() - _t_llm_start
                    _first_token = False
                print(chunk, end="", flush=True)
                full_answer += chunk
            _t_llm_total = _time.time() - _t_llm_start
            print()
            print(f"[[timer]LLM 首token: {_t_first_token:.2f}s | 生成总耗时: {_t_llm_total:.2f}s | 全流程: {_time.time() - _t_start:.2f}s]", flush=True)

            # 保存到对话历史
            chat_history.append({"role": "user", "content": question})
            chat_history.append({"role": "assistant", "content": full_answer})

            # 限制历史长度
            if len(chat_history) > max_history * 2:
                chat_history = chat_history[-max_history * 2:]

        except LLMError as e:
            print(f"\n  ⚠ LLM 错误: {e}")
        except Exception as e:
            print(f"\n  ⚠ 错误: {type(e).__name__}: {e}")


def cmd_init_db(args):
    """初始化数据库 + 创建默认用户和示例知识库。"""
    from rag.database import get_db
    from rag.auth import hash_password

    db = get_db()
    print("✓ 数据库已初始化:", db._db_path)

    # 创建默认管理员
    admin = db.get_user(username="admin")
    if not admin:
        admin_id = db.add_user(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="系统管理员",
            department="dev",
            role="admin",
        )
        print(f"✓ 管理员已创建: admin / admin123 (id={admin_id})")
    else:
        print(f"  管理员已存在 (id={admin['id']})")

    # 为三个部门创建默认用户
    defaults = [
        ("dev_user", "dev123", "开发工程师", "dev"),
        ("test_user", "test123", "测试工程师", "test"),
        ("product_user", "product123", "产品工程师", "product"),
    ]
    for username, pw, display, dept in defaults:
        existing = db.get_user(username=username)
        if not existing:
            uid = db.add_user(
                username=username,
                password_hash=hash_password(pw),
                display_name=display,
                department=dept,
            )
            print(f"✓ 用户已创建: {username} / {pw} (id={uid}, dept={dept})")
        else:
            print(f"  用户已存在: {username} (id={existing['id']})")

    # 为每个部门创建一个默认知识库
    from rag.kb_manager import KBManager
    mgr = KBManager()
    for dept, dept_name in [("dev", "开发部"), ("test", "测试部"), ("product", "产品部")]:
        user = db.get_user(username=f"{dept}_user")
        admin_user = db.get_user(username="admin")
        owner = user if user else admin_user
        kbs = db.list_kbs(user_id=owner["id"])
        if not kbs:
            kb = mgr.create_kb(
                name=f"{dept_name}知识库",
                owner={"user_id": owner["id"], "department": dept},
                department=dept,
                description=f"{dept_name}默认知识库",
            )
            print(f"✓ 知识库已创建: {kb['name']} (id={kb['id']}, collection={kb['collection_name']})")
        else:
            print(f"  知识库已存在: {kbs[0]['name']} (id={kbs[0]['id']})")


def cmd_user(args):
    """用户管理。"""
    if not args:
        print("用法: python -m rag.main user <add|list> [...]")
        return

    from rag.database import get_db
    from rag.auth import hash_password

    db = get_db()
    sub = args[0].lower()
    rest = args[1:]

    if sub == "add":
        if len(rest) < 4:
            print("用法: python -m rag.main user add <username> <password> <display_name> <dept>")
            return
        username, password, display_name, dept = rest[0], rest[1], rest[2], rest[3]
        if dept not in ("dev", "test", "product"):
            print("错误: 部门必须是 dev / test / se")
            return

        existing = db.get_user(username=username)
        if existing:
            print(f"错误: 用户 {username} 已存在 (id={existing['id']})")
            return

        uid = db.add_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            department=dept,
        )
        print(f"✓ 用户已创建: {username} (id={uid}, dept={dept})")

    elif sub == "list":
        dept = None
        if "--dept" in rest:
            idx = rest.index("--dept")
            if idx + 1 < len(rest):
                dept = rest[idx + 1]
        users = db.list_users(department=dept)
        print(f"{'ID':<5} {'用户名':<15} {'显示名':<10} {'部门':<6} {'角色':<6}")
        print("-" * 50)
        for u in users:
            print(f"{u['id']:<5} {u['username']:<15} {u['display_name']:<10} "
                  f"{u['department']:<6} {u['role']:<6}")
    else:
        print(f"未知子命令: {sub}")


def cmd_kb(args):
    """知识库管理。"""
    if not args:
        print("用法: python -m rag.main kb <create|list|delete|docs> [...]")
        return

    from rag.database import get_db
    from rag.kb_manager import KBManager

    db = get_db()
    mgr = KBManager()
    sub = args[0].lower()
    rest = args[1:]

    if sub == "create":
        if len(rest) < 2:
            print("用法: python -m rag.main kb create <name> <owner_id> [--dept dev] [--desc '描述']")
            return
        name = rest[0]
        owner_id = int(rest[1])
        dept = "dev"
        desc = ""

        owner_user = db.get_user(user_id=owner_id)
        if not owner_user:
            print(f"错误: 用户 {owner_id} 不存在")
            return
        owner = {"user_id": owner_id, "department": owner_user["department"]}

        if "--dept" in rest:
            idx = rest.index("--dept")
            if idx + 1 < len(rest):
                dept = rest[idx + 1]
        if "--desc" in rest:
            idx = rest.index("--desc")
            if idx + 1 < len(rest):
                desc = rest[idx + 1]

        kb = mgr.create_kb(name=name, owner=owner, department=dept, description=desc)
        print(f"✓ 知识库已创建:")
        print(f"  ID: {kb['id']}")
        print(f"  名称: {kb['name']}")
        print(f"  Collection: {kb['collection_name']}")
        print(f"  部门: {kb['department']}")

    elif sub == "list":
        user_id = None
        if "--user" in rest:
            idx = rest.index("--user")
            if idx + 1 < len(rest):
                user_id = int(rest[idx + 1])
        kbs = db.list_kbs(user_id=user_id)
        print(f"{'ID':<5} {'名称':<20} {'Collection':<20} {'部门':<6} {'文档':<5} {'状态'}")
        print("-" * 80)
        for kb in kbs:
            doc_count = db.get_document_count(kb["id"])
            status = "活跃" if kb["is_active"] else "禁用"
            print(f"{kb['id']:<5} {kb['name']:<20} {kb['collection_name']:<20} "
                  f"{kb['department']:<6} {doc_count:<5} {status}")

    elif sub == "delete":
        if len(rest) < 1:
            print("用法: python -m rag.main kb delete <kb_id>")
            return
        kb_id = int(rest[0])
        kb = db.get_kb(kb_id=kb_id)
        if not kb:
            print(f"错误: 知识库 {kb_id} 不存在")
            return
        print(f"确认删除知识库: {kb['name']} (id={kb_id})? 这将同时删除所有相关数据。")
        confirm = input("输入 'yes' 确认: ")
        if confirm.lower() == "yes":
            mgr.delete_kb(kb_id, {"user_id": kb["owner_id"], "role": "admin"})
            print(f"✓ 知识库 {kb_id} 已删除")
        else:
            print("已取消")

    elif sub == "docs":
        if len(rest) < 1:
            print("用法: python -m rag.main kb docs <kb_id>")
            return
        kb_id = int(rest[0])
        docs = db.list_documents(kb_id=kb_id, limit=999)
        print(f"知识库 {kb_id} 的文档 ({len(docs)} 条):")
        print(f"{'ID':<5} {'文件名':<30} {'状态':<12} {'Chunks':<7} {'上传时间'}")
        print("-" * 85)
        for d in docs:
            print(f"{d['id']:<5} {d['file_name']:<30} {d['status']:<12} "
                  f"{d['chunk_count']:<7} {d['uploaded_at'] or '-'}")
    else:
        print(f"未知子命令: {sub}")


def cmd_info(args):
    """查看向量库状态。"""
    from rag.pipeline import Pipeline
    from rag.database import get_db

    pipe = Pipeline()
    db = get_db()

    print("═" * 50)
    print("  系统状态")
    print("═" * 50)
    stats = db.get_stats()
    print(f"  用户数: {stats['users']}")
    print(f"  知识库: {stats['knowledge_bases']}")
    print(f"  文档数: {stats['documents']}")
    print(f"  Chunks: {stats['chunks']}")
    print()
    print(f"  向量库路径: {pipe._config.store.persist_dir}")
    print(f"  ChromaDB Collections: {pipe.store.list_collections()}")
    print(f"  数据库: {db._db_path}")
    print()

    # LLM 状态
    health = pipe.check_llm()
    print(f"  LLM 状态: {health['status']}")
    if health["status"] == "ok":
        print(f"    目标模型: {health['target_model']} "
              f"({'✓ 已下载' if health['model_available'] else '✗ 未下载'})")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    commands = {
        "ingest": cmd_ingest,
        "search": cmd_search,
        "ask": cmd_ask,
        "chat": cmd_chat,
        "info": cmd_info,
        "init-db": cmd_init_db,
        "user": cmd_user,
        "kb": cmd_kb,
    }

    if cmd in commands:
        commands[cmd](args)
    else:
        print(f"未知命令: {cmd}")
        print(f"可用命令: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
