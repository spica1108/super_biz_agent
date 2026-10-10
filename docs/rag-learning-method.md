# RAG 学习方法论

> 如何用 `docs/rag-learning-guide.md` + Wiki 文章高效吃透这个项目的 RAG 体系。

---

## 两种资料对比

| 维度 | rag-learning-guide.md | Wiki 文章 (.zread/wiki/) |
|------|----------------------|--------------------------|
| **定位** | 骨架地图 | 专题教科书 |
| **粒度** | 1125 行，一个文件贯通 | 单篇 ~500 行，32 篇独立成章 |
| **风格** | 代码先行，行号+片段+一句话解释 | 叙述先行，背景→原理→设计取舍→总结 |
| **图示** | ASCII 手绘，结构精简 | Mermaid 渲染，时序图/架构图/流程图 |
| **知识点** | 行内标注，一句话点明 | 单独章节展开，有对比表格、使用场景 |
| **组织方式** | 按**数据流**（从摄入到检索到回答） | 按**模块**（每篇一个类/一个文件） |
| **覆盖广度** | 仅 RAG 核心链路 | 覆盖全项目（含 MCP、AIOps、部署） |
| **适合场景** | 快速建立全局认知、跟代码调试时对照 | 深入理解某个模块、面试准备 |

---

## 三阶段学习法

### Phase 1：骨架先行（~1h）

**目标：** 建立导航地图——知道每个模块干什么、调谁、被谁调。

**用什么：** 只读 `rag-learning-guide.md`。

**怎么读：** 看小节标题 + 调用链图 + 每个类的方法表。代码片段可以扫一眼跳过，不需要深究每个参数为什么这么传。

**读到什么程度算够：** 能不看文档说出下面这张表：

| 类 | 方法 | 一句话 |
|---|---|---|
| `VectorIndexService` | `index_single_file()` | 读文件→删旧数据→分割→写入 Milvus |
| `DocumentSplitterService` | `split_markdown()` | Markdown 按标题→长度两阶段切分 |
| `DashScopeEmbeddings` | `embed_documents()` | 多条文本 → 批量调 API → 向量列表 |
| | `embed_query()` | 单条文本 → 调 API → 一个向量 |
| `VectorStoreManager` | `add_documents()` | 文档列表 → 向量化 → 写入 Milvus |
| | `delete_by_source()` | 按文件路径删旧向量 |
| `RagAgentService` | `query()` | 发问题 → Agent 跑完 → 返回完整答案 |
| | `query_stream()` | 发问题 → Agent 逐 token 流式产出 |

这里的"知道"定义：**入参是什么、出参是什么、内部调了谁**。

**注意区分：**

| Phase 1 需要看懂 | Phase 1 不需要纠结 |
|------------------|-------------------|
| 这个模块干什么活 | 这个活具体怎么干的 |
| 它调谁、被谁调 | 每个参数为什么这么传 |
| 数据从哪来、到哪去 | 边界条件怎么处理的 |
| 有哪些关键概念需要后续学 | 每个概念的完整定义 |

---

### Phase 2：主题深入（每个主题 ~30min）

**目标：** 读懂设计原理——每个模块为什么这么设计，参数怎么选，边界怎么处理。

**用什么：** Guide + Wiki + 源码，三栏对照。

**Guide ↔ Wiki 对照表：**

| 学习主题 | Guide | Wiki | 核心源码 |
|---------|-------|------|---------|
| 文档摄入 | Step 2 | **17**（分割管线）+ **04**（知识库初始化） | `document_splitter_service.py` |
| 向量嵌入 | Step 3 | **18**（Embedding 统一接口） | `vector_embedding_service.py` |
| Milvus 存储 | Step 4 | **09**（Milvus 集成）+ **19**（VectorStore 管理） | `milvus_client.py` |
| 知识检索 | Step 5 | **20**（本地工具集）+ **31**（@tool 开发） | `knowledge_tool.py` |
| Agent 核心 | Step 6 | **15**（Agent 架构）+ **16**（流式 SSE） | `rag_agent_service.py` |
| API 层 | Step 7 | **30**（API 设计模式）+ **05**（接口速览） | `chat.py` |
| 配置/LLM | Step 1 | **07**（配置体系）+ **08**（LLM 工厂） | `config.py` |

**具体操作：** IDE 左侧开 Guide，右侧开 Wiki，中间开源码。Guide 给代码定位（行号），Wiki 给设计背景（为什么），源码验证理解。

---

### Phase 3：交叉验证（按需）

两种资料的 **独门内容**：

**Guide 独有：**
- 写入/检索两条数据流的 ASCII 全景图
- `_merge_small_chunks` 的逐行注释解释
- L2 vs Cosine、IVF_FLAT 原理等算法级知识点
- 两周学习路线图

**Wiki 独有：**
- Mermaid 时序图/架构图
- 设计决策的"为什么"（如 chunk_size 翻倍到 1600）
- 预留扩展点说明（API 层的事件类型兼容设计）
- MCP、AIOps、部署等 RAG 外围模块

遇到不懂的代码 → 回 Guide 找上下游关系。看不懂 Wiki 里的设计决策 → 回 Guide 看代码怎么落地。Guide 和 Wiki 说不一致的地方 → 以源码为准。

---

## 学习路线图

```
Phase 1 (~1h)           Phase 2 (每主题 ~30min)          Phase 3 (按需)
─────────────           ──────────────────────          ────────────
rag-learning-guide.md    Guide + Wiki + 源码              交叉验证
       │                        │
       ├─ Step 1 ────────────── 07 + 08 + config.py
       ├─ Step 2 ────────────── 17 + 04 + document_splitter_service.py
       ├─ Step 3 ────────────── 18 + vector_embedding_service.py
       ├─ Step 4 ────────────── 09 + 19 + milvus_client.py
       ├─ Step 5 ────────────── 20 + 31 + knowledge_tool.py
       ├─ Step 6 ────────────── 15 + 16 + rag_agent_service.py
       └─ Step 7 ────────────── 30 + 05 + chat.py
       │
       ▼
  能画出全部数据流图
  能背出每个类的方法表
```

**验证标准（Phase 1 完成时）：** 不翻书能画出下面这两条链路：

```
写入：上传文件 → VectorIndexService.index_single_file()
        → DocumentSplitterService.split_document()
        → VectorStoreManager.add_documents()
        → Embedding → Milvus

检索：用户提问 → RagAgentService.query()
        → Agent 判断需要检索 → retrieve_knowledge()
        → VectorStoreManager.as_retriever().invoke()
        → Embedding → Milvus search → format_docs() → LLM 生成
```

**验证标准（Phase 2 完成时）：** 能回答以下问题：
- Markdown 分割为什么是三阶段？为什么 h3 不参与标题分割？
- `embed_documents` 和 `embed_query` 为什么要分成两个方法？
- `MilvusClientManager` 和 `VectorStoreManager` 两层封装各管什么？
- Agent 怎么决定是否调用 `retrieve_knowledge`？调用后结果怎么回到 LLM？
- SSE 流式从 LLM token 到前端 DOM 经过了哪些转换？

---

## 两种资料各自的定位类比

| | 相当于 |
|---|------|
| **rag-learning-guide.md** | 一张地铁线路图——只标站点和换乘关系，不画每栋楼的样子 |
| **Wiki 文章** | 每个站点的游览手册——讲这个站附近有什么、为什么值得看、怎么逛 |
| **源码** | 实际的城市街道——地图和手册都是它的抽象，最终以它为准 |
