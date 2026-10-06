"""
WebSocket 分发器（Dispatcher）

作用：一条 WS 连接上会跑多种消息（聊天、工具确认、以后的爬虫进度等）。
如果每段代码都自己去 ws.receive_text()，会互相抢消息。

Dispatcher 是整条连接上唯一读消息的地方。
它读到一条，看 type，分发给对应的处理者。
"""
import asyncio
import json
import uuid

from fastapi import WebSocket, WebSocketDisconnect


class WSDispatcher:
    def __init__(self, ws: WebSocket):
        self.ws = ws
        # 等待中的确认请求：{req_id: Future}
        # Future 是"未来会被填入结果的盒子"，谁在等确认，就注册一个
        self.waiters: dict[str, asyncio.Future] = {}
        # 聊天处理回调，由外部设置。收到 type == "chat" 时调它
        self.on_chat = None

    async def send(self, payload: dict):
        """统一出口：所有发给前端的消息都走这里，自动转 JSON"""
        await self.ws.send_text(json.dumps(payload, ensure_ascii=False))

    async def run(self):
        """
        主循环：整条连接唯一读消息的地方。
        读到一条，分一条。
        """
        try:
            while True:
                raw = await self.ws.receive_text()
                msg = json.loads(raw)
                await self.dispatch(msg)
        except WebSocketDisconnect:
            # 前端断开，正常退出
            pass

    async def dispatch(self, msg: dict):
        """按 type 分发到对应处理者"""
        t = msg.get("type")

        if t == "chat":
            # 聊天：用 create_task 处理，不阻塞主循环
            # 原因：聊天处理里可能要等用户确认，如果 await 这里，
            # 主循环就回不到 receive_text()，收不到 tool_confirm，死锁
            if self.on_chat:
                asyncio.create_task(self.on_chat(msg))

        elif t == "tool_confirm":
            # 工具确认：找到对应 req_id 的 Future，把结果填进去
            req_id = msg.get("id")
            fut = self.waiters.get(req_id)
            if fut and not fut.done():
                fut.set_result(bool(msg.get("approved", False)))

    async def wait_for_confirm(self, req_id: str, timeout: int = 60) -> bool:
        """
        注册一个等待，返回用户对某个 req_id 的回复。
        超时视为拒绝。
        """
        fut = asyncio.get_event_loop().create_future()
        self.waiters[req_id] = fut
        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            return False
        finally:
            self.waiters.pop(req_id, None)


async def make_ws_confirm(dispatcher: WSDispatcher):
    """
    生成一个 confirm_fn，绑定到给定的 dispatcher。
    guard 需要问用户时调它：
      1. 发 tool_request 给前端
      2. 等前端回 tool_confirm
      3. 返回 True/False
    """
    async def confirm_fn(command: str, reason: str) -> bool:
        req_id = uuid.uuid4().hex
        await dispatcher.send({
            "type": "tool_request",
            "id": req_id,
            "command": command,
            "reason": reason,
        })
        return await dispatcher.wait_for_confirm(req_id)

    return confirm_fn
