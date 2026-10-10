# Phase 1 学习方法：骨架先行

> Phase 1 的核心思想：**先建地图，再逛街道。** 不知道自己在哪，看细节只会更晕。

---

## 一句话定义

**知道每个类封装了什么方法、每个方法是干什么的、方法之间怎么调用。** 不需要知道方法内部怎么实现、参数为什么这么传、边界条件怎么处理。

---

## 够用的认知水平（举例）

以文档摄入链路为例，Phase 1 看下面这张表就够：

| 调用顺序 | 类 | 方法 | 一句话 |
|---------|---|------|--------|
| 1 | API 层 | `upload_file()` | 接收文件，调 `index_single_file()` |
| 2 | `VectorIndexService` | `index_single_file()` | 读文件→删旧数据→分割→写入 Milvus |
| 3 | `DocumentSplitterService` | `split_document()` | 判断文件类型，分发给 `split_markdown()` 或 `split_text()` |
| 3.1 | | `split_markdown()` | 标题分割→递归字符分割→合并小碎片 |
| 4 | `VectorStoreManager` | `delete_by_source()` | 按文件路径删掉旧向量（覆盖更新） |
| 5 | | `add_documents()` | 调 Embedding → 写入 Milvus |

到这一步就停。**不需要**追问：
- `_merge_small_chunks` 为什么 `min_size=300`
- `RecursiveCharacterTextSplitter` 的分隔符优先级怎么设计
- `normalized_path = path.as_posix()` 和 `str(path)` 有什么区别

---

## Phase 1 的边界：看懂 vs 跳过

| 看懂（Phase 1 的任务） | 跳过（Phase 2 再搞） |
|------------------------|---------------------|
| 这个模块干什么活 | 这个活具体怎么干的 |
| 它调谁、被谁调 | 每个参数为什么这么传 |
| 数据从哪来、到哪去 | 边界条件怎么处理的 |
| 有哪些关键概念需要后续学 | 每个概念的完整定义 |
| 入参是什么类型、出参是什么类型 | 内部有哪些中间变量 |
| 异常大致怎么传播（抛出去还是吞掉） | 每种异常的精确处理逻辑 |

---

## RAG 全链路 Phase 1 速查表

读完 Guide 每个 Step 后，你应该能不看文档说出下面这张表。**这是 Phase 1 的验收标准。**

### 写入链路

| 类 | 方法 | 一句话 |
|---|---|---|
| `file.upload_file` | — | 接收 txt/md 文件，保存到 uploads/，调索引 |
| `VectorIndexService` | `index_single_file(path)` | 编排：读→删→分→写 |
| | `index_directory(path)` | 遍历目录，逐文件调 `index_single_file` |
| `DocumentSplitterService` | `split_document(content, path)` | .md → `split_markdown`，.txt → `split_text` |
| | `split_markdown(content, path)` | 标题分割→字符分割→合并碎片 |
| | `split_text(content, path)` | 递归字符分割 |
| `VectorStoreManager` | `add_documents(docs)` | 生成 UUID → 调 Embedding → 写入 Milvus |
| | `delete_by_source(path)` | Milvus 标量过滤删旧数据 |
| `DashScopeEmbeddings` | `embed_documents(texts)` | 批量文本 → OpenAI API → 向量列表 |
| `MilvusClientManager` | `connect()` | 建立连接 + 创建/校验 Collection + 加载 |

### 检索链路

| 类 | 方法 | 一句话 |
|---|---|---|
| `RagAgentService` | `query(question, session_id)` | 发问题 → Agent.run → 返回完整答案 |
| | `query_stream(question, session_id)` | 发问题 → Agent 流式产出 token |
| | `get_session_history(id)` | 从 MemorySaver 读对话历史 |
| | `clear_session(id)` | 删 MemorySaver 中指定对话 |
| `retrieve_knowledge` | `retrieve_knowledge(query)` | 向量检索 → format_docs → 返回格式化上下文 |
| `VectorStoreManager` | `similarity_search(query, k)` | 调 Embedding → Milvus search |
| | `as_retriever(k)` | 包装为 LangChain Retriever 对象 |
| `DashScopeEmbeddings` | `embed_query(text)` | 单条文本 → OpenAI API → 一个向量 |

### 基础设施

| 类 | 方法 | 一句话 |
|---|---|---|
| `Settings(config)` | — | 从 .env 加载 RAG/Milvus/Embedding 参数 |
| `LLMFactory` | `create_chat_model(...)` | 创建 ChatOpenAI 实例（支持多 Provider） |
| `MilvusClientManager` | `connect()` | 连接 Milvus，管理 Collection 生命周期 |
| | `get_collection()` | 返回 pymilvus Collection 对象 |
| | `health_check()` | 检查 Milvus 连通性 |
| | `close()` | 释放连接 |

---

## Phase 1 操作流程

```
1. 打开 rag-learning-guide.md
2. 从 Step 0 总览开始，看懂架构全景图和两条数据流
3. 依次读 Step 1→7，每个 Step：
   a. 看小节标题 + 第一段（知道这步在讲什么）
   b. 看调用链/架构图（知道谁调谁）
   c. 看方法表（如果有的话）
   d. 代码片段扫一眼就过，不纠结细节
4. 读完后合上文档，自己画出：
   - 写入链路的调用顺序
   - 检索链路的调用顺序
5. 画不出来 → 回去补那一步
```

预计时间：**30-60 分钟**。

---

## Phase 1 完成标准

不翻任何资料，能写出：

```
写入：上传文件 → VectorIndexService.index_single_file()
        → DocumentSplitterService.split_document()
        → VectorStoreManager.add_documents()
        → DashScopeEmbeddings.embed_documents()
        → Milvus

检索：用户提问 → RagAgentService.query() [Agent 内部]
        → Agent 决定调 retrieve_knowledge()
        → VectorStoreManager.as_retriever().invoke()
        → DashScopeEmbeddings.embed_query()
        → Milvus search
        → format_docs() 格式化
        → LLM 生成回答
```

做到这一步，Phase 1 就完成了。**然后带着这张地图进入 Phase 2，去 Wiki 和源码里看每栋"楼"长什么样。**
