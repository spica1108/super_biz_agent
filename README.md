# SuperBizAgent

企业级智能对话和运维助手，支持 RAG 知识库问答和 AIOps 智能诊断

## 项目简介

本项目聚焦 RAG 知识库问答和 AIOps 自动故障诊断两大场景。支持文档上传后自动向量化与检索增强生成，让 AI 基于内部知识库精准回答业务问题；内置自动诊断引擎，可从告警信息出发自主制定诊断计划、调用日志和监控工具完成根因分析，将运维响应从小时级压缩到分钟级。

## 技术栈

- **框架**: FastAPI + LangChain + LangGraph
- **LLM**: 阿里云 DashScope (通义千问)
- **向量库**: Milvus
- **工具协议**: MCP (Model Context Protocol)

## 前端开发

前端使用 Vue 3、TypeScript 和 Vite。开发服务器会将 `/api` 请求代理到本地 FastAPI（`127.0.0.1:9900`）。

```powershell
cd frontend
npm install
npm run dev
```

生产构建会输出到项目根目录的 `static/`，由 FastAPI 在 `/` 和 `/static/` 提供：

```powershell
npm run build
```
