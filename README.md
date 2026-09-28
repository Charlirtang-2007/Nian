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

- [ ] 文字聊天
- [ ] 表情（Live2D）
- [ ] 终端命令（只读自动，其他问）
- [ ] 爬虫（网易云歌词，评论后面再说）
- [ ] 微信 Bot
- [ ] 控制电脑

## 进度

- 项目初始化：monorepo，backend / frontend / docs
- 当前：准备做 FastAPI + DeepSeek 文字聊天 + WebSocket

## 技术栈

- 后端：FastAPI
- 前端：Vite + Vue
- 数据库：SQLite 先跑通，后面换 MySQL；SQLAlchemy
- 大模型：DeepSeek
- 通信：WebSocket
- 爬虫：先简单方案，后面再上 Scrapy
- 运行环境：Arch Linux

## 目录

backend/   FastAPI
frontend/  Vite + Vue
docs/      笔记
