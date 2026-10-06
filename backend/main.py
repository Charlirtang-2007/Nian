import json
from functools import lru_cache
import asyncio
import uuid
from llm import ask, ask_stream, chat_with_tools
from ws_dispatcher import WSDispatcher, make_ws_confirm
from tools.guard import guarded_exec
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
    WebSocket 主入口。
    用 Dispatcher 统一管理消息收发。
    """
    await ws.accept()

    dispatcher = WSDispatcher(ws)
    confirm_fn = await make_ws_confirm(dispatcher)

    async def handle_chat(msg: dict):
        """处理一条聊天消息"""
        content = msg.get("content", "").strip()

        # 测试触发：输入 /test_tool 走完整工具确认流程
        if content == "/test_tool":
            await run_tool_test(dispatcher, confirm_fn)
            return

        # 走带工具的对话循环
        async for chunk in chat_with_tools(client, content, confirm_fn):
            await dispatcher.send({"type": "delta", "content": chunk})
        await dispatcher.send({"type": "done"})
    
    # 关键：把处理函数挂上，然后启动 dispatcher
    dispatcher.on_chat = handle_chat
    await dispatcher.run()

async def run_tool_test(dispatcher: WSDispatcher, confirm_fn):
    """
    假工具调用：走一遍 guarded_exec 流程，把结果推给前端。
    接入模型后，这段会被"从模型响应解析 tool_call"替代。
    """
    command = "touch /tmp/nian_ws_test"

    await dispatcher.send({
        "type": "delta",
        "content": f"（测试）模型想执行：{command}\n",
    })

    result = await guarded_exec(command, confirm_fn)

    await dispatcher.send({
        "type": "tool_result",
        "id": uuid.uuid4().hex,
        "command": command,
        **result,
    })


    await dispatcher.send({"type": "done"})

    await dispatcher.send({"type": "done"})
