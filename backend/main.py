import json
from functools import lru_cache

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import AsyncOpenAI
from config import settings  # 引用配置类

app = FastAPI()

# ---------- CORS 中间件 ----------
# 允许本地 Vite dev server 跨域访问后端
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 依赖：大模型客户端 ----------
@lru_cache
def get_client() -> AsyncOpenAI:
    """
    创建 DeepSeek 客户端（异步版）。
    - 用 AsyncOpenAI：因为 ws_chat 是 async 函数，内部要 await
    - lru_cache：整个进程只建一个实例，复用 HTTP 连接池
    """
    return AsyncOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
    )


# ---------- 请求 / 响应模型 ----------
class ChatIn(BaseModel):
    # 前端 HTTP 请求体，格式：{"message": "..."}
    message: str


class ChatOut(BaseModel):
    # 后端 HTTP 响应体，格式：{"reply": "..."}
    reply: str


# ---------- 调模型：两段小逻辑，HTTP 和 WS 各自调用 ----------
async def ask(client: AsyncOpenAI, message: str) -> str:
    """一次性问，等完整回复再返回。给 HTTP /chat 用。"""
    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": message}],
    )
    return resp.choices[0].message.content


async def ask_stream(client: AsyncOpenAI, message: str):
    """流式问，逐块 yield 文本。给 WebSocket 用。"""
    stream = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": message}],
        stream=True,
    )
    async for chunk in stream:
        # chunk.choices[0].delta.content 是一小段文字，可能为 None
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ---------- 路由 ----------
@app.get("/")
def read_root():
    return {"message": "Nian backend is running"}


@app.post("/chat", response_model=ChatOut)
async def chat(
    body: ChatIn,
    client: AsyncOpenAI = Depends(get_client),
):
    """
    HTTP 版：一问一答。
    调用方：curl、脚本、以后的微信 Bot、内部服务。
    """
    reply = await ask(client, body.message)
    return ChatOut(reply=reply)


@app.websocket("/ws/chat")
async def ws_chat(
    ws: WebSocket,
    client: AsyncOpenAI = Depends(get_client),
):
    """
    WebSocket 版：前端主通道。
    协议（JSON 字符串）：
      前端 → 后端：
        {"type": "chat", "content": "你好"}
      后端 → 前端：
        {"type": "delta", "content": "你"}   # 流式文字块，可能多条
        {"type": "done"}                     # 本轮结束
    """
    await ws.accept()  # 完成升级握手，返回 101

    try:
        while True:  # 保持连接，循环收消息
            raw = await ws.receive_text()   # 等前端发一条
            msg = json.loads(raw)

            # 目前只处理 chat 类型，其他类型（以后的 tool_confirm）先忽略
            if msg.get("type") != "chat":
                continue

            message = msg.get("content", "")

            # 逐块把模型输出推给前端
            async for delta in ask_stream(client, message):
                await ws.send_text(json.dumps(
                    {"type": "delta", "content": delta},
                    ensure_ascii=False,  # 中文原样输出，不转成 \uXXXX
                ))

            # 本轮结束标记
            await ws.send_text(json.dumps({"type": "done"}))

    except WebSocketDisconnect:
        # 前端断开连接，正常退出，不打印异常
        pass