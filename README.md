# Nian

一个助手型桌宠。不是工具，是能陪着、能控制电脑、能主动获取信息的 AI 助手。

## 为什么做

为了好玩，也为了驱动自己学新东西。
不想枯燥地学，所以用项目带着走。

## 原则

- 先确定信息，再思考输出。
- 不确定就先问用户。
- 一切以用户为主，助手只是工具。

## 功能

### 已完成

- [x] 文字聊天（WebSocket 流式，打字机效果）
- [x] 大模型接入（DeepSeek）
- [x] 工具调用（function calling，模型能提议执行终端命令）
- [x] 终端命令执行（超时杀进程组，返回 stdout/stderr/exit_code）
- [x] 权限三层（只读自动 / 写操作问 / 灾难命令拒绝）
- [x] 前端确认弹窗（显示拦截原因）
- [x] 对话记忆（SQLite 持久化，刷新不丢）
- [x] 断线轮询重连（后端起来自动连上）

### 进行中 / 未开始

- [ ] 爬虫（网易云歌词，评论后面再说）
- [ ] 表情（Live2D）
- [ ] 微信 Bot
- [ ] 控制电脑（键鼠、文件等更多工具）
- [ ] 信息真实度判断

## 进度

**当前阶段：地基完成，准备盖楼。**

- 后端骨架、工具调用、权限、记忆 —— 四个地基模块已完成
- 爬虫、表情、微信、SDK —— 待开始

## 技术栈

| 层 | 技术 |
|:---|:---|
| 前端 | Vite + Vue |
| 后端 | FastAPI |
| 数据库 | SQLite（SQLAlchemy async，以后可换 PostgreSQL/MySQL） |
| 大模型 | DeepSeek（function calling） |
| 通信 | WebSocket（主通道）+ HTTP（旁路） |
| 运行环境 | Arch Linux |

## 目录

```
backend/    FastAPI 后端
  tools/    终端工具链（terminal / permission / guard）
  db.py     数据库连接
  models.py ORM 模型
  llm.py    大模型调用与工具循环
  ws_dispatcher.py  WebSocket 分发器
frontend/   Vite + Vue 前端
docs/       笔记与架构文档
```

## 架构一句话

`/ws/chat` 用 Dispatcher 单点收消息 → 聊天消息进 `chat_with_tools` 流式循环 → 模型要工具就走 `guarded_exec` 三层审查 → 需要确认时通过 WS 弹窗问用户 → 执行结果回喂模型再生成 → 每句话落 SQLite。
