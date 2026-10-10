# MCP 学习资源对照指南

## 一、两种资源的定位

| 维度 | `docs/mcp-golden-sky.md` | `.zread/wiki/versions/2026-07-05-165849/` |
|------|--------------------------|---------------------------------------------|
| **性质** | 教程/课程大纲 | 项目百科/参考文档 |
| **组织方式** | 按学习路径递进，5 阶段 | 按模块独立成篇，每篇一个主题 |
| **优势** | 有代码行号、图解、知识点注释、练习 | 架构讲解更完整、背景信息更丰富 |
| **劣势** | 精简，不重复 wiki 已有的细节 | 纯阅读，无交互式练习 |
| **适合场景** | 建立知识框架 + 动手验证 | 深入理解设计决策 + 完整上下文 |

---

## 二、MCP 相关的 Wiki 文件清单

共 **5 个直接相关** + **6 个间接相关**：

### 直接相关（MCP 主题）

| # | 文件名 | 对应 gold-sky 阶段 |
|---|--------|-------------------|
| **21** | `MCP 客户端架构：全局单例、重试拦截器与多服务器管理.md` | 阶段二：Client 管理 |
| **22** | `CLS 日志查询 MCP Server：FastMCP 实现的日志检索与分析工具.md` | 阶段一：Server 构建 |
| **23** | `监控数据 MCP Server：CPU - 内存 - 进程 - 历史工单查询工具.md` | 阶段一：Server 构建 |
| **24** | `工具调用重试与容错：指数退避拦截器与优雅降级策略.md` | 阶段二：重试机制 |
| **32** | `新增 MCP Server：FastMCP 工具注册与主应用集成指南.md` | 阶段五：进阶 |

### 间接相关（MCP 的消费方和上下文）

| # | 文件名 | 关联点 |
|---|--------|--------|
| **10** | `Plan-Execute-Replan 模式概述.md` | AIOps Agent 整体架构，MCP 工具在其中的位置 |
| **11** | `Planner 节点.md` | MCP 工具列表如何参与计划生成 |
| **12** | `Executor 节点.md` | ToolNode 如何执行 MCP 工具调用 |
| **13** | `Replanner 节点.md` | MCP 工具在决策环节的使用 |
| **14** | `AIOps 诊断流程：从告警获取到根因分析的完整链路.md` | MCP 在端到端诊断中的角色 |
| **20** | `本地工具集.md` | 本地工具 vs MCP 工具的边界划分 |

---

## 三、推荐学习策略

> **核心原则：`mcp-golden-sky.md` 做导航，wiki 做深度阅读。**

每阶段的操作顺序：

```
先读 gold-sky  →  建立框架认知（15min）
  ↓
再读 wiki     →  填充细节，理解设计决策（20-40min）
  ↓
回 gold-sky   →  做练习验证理解（15-30min）
```

### 阶段一：MCP Server 构建

| 顺序 | 读什么 | 重点 |
|------|--------|------|
| 1 | gold-sky 阶段一 | FastMCP 工具定义骨架、`@mcp.tool()` 装饰器原理 |
| 2 | wiki **#22** CLS Server | 5 个工具的完整实现、日志装饰器、Mock 数据模式 |
| 3 | wiki **#23** Monitor Server | CPU/内存指标动态生成、参数设计差异（int vs str） |
| 4 | gold-sky 阶段一练习 | 手写极简 MCP Server |

### 阶段二：MCP Client 管理

| 顺序 | 读什么 | 重点 |
|------|--------|------|
| 1 | gold-sky 阶段二 | 单例调用链、retry_interceptor 流程 |
| 2 | wiki **#21** MCP 客户端架构 | MultiServerMCPClient 初始化、多服务器管理全貌 |
| 3 | wiki **#24** 重试与容错 | 指数退避策略的详细分析、fail gracefully 设计哲学 |
| 4 | gold-sky 阶段二练习 | 画调用时序图 |

### 阶段三：MCP + AIOps Agent 集成

| 顺序 | 读什么 | 重点 |
|------|--------|------|
| 1 | gold-sky 阶段三 | Plan-Execute-Replan 数据流图、format_tools_description vs bind_tools |
| 2 | wiki **#11** Planner | 经验文档检索 + 工具列表如何传递给 LLM |
| 3 | wiki **#12** Executor | ToolNode 自动执行、工具调用三段式 |
| 4 | wiki **#13** Replanner | 三种决策逻辑 |
| 5 | wiki **#10** + **#14** | 整体架构 + 端到端链路串联 |
| 6 | gold-sky 阶段三练习 | 追踪完整诊断流程 |

### 阶段四：MCP + RAG Agent 集成

| 顺序 | 读什么 | 重点 |
|------|--------|------|
| 1 | gold-sky 阶段四 | 两种 Agent 模式的 5 维度对比 |
| 2 | wiki **#15** RAG Agent 架构 | ReAct 模式完整上下文、create_agent 用法 |
| 3 | gold-sky 阶段四练习 | 对比分析 + 降级路径追踪 |

### 阶段五：进阶主题

| 顺序 | 读什么 | 重点 |
|------|--------|------|
| 1 | wiki **#32** 新增 MCP Server | 完整的 3 步集成指南 |
| 2 | gold-sky 阶段五 | 全链路 Trace、Mock→真实 API 升级 |

---

## 四、建议阅读顺序汇总

```
gold-sky 阶段一
  → wiki #22 → wiki #23
  → 练习

gold-sky 阶段二
  → wiki #21 → wiki #24
  → 练习

gold-sky 阶段三
  → wiki #11 → wiki #12 → wiki #13
  → wiki #10 → wiki #14
  → 练习

gold-sky 阶段四
  → wiki #15
  → 练习

gold-sky 阶段五
  → wiki #32
```
