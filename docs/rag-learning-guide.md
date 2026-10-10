# SuperBizAgent RAG 学习指南

> 从零理解一个生产级 Agentic RAG 系统。按数据流向，7 步贯通全部链路。

---

## 0. 总览

### 一句话定位

这是一个 **Agentic RAG** 系统：LLM 作为 Agent **自主决定**何时调用知识检索工具，而不是每次对话都固定执行 retrieve→augment→generate 三部曲。

| 模式 | 流程 | 本项目 |
|------|------|--------|
| 传统 RAG | 用户提问 → **必定检索** → 拼上下文 → 生成回答 | ❌ |
| Agentic RAG | 用户提问 → **Agent 判断是否需要检索** → 需要则调工具 → 生成回答 | ✅ |

### 技术栈全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (static/)                            │
│                    SSE / HTTP JSON                               │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                    FastAPI (app/main.py)                         │
│  路由: /api/chat  /api/chat_stream  /api/upload  /api/health   │
└───────┬──────────────────────────────────┬──────────────────────┘
        │                                  │
        │  检索链路                          │  写入链路
        ▼                                  ▼
┌───────────────────┐              ┌──────────────────┐
│  RagAgentService  │              │ VectorIndexService│
│  (LangGraph Agent)│              │  (索引编排器)      │
└────────┬──────────┘              └────────┬─────────┘
         │                                  │
         │ 工具调用                           │ 分割
         ▼                                  ▼
┌───────────────────┐              ┌──────────────────────┐
│  retrieve_knowledge│             │DocumentSplitterService│
│  (LangChain Tool)  │              │ (Markdown/Text分割)   │
└────────┬──────────┘              └────────┬─────────────┘
         │                                  │
         │ 向量检索                           │ 写入向量
         ▼                                  ▼
┌─────────────────────────────────────────────────────┐
│              VectorStoreManager                      │
│         (langchain_milvus.Milvus 封装)               │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│            DashScopeEmbeddings                       │
│     (LangChain Embeddings 接口 → OpenAI API)         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│            MilvusClientManager                       │
│     (pymilvus 连接/Collection/Index 生命周期)         │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │  Milvus 向量数据库 │
              │  Collection: biz  │
              │  Dim: 1024, L2   │
              └──────────────────┘
```

### 两条核心数据流

**写入链路（文档入库）：**
```
用户上传文件 → file.py 接收 → VectorIndexService 编排
  → 1. 读文件内容
  → 2. 删旧向量 (delete_by_source)
  → 3. DocumentSplitterService 分割 (Markdown三阶段 / Text单阶段)
  → 4. VectorStoreManager.add_documents() → 调用 Embedding → 写入 Milvus
```

**检索链路（问答）：**
```
用户提问 → chat.py → RagAgentService (LangGraph Agent)
  → Agent 判断需要检索 → 调用 retrieve_knowledge 工具
  → VectorStoreManager.as_retriever() → Embedding → Milvus search
  → format_docs() 格式化 → 拼入 LLM 上下文 → 生成回答
```

---

## 1. Step 1：配置入口

### 文件：[app/config.py](../app/config.py)

所有 RAG 相关参数集中在一个 Pydantic Settings 类中，从 `.env` 文件加载。

### 关键字段（行 44-55）

```python
# RAG 配置                                # 行号
rag_top_k: int = 3                         # 50  每次检索返回几个文档
rag_model: str = "qwen-max"                # 51  RAG 对话用的 LLM 模型

# 文档分块配置
chunk_max_size: int = 800                  # 54  每个分片最大字符数
chunk_overlap: int = 100                   # 55  相邻分片重叠字符数

# Milvus 配置
milvus_host: str = "localhost"             # 45
milvus_port: int = 19530                   # 46

# Embedding 配置
embedding_model: str = ""                  # 41  默认走 text-embedding-v4
embedding_api_key: str = ""                # 39
embedding_base_url: str = ""               # 40  支持 DashScope/火山方舟
```

### 知识点：Pydantic Settings

- `SettingsConfigDict(env_file=".env")` → 自动从 `.env` 读环境变量，字段名与变量名做 case-insensitive 匹配
- `@field_validator` 可以在加载后做二次处理（例如把 `debug=release` 转为 `False`）
- 全局单例 `config = Settings()` 在 `config.py:92`，整个项目 `from app.config import config` 即可用

**为什么用 Pydantic Settings 而不是 `os.getenv`：**
- 类型安全（`int` 字段自动转换）
- 默认值集中可见
- IDE 有自动补全

---

## 2. Step 2：文档摄入（Ingestion Pipeline）

### 调用链全景图

```
 POST /api/upload
        │  file.py:21  upload_file()
        │  file.py:73  vector_index_service.index_single_file(str(file_path))
        ▼
 VectorIndexService.index_single_file()          # vector_index_service.py:131
        │
        ├─ 1. path.read_text()                    # :151  读取文件内容
        ├─ 2. vector_store_manager.delete_by_source()  # :157  删旧数据
        ├─ 3. document_splitter_service.split_document() # :160  分割文档
        └─ 4. vector_store_manager.add_documents() # :165  写入 Milvus
                 │
                 ▼
        DocumentSplitterService.split_document()  # document_splitter_service.py:118
                 │
                 ├─ .md 文件 → split_markdown()   # :45  三阶段分割
                 └─ .txt 文件 → split_text()      # :83  单阶段分割
                          │
                          ▼
        VectorStoreManager.add_documents()        # vector_store_manager.py:72
                 │
                 ├─ uuid 生成 id                   # :89
                 └─ vector_store.add_documents()   # :93  自动调 embedding + 写入
```

### 2.1 API 入口：[app/api/file.py](../app/api/file.py)

**`upload_file()` — 行 21-92：**

```python
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # 1. 验证扩展名 (只允许 txt/md)         # :41-46
    # 2. 创建 uploads/ 目录                 # :49
    # 3. 保存文件到 uploads/                 # :60-66
    # 4. 自动触发向量索引！                  # :71-74
    vector_index_service.index_single_file(str(file_path))
```

关键设计：**上传即索引** — 文件落地后立即调用 `index_single_file`，对用户来说上传完成即可检索。

### 2.2 索引编排器：[app/services/vector_index_service.py](../app/services/vector_index_service.py)

**`index_single_file()` — 行 131-172：**

```python
def index_single_file(self, file_path: str):
    # 1. 读取文件内容
    content = path.read_text(encoding="utf-8")            # :151

    # 2. 删除该文件的旧向量数据（支持覆盖更新）
    normalized_path = path.as_posix()                     # :156
    vector_store_manager.delete_by_source(normalized_path) # :157

    # 3. 分割文档
    documents = document_splitter_service.split_document( # :160
        content, normalized_path
    )

    # 4. 批量写入 Milvus
    if documents:
        vector_store_manager.add_documents(documents)     # :165
```

**为什么先删再写？** 因为目标是"覆盖更新"而不是"追加"。如果同个文件上传两次，不删旧数据会导致检索出重复内容。

### 2.3 文档分割器（重点）：[app/services/document_splitter_service.py](../app/services/document_splitter_service.py)

这是整个摄入链路最值得细读的部分。Markdown 文件走 **三阶段分割**：

```
原始 Markdown
      │
      ▼
┌─ 第1阶段 ─────────────────────────────────────┐
│ MarkdownHeaderTextSplitter(:45)                │
│ headers_to_split_on=[("#","h1"), ("##","h2")] │
│ strip_headers=False  ← 标题保留在正文中         │
│                                                │
│ 输出：按 # 和 ## 切分后的文档列表               │
│ 每个文档的 metadata 带有 h1/h2 标题信息         │
└──────────────────┬─────────────────────────────┘
                   ▼
┌─ 第2阶段 ─────────────────────────────────────┐
│ RecursiveCharacterTextSplitter(:32)            │
│ chunk_size=1600, chunk_overlap=100             │
│                                                │
│ 把超过 1600 字符的文档继续切分                  │
│ 切割优先级：\n\n → \n → 空格 → 字符            │
└──────────────────┬─────────────────────────────┘
                   ▼
┌─ 第3阶段 ──────────────────────────────────────┐
│ _merge_small_chunks(:134)                      │
│ min_size=300                                    │
│                                                 │
│ 把不足 300 字符的相邻片段合并                    │
│ 避免碎片化，但总大小不超过 chunk_size*2(1600)    │
└────────────────────────────────────────────────┘
                   │
                   ▼
             最终分片列表
```

**`_merge_small_chunks()` — 行 134-172：**

```python
def _merge_small_chunks(self, documents, min_size=300):
    merged_docs = []
    current_doc = None

    for doc in documents:
        doc_size = len(doc.page_content)

        if current_doc is None:
            current_doc = doc
        elif doc_size < min_size and len(current_doc.page_content) < self.chunk_size * 2:
            # 当前文档太小 且 合并后不会太大 → 合并
            current_doc.page_content += "\n\n" + doc.page_content
        else:
            # 保存当前，开始新的
            merged_docs.append(current_doc)
            current_doc = doc

    if current_doc is not None:
        merged_docs.append(current_doc)
    return merged_docs
```

### 知识点：分割策略详解

**为什么需要 chunk_overlap？**
```
文档:  "...配置 A 的参数很重要。同时，配置 B 也需要..."
                  ↑ 切分点 ↑

不做 overlap → chunk1: "...配置 A 的参数很重要。"  chunk2: "同时，配置 B 也需要..."
做 overlap   → chunk1: "...配置 A 的参数很重要。同时，"  chunk2: "...参数很重要。同时，配置 B 也需要..."
```

overlap 让相邻分片共享部分内容，避免关键信息正好落在分片边界上被割裂。

**为什么 Markdown 用标题分割器？**
- Markdown 的 `#` `##` 是天然的语义边界
- 按标题切分后，每个分片自带标题元数据（`metadata["h1"]`、`metadata["h2"]`）
- 检索时 `format_docs()` 会展示标题路径，LLM 能更好理解上下文

**为什么 Markdown 不做 `###`（h3）分割？**
```python
headers_to_split_on=[
    ("#", "h1"),
    ("##", "h2"),
    # 不再按三级标题分割，避免过度碎片化  ← 注释在 :27
]
```
切太细会导致每个分片只有几句话，缺乏上下文，检索质量反而下降。

**`strip_headers=False` 的含义：**
- `True`：标题放在 metadata 里，正文不含标题
- `False`：标题同时出现在正文和 metadata 中 → LLM 看到的上下文更完整

---

## 3. Step 3：向量嵌入

### 文件：[app/services/vector_embedding_service.py](../app/services/vector_embedding_service.py)

### 类图

```
LangChain Embeddings (抽象接口)
  ├─ embed_documents(texts) → List[List[float]]  批量嵌入
  └─ embed_query(text) → List[float]              查询嵌入
        ↑
        │ 实现
        │
  DashScopeEmbeddings(:13)
  ├─ 字段：
  │   ├─ api_key       — DashScope/火山方舟 API Key
  │   ├─ model         — 默认 text-embedding-v4
  │   ├─ dimensions    — 1024
  │   ├─ base_url      — API 地址
  │   └─ client: OpenAI — 延迟初始化
  │
  ├─ 公开方法：
  │   ├─ embed_documents(:158)   → 批量调 OpenAI embeddings.create()
  │   ├─ embed_query(:197)       → 单条调 OpenAI embeddings.create()
  │   └─ embed_multimodal(:131)  → 多模态（文本+图片+视频）
  │
  └─ 内部方法：
      ├─ _ensure_client(:63)      → 按需创建 OpenAI 客户端
      ├─ _is_placeholder_key(:57) → 检测 API Key 是否占位符
      └─ _mask_api_key(:50)       → 日志脱敏
```

### 核心代码

**`embed_documents()` — 行 158-195：**

```python
def embed_documents(self, texts: List[str]) -> List[List[float]]:
    if not texts:
        return []

    # 多模态 endpoint → 逐个调 HTTP POST
    if self._use_multimodal_endpoint:
        embeddings = [self._embed_text_multimodal(text) for text in texts]
        return embeddings

    # 标准 OpenAI 兼容 endpoint → 批量调
    client = self._ensure_client()
    response = client.embeddings.create(
        model=self.model,
        input=texts,           # 一次传入多条文本
        dimensions=self.dimensions,
        encoding_format="float"
    )
    embeddings = [item.embedding for item in response.data]
    return embeddings
```

**`embed_query()` — 行 197-233：**

```python
def embed_query(self, text: str) -> List[float]:
    # 结构几乎一样，但 input=text 是单条
    response = client.embeddings.create(
        model=self.model,
        input=text,            # 单条文本
        dimensions=self.dimensions,
        encoding_format="float"
    )
    embedding = response.data[0].embedding
    return embedding
```

### 知识点：`embed_documents` vs `embed_query`

LangChain 把这两个方法分开是有原因的：

| | `embed_documents` | `embed_query` |
|---|---|---|
| 用途 | 入库时批量向量化文档 | 检索时向量化用户问题 |
| 输入 | `List[str]` | `str` |
| 输出 | `List[List[float]]` | `List[float]` |
| 典型调用者 | `VectorStoreManager.add_documents()` | `VectorStoreManager.similarity_search()` |

有些 embedding 模型对文档和查询使用**不同的编码策略**（非对称 embedding），比如 query 侧用更轻量的编码。分开两个方法为这种优化留了接口。

### 知识点：延迟初始化模式

```python
def _ensure_client(self) -> OpenAI:
    if self.client is not None:      # 已创建 → 直接返回
        return self.client

    if self._is_placeholder_key(self.api_key):
        raise ValueError("请设置 EMBEDDING_API_KEY")

    self.client = OpenAI(            # 首次调用时才创建
        api_key=self.api_key,
        base_url=self.base_url,
    )
    return self.client
```

**为什么这么设计？** `vector_embedding_service` 是模块级全局单例（行 244），在 `import` 时就会创建。如果直接在 `__init__` 里初始化 OpenAI 客户端，而 `.env` 还没配好 API Key，整个应用启动就会崩溃。延迟初始化让：
- 应用能正常启动（只打 warning 日志）
- 真正调用 embedding 时才报明确的错误

### 知识点：OpenAI 兼容 API

本项目没有直连 DashScope SDK，而是统一走 OpenAI 兼容协议：

```
DashScopeEmbeddings
      │
      ▼
  OpenAI 客户端 (openai 库)
      │  base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
      │  POST /v1/embeddings
      ▼
  阿里云 DashScope 后端
```

这样做的好处是同一套代码可以切到火山方舟或其他兼容服务，只改 `base_url` 即可：

```python
# vector_embedding_service.py:237-242  — 根据 llm_provider 自动选 base_url
default_embedding_base_url = (
    "https://ark.cn-beijing.volces.com/api/v3"     # 火山方舟
    if embedding_provider == "volcengine"
    else "https://dashscope.aliyuncs.com/compatible-mode/v1"  # DashScope
)
```

### 知识点：L2 距离 vs Cosine 距离

本项目 Milvus 使用 **L2（欧氏距离）**：
```python
# milvus_client.py:198
index_params = {"metric_type": "L2"}
```

| 度量 | 公式简述 | 特点 |
|------|---------|------|
| **L2** | √Σ(ai - bi)² | 值越小越相似。对向量大小敏感 |
| **Cosine** | 1 - (a·b)/(‖a‖‖b‖) | 只看方向不看长度。文本 embedding 更常用 |

大部分文本 embedding 模型（包括 text-embedding-v4）输出的是**归一化向量**，此时 L2 和 Cosine 等价。本项目选 L2 不会影响效果。

---

## 4. Step 4：向量存储

### 两层封装架构

```
┌─────────────────────────────────────────────────────────┐
│  VectorStoreManager (vector_store_manager.py)            │
│  上层封装：LangChain 标准接口                             │
│                                                         │
│  - add_documents(docs) → 自动调 embedding + 写入         │
│  - delete_by_source(path) → 按文件路径删除               │
│  - similarity_search(query,k) → 查询                     │
│  - as_retriever() → 返回 LangChain Retriever 对象        │
│                                                         │
│  内部持有: langchain_milvus.Milvus 实例                  │
│  配置: collection="biz",                                  │
│        text_field="content", vector_field="vector"        │
└───────────────┬─────────────────────────────────────────┘
                │ 调用
                ▼
┌─────────────────────────────────────────────────────────┐
│  MilvusClientManager (milvus_client.py)                   │
│  底层封装：pymilvus 连接/Collection/Index 生命周期        │
│                                                         │
│  - connect() → 建立连接 + 创建/校验 Collection           │
│  - get_collection() → 返回 pymilvus Collection 对象      │
│  - health_check() / close()                              │
│                                                         │
│  管理对象: pymilvus.connections + pymilvus.Collection    │
└─────────────────────────────────────────────────────────┘
```

### 4.1 Collection Schema

```python
# milvus_client.py:149-188 — _create_collection()

fields = [
    FieldSchema(name="id",       dtype=DataType.VARCHAR,       # 主键，UUID
                max_length=100,  is_primary=True),

    FieldSchema(name="vector",   dtype=DataType.FLOAT_VECTOR,  # 向量字段
                dim=1024),                                     # 维度 = 1024

    FieldSchema(name="content",  dtype=DataType.VARCHAR,       # 原文内容
                max_length=8000),                              # 最大 8000 字符

    FieldSchema(name="metadata", dtype=DataType.JSON),         # 元数据（JSON）
]
```

| 字段 | 类型 | 内容示例 |
|------|------|---------|
| `id` | VARCHAR(100) | `"a1b2c3d4-..."` (UUID) |
| `vector` | FLOAT_VECTOR(1024) | `[0.12, -0.34, 0.56, ...]` (1024维) |
| `content` | VARCHAR(8000) | `"## CPU 使用率过高\n\n当 CPU 使用率超过..."` |
| `metadata` | JSON | `{"_source": "uploads/cpu.md", "_file_name": "cpu.md", "h1": "CPU", "h2": "排查步骤"}` |

### 4.2 索引配置

```python
# milvus_client.py:192-208 — _create_index()

index_params = {
    "metric_type": "L2",          # 距离度量
    "index_type": "IVF_FLAT",     # 索引类型
    "params": {"nlist": 128},     # 聚类中心数
}
collection.create_index(field_name="vector", index_params=index_params)
```

### 知识点：IVF_FLAT 索引

```
IVF = Inverted File Index（倒排文件索引）

工作方式：
1. 把所有向量聚成 nlist(128) 个簇（cluster）
2. 查询时，先把 query 向量找到最近的几个簇（nprobe 个）
3. 只在这些簇内部做精确（FLAT）距离计算

         全部向量 (假设 10万条)
              │
    ┌─────────┼─────────┬──────────┐
    ▼         ▼         ▼          ▼
  簇 1      簇 2      簇 3   ...  簇 128
 (约800条) (约800条) (约800条)    (约800条)
              │
    查询时只搜最近的 nprobe 个簇 ← 减少计算量
```

**参数含义：**
- `nlist=128`：分成 128 个簇。越大 → 每个簇越小 → 搜索越快，但可能漏掉边界上的相似向量
- `nprobe=10`（搜索时设置）：搜最近的 10 个簇。越大 → 召回率越高但越慢

**为什么用 IVF_FLAT 而不是更高级的索引（HNSW 等）：**
- IVF_FLAT 是 Milvus 最基础、最稳定的索引
- 本项目数据量不大（运维文档），IVF_FLAT 足够
- 生产环境大数据量可考虑 IVF_PQ（压缩）或 HNSW（图索引）

### 4.3 关键操作流程

**写入（add_documents）：**
```
vector_store_manager.add_documents(documents)
        │  vector_store_manager.py:93
        │
        ▼
  langchain_milvus.Milvus.add_documents(docs, ids=[uuid1, uuid2, ...])
        │
        ├─ 对每个 doc 调 embedding_function.embed_documents([doc1.content, doc2.content, ...])
        ├─ 构造 Milvus 插入数据
        └─ 写入 Collection: {id, vector, content, metadata}
```

**覆盖更新（delete_by_source）：**
```
vector_store_manager.delete_by_source(file_path)
        │  vector_store_manager.py:105
        │
        ▼
  collection.delete(expr='metadata["_source"] == "uploads/cpu.md"')
        │
        └─ Milvus 按表达式删除匹配行
```

这里用的是 Milvus 的**标量过滤**能力 —— JSON 字段 `metadata` 支持 `["key"]` 路径访问语法。

---

## 5. Step 5：检索链路

### 文件：[app/tools/knowledge_tool.py](../app/tools/knowledge_tool.py)

### 工具执行流程

```
Agent 决定需要检索
        │
        ▼
retrieve_knowledge(query="CPU 使用率高怎么办")
        │  knowledge_tool.py:14
        │
        ├─ 1. vector_store_manager.get_vector_store()        :29
        │      └─ 获取 langchain_milvus.Milvus 实例
        │
        ├─ 2. vector_store.as_retriever(                     :30-32
        │        search_kwargs={"k": config.rag_top_k}       → 默认 k=3
        │    )
        │      └─ 包装为 LangChain Retriever 对象
        │
        ├─ 3. retriever.invoke(query)                         :34
        │      └─ 内部：调 embedding → Milvus search → 返回 top_k 个 Document
        │
        └─ 4. format_docs(docs)                               :41
               └─ 把 Document 列表格式化为 LLM 可读的文本
```

### 核心代码

**`retrieve_knowledge()` — 行 13-48：**

```python
@tool(response_format="content_and_artifact")   # ← 关键装饰器
def retrieve_knowledge(query: str) -> Tuple[str, List[Document]]:
    """从知识库中检索相关信息来回答问题"""

    # 包装为 Retriever
    vector_store = vector_store_manager.get_vector_store()
    retriever = vector_store.as_retriever(
        search_kwargs={"k": config.rag_top_k}   # k=3
    )

    # 检索
    docs = retriever.invoke(query)

    if not docs:
        return "没有找到相关信息。", []

    # 格式化
    context = format_docs(docs)
    return context, docs
```

**`format_docs()` — 行 51-85：**

```python
def format_docs(docs: List[Document]) -> str:
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("_file_name", "未知来源")

        # 标题层级：h1 > h2 > h3
        headers = []
        for key in ["h1", "h2", "h3"]:
            if key in doc.metadata and doc.metadata[key]:
                headers.append(doc.metadata[key])
        header_str = " > ".join(headers) if headers else ""

        # 构建格式化块
        formatted = f"""【参考资料 {i}】
标题: {header_str}
来源: {source}
内容:
{doc.page_content}
"""
```

格式化后的效果示例：

```
【参考资料 1】
标题: CPU > 排查步骤
来源: cpu_high_usage.md
内容:
首先使用 top 命令查看 CPU 使用率最高的进程...
```

### 知识点：LangChain Tool 装饰器

```python
@tool(response_format="content_and_artifact")
```

- `@tool`：把普通函数变成 LangChain Agent 可调用的 Tool。LLM 看到的是函数的 `"""docstring"""`，并据此判断何时该调用
- `response_format="content_and_artifact"`：返回值是 `(text_for_llm, raw_data)` 元组
  - `text_for_llm`（第一个元素）→ 拼入 LLM 上下文
  - `raw_data`（第二个元素）→ 可以被下游逻辑获取，但 LLM 看不见

**工具选择机制（Agent 如何决定调用哪个工具）：**

```
1. Agent 初始化时，LangChain 把每个 @tool 函数的签名 + docstring
   转换为 OpenAI Function Calling 的 tool definition
2. 每轮对话，LLM 根据 system prompt + 用户问题 + tool definitions
   决定：直接回答？还是调用某个工具？
3. 如果 LLM 返回 tool_call，Agent 框架执行该函数，把返回值
   作为 tool_result 发回 LLM，LLM 基于结果生成最终回答
```

### 知识点：Retriever 模式

```python
retriever = vector_store.as_retriever(search_kwargs={"k": 3})
docs = retriever.invoke(query)
```

LangChain 的 Retriever 是一个标准化接口：

```
Retriever 接口
  └─ invoke(query: str) → List[Document]

  VectorStore.as_retriever() 只是众多实现之一，
  还可以有：TF-IDF Retriever、BM25 Retriever、Web Search Retriever 等
  它们都是同一套接口，可以互换
```

---

## 6. Step 6：Agent 层（核心）

### 文件：[app/services/rag_agent_service.py](../app/services/rag_agent_service.py)

这是整个 RAG 系统最复杂的模块，约 420 行。

### 6.1 Agent 架构图

```
┌──────────────────────────────────────────────────────────────┐
│                       用户请求                                 │
│              "CPU 使用率过高怎么办？"                           │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI API 层 (chat.py)                      │
│          query() 或 query_stream() 带 session_id               │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                  RagAgentService                               │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │               LangGraph Agent (create_agent)           │    │
│  │                                                        │    │
│  │  ┌──────────┐    ┌──────────────┐    ┌───────────┐   │    │
│  │  │  System   │    │  LLM Model   │    │  Tools    │   │    │
│  │  │  Message  │───▶│  (ChatOpenAI) │───▶│ □ knowledge│   │    │
│  │  │           │    │              │    │ □ time    │   │    │
│  │  └──────────┘    └──────┬───────┘    │ □ alerts  │   │    │
│  │                         │            │ □ MCP x N │   │    │
│  │                         │            └─────┬─────┘   │    │
│  │                         │                  │          │    │
│  │                         │  需要时调用       │          │    │
│  │                         │◄─────────────────┘          │    │
│  │                         │                             │    │
│  │                         │ 返回工具结果                 │    │
│  │                         ▼                             │    │
│  │                  生成最终回答                          │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │            MemorySaver (checkpointer)                  │    │
│  │           按 thread_id 存储对话历史                      │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │         trim_messages_middleware                       │    │
│  │    保留首条 SystemMessage + 最近 6 条                   │    │
│  └──────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 初始化流程

```python
# rag_agent_service.py:77-110
class RagAgentService:
    def __init__(self, streaming=True):
        self.model_name = config.rag_model          # "qwen-max"
        self.system_prompt = self._build_system_prompt()
        self.model = llm_factory.create_chat_model( # 创建 ChatOpenAI
            model=self.model_name,
            temperature=0.7,
            streaming=streaming,
        )
        self.tools = list(DEFAULT_LOCAL_AGENT_TOOLS) # 3 个本地工具
        self.mcp_tools = []                          # MCP 工具（延迟加载）
        self.checkpointer = MemorySaver()            # 内存级对话存储
        self.agent = None                            # Agent 延迟创建
```

**为什么 Agent 也是延迟创建的？** 因为 MCP 工具需要通过异步网络调用加载（`await get_mcp_client_with_retry()`），不能在同步的 `__init__` 里执行。

```python
# rag_agent_service.py:112-150
async def _initialize_agent(self):
    if self._agent_initialized:
        return                      # 幂等，只初始化一次

    # 加载 MCP 工具
    mcp_client = await get_mcp_client_with_retry()
    mcp_tools, mcp_err = await load_mcp_tools_safe(mcp_client)

    # 合并本地 + MCP 工具
    all_tools = self.tools + self.mcp_tools

    # 创建 LangGraph Agent
    self.agent = create_agent(
        self.model,
        tools=all_tools,              # 注册工具
        checkpointer=self.checkpointer, # 绑定 MemorySaver
    )
    self._agent_initialized = True
```

### 6.3 非流式查询

```python
# rag_agent_service.py:181-244
async def query(self, question: str, session_id: str) -> str:
    await self._initialize_agent()

    # 构建消息
    messages = [
        SystemMessage(content=self.system_prompt),   # 系统提示
        HumanMessage(content=question)               # 用户问题
    ]
    agent_input = {"messages": messages}

    # 配置会话（thread_id → MemorySaver 用）
    config_dict = {"configurable": {"thread_id": session_id}}

    # 同步等待完整结果
    result = await self.agent.ainvoke(
        input=agent_input,
        config=config_dict,
    )

    # 提取最后一条 AI 消息
    messages_result = result.get("messages", [])
    last_message = messages_result[-1]
    return last_message.content
```

### 6.4 流式查询（更复杂但更真实）

```python
# rag_agent_service.py:246-316
async def query_stream(self, question, session_id):
    # ... 同样的初始化 ...

    # astream 逐 token 产出，stream_mode="messages"
    async for token, metadata in self.agent.astream(
        input=agent_input,
        config=config_dict,
        stream_mode="messages",     # ← 关键模式
    ):
        message_type = type(token).__name__

        # 只处理 AIMessage / AIMessageChunk
        if message_type in ("AIMessage", "AIMessageChunk"):
            content_blocks = getattr(token, 'content_blocks', None)

            if content_blocks and isinstance(content_blocks, list):
                for block in content_blocks:
                    if block.get('type') == 'text':
                        text_content = block.get('text', '')
                        if text_content:
                            yield {"type": "content", "data": text_content}

    yield {"type": "complete"}   # 结束信号
```

### 知识点：流式 vs 非流式的两条路径

```
非流式：ainvoke
  ┌──────┐     ┌──────────────┐     ┌──────────┐
  │输入   │────▶│ Agent 内部运行 │────▶│ 完整结果  │
  │消息   │     │ (可能多轮推理) │     │ (一次性)  │
  └──────┘     └──────────────┘     └──────────┘
  调用方等待 ←────── 整个过程 ──────→ 最后拿到

流式：astream(stream_mode="messages")
  ┌──────┐     ┌──────────────┐
  │输入   │────▶│ Agent 内部运行 │──→ token1
  │消息   │     │              │──→ token2
  └──────┘     │              │──→ token3
               │              │──→ ...
               └──────────────┘
  调用方立即收到 ←── yield ───→ 逐 token 到达
```

**`stream_mode="messages"` 的含义：** LangGraph 有多个 stream mode：
- `"values"`：每个节点完成后产出完整状态
- `"updates"`：每个节点完成后产出增量更新
- `"messages"`：**逐消息逐 token** 产出 LLM 生成的 token → 最适合打字机效果

### 6.5 消息裁剪中间件

```python
# rag_agent_service.py:37-74
def trim_messages_middleware(state: AgentState) -> dict | None:
    messages = state["messages"]

    if len(messages) <= 7:
        return None   # 消息少，不裁剪

    first_msg = messages[0]          # 保留 SystemMessage
    recent = messages[-6:]           # 保留最近 6 条（3 轮对话）

    new_messages = [first_msg] + list(recent)

    return {"messages": [
        RemoveMessage(id=REMOVE_ALL_MESSAGES),  # 先清空
        *new_messages                           # 再写入
    ]}
```

**为什么是 7 条阈值和 6 条保留？**

```
阈值 7 = 1 SystemMessage + 3 轮对话 (每轮 Human + AI 共 2 条)
保留 6 = 最近 3 轮对话（不含 SystemMessage，因为 first_msg 单独保留）

超过 3 轮后：用户消息 4+ → 裁剪 → 只给 LLM 最近 3 轮上下文
目的：防止对话历史撑爆 LLM 上下文窗口
```

### 6.6 会话管理

```
MemorySaver 内部结构（简化版）：
{
  "thread_abc": Checkpoint(
    channel_values={
      "messages": [SystemMessage, HumanMessage("你好"), AIMessage("你好！..."), ...]
    }
  ),
  "thread_xyz": Checkpoint(
    channel_values={
      "messages": [...]
    }
  )
}

外部 API：
  - get_session_history(session_id) → 读取 checkpointer 中的消息列表
  - clear_session(session_id) → checkpointer.delete_thread(session_id)
```

**`thread_id` 就是前端传的 `session_id`：**
```python
# rag_agent_service.py:211-215
config_dict = {
    "configurable": {
        "thread_id": session_id   # ← 前端 ChatRequest.id
    }
}
```

### 知识点：LangGraph Agent vs LangChain Chain

| | LangChain Chain | LangGraph Agent |
|---|---|---|
| 流程 | 固定步骤（先检索再生成） | LLM 自主决策 |
| 工具调用 | 不支持或硬编码 | LLM 自行判断是否调用 |
| 多轮对话 | 需自行管理 | 内置 checkpointer + thread_id |
| 适用场景 | 简单 RAG、单步任务 | 复杂推理、需要多工具协作 |

**`create_agent()` 做了什么（简化理解）：**
```python
# LangGraph 内部大致等价于：
# 1. 把 tools 转为 OpenAI Function Calling 的 tool definitions
# 2. 构建一个循环图：
#    LLM 节点 → 判断：生成文本？→ 输出
#                  调用工具？→ 工具节点 → LLM 节点（循环）
# 3. 绑定 checkpointer，让每轮的 state 持久化
```

### 知识点：System Prompt 设计

```python
# rag_agent_service.py:151-179
def _build_system_prompt(self) -> str:
    return """
        你是一个专业的AI助手，能够使用多种工具来帮助用户解决问题。

        工作原则:
        1. 理解用户需求，选择合适的工具来完成任务
        2. 当需要获取实时信息或专业知识时，主动使用相关工具
        3. 基于工具返回的结果提供准确、专业的回答
        4. 如果工具无法提供足够信息，请诚实地告知用户
        ...
    """
```

注意：system prompt **不需要列举具体工具名**，因为 LangChain 会自动把 `@tool` 函数的 name + docstring 注入 LLM 的工具定义中。Prompt 只需描述**使用工具的原则**。

---

## 7. Step 7：API 层

### 文件：[app/api/chat.py](../app/api/chat.py) + [app/main.py](../app/main.py)

### 路由注册关系

```
FastAPI 应用 (main.py)
  │
  ├─ /api/chat          POST  → chat()             非流式对话
  ├─ /api/chat_stream   POST  → chat_stream()       流式对话 (SSE)
  ├─ /api/chat/clear    POST  → clear_session()     清空会话
  ├─ /api/chat/session/{id} GET → get_session_info() 查询历史
  ├─ /api/upload        POST  → upload_file()       文件上传
  ├─ /api/index_directory POST → index_directory()  批量索引
  ├─ /api/health        GET   → health_check()      健康检查
  └─ /api/embeddings/... POST → ...                 Embedding API
```

### SSE 事件类型定义

流式对话返回的是 SSE（Server-Sent Events），事件类型定义在 [chat.py:87-173](../app/api/chat.py#L87)：

```python
# 内容块（打字机效果的核心）
{"type": "content", "data": "CPU 使用率过高"}

# 工具调用（前端可以展示"正在检索知识库..."）
{"type": "tool_call", "data": {"tool": "retrieve_knowledge", ...}}

# 检索结果（前端可以展示"引用来源"）
{"type": "search_results", "data": [...]}

# 完成信号
{"type": "done"}

# 错误
{"type": "error", "data": "错误信息"}
```

### SSE 流的数据转换

```
LangGraph astream 产出                    chat.py event_generator 转换
─────────────────────                    ────────────────────────────
token="CPU"      metadata={node:"llm"}  → {"type":"content", "data":"CPU"}
token="使用"     metadata={node:"llm"}  → {"type":"content", "data":"使用"}
...
(token, metadata)                       → {"type":"debug", "node":"llm", ...}
(AIMessage, ...)                        → {"type":"tool_call", "data":{...}}
  (token 包含 tool_calls)
最后                                     → {"type":"complete"}
```

### 知识点：SSE vs WebSocket

| | SSE | WebSocket |
|---|---|---|
| 方向 | 单向（服务端→客户端） | 双向 |
| 协议 | HTTP | 升级到 ws:// |
| 重连 | 浏览器自动 | 需手动实现 |
| 适合 | 服务端推送（对话、通知） | 实时双向（聊天室、游戏） |

RAG 对话只需要"用户发一个问题 → 服务端流式回答案"，单向推送即可，SSE 比 WebSocket 更轻量。

### 知识点：FastAPI Lifespan

```python
# main.py:20-46
@asynccontextmanager
async def lifespan(app: FastAPI):
    # === 启动阶段 ===
    milvus_manager.connect()        # 连接 Milvus
    yield                           # ← 应用运行期间
    # === 关闭阶段 ===
    milvus_manager.close()          # 释放连接
```

这是 FastAPI 推荐的生命周期管理模式，替代了旧版的 `@app.on_event("startup")` / `@app.on_event("shutdown")`。`yield` 之前是启动逻辑，之后是关闭逻辑。

---

## 8. 附录：知识点索引

按概念首字母排列。

| 概念 | 所在 Step | 一句话说明 |
|------|----------|-----------|
| **Agentic RAG** | Step 0 | LLM 自主决定何时检索，而非固定链路 |
| **as_retriever()** | Step 5 | VectorStore 包装为标准化 Retriever 接口 |
| **chunk_overlap** | Step 2 | 相邻分片重叠字符数，防止关键信息被割裂 |
| **content_and_artifact** | Step 5 | @tool 的双返回值模式，text 给 LLM 看，artifact 给程序用 |
| **create_agent()** | Step 6 | LangGraph 提供的 Agent 工厂函数，内部是工具调用循环 |
| **延迟初始化** | Step 3, 6 | `_ensure_client` / `_initialize_agent`，避免 import 时崩溃 |
| **Embeddings 接口** | Step 3 | LangChain 标准：`embed_documents` + `embed_query` |
| **EventSourceResponse** | Step 7 | FastAPI 的 SSE 响应封装 |
| **format_docs()** | Step 5 | 把 Document 列表格式化为 LLM 可读的带引用标记文本 |
| **IVF_FLAT** | Step 4 | 聚类 + 精确搜索的向量索引，nlist 控制簇数，nprobe 控制搜索范围 |
| **L2 距离** | Step 3, 4 | 欧氏距离，值越小越相似。归一化向量下等价于 Cosine |
| **LangGraph** | Step 6 | 有状态的多步骤 Agent 框架，支持 checkpointer |
| **MemorySaver** | Step 6 | 内存级的 LangGraph checkpointer，按 thread_id 存储对话 |
| **Milvus** | Step 4 | 开源向量数据库，支持标量过滤 + 向量搜索 |
| **OpenAI 兼容 API** | Step 3 | 用 `openai` 库连接 DashScope/火山方舟等，统一接口 |
| **Pydantic Settings** | Step 1 | 从 .env 加载类型安全的配置 |
| **RecursiveCharacterTextSplitter** | Step 2 | 按分隔符优先级的递归文本分割器 |
| **SSE** | Step 7 | Server-Sent Events，HTTP 单向流式推送 |
| **stream_mode="messages"** | Step 6 | LangGraph 的逐 token 流式模式 |
| **thread_id** | Step 6 | LangGraph 的会话标识，= 前端的 session_id |
| **trim_messages** | Step 6 | 消息裁剪策略：保留首条 + 最近 N 条 |
| **VectorStoreManager** | Step 4 | langchain_milvus 的上层封装 |

---

## 9. 学习路线图

推荐按以下顺序阅读源码，每步预计 15-30 分钟：

```
Week 1: 数据怎么存进去
  □ config.py (10 min)
  □ file.py → vector_index_service.py → document_splitter_service.py (30 min)
  □ vector_embedding_service.py (20 min)
  □ milvus_client.py → vector_store_manager.py (30 min)

Week 2: 答案怎么拿出来
  □ knowledge_tool.py (15 min)
  □ rag_agent_service.py — 上半部分，初始化和 query() (30 min)
  □ rag_agent_service.py — 下半部分，query_stream() 和会话管理 (30 min)
  □ chat.py → main.py (20 min)

验证：上传一个 md 文件，日志跟踪整个流程
```

总核心代码量约 500 行（不含 MCP/AIOps 模块），集中时间一个下午可通读完毕。
