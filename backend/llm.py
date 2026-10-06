"""
大模型调用层

职责：
  1. 定义可用的工具清单（TOOLS），告诉模型它能调用什么
  2. 提供 ask / ask_stream：不带工具的简单问答（给普通聊天用）
  3. 提供 chat_with_tools：带工具的完整循环（模型可提议执行命令）

设计原则：
  - 本层只管"调模型"，不管权限判断、不管命令执行
  - 工具的实际执行通过 handle_tool_call 转给 guard 处理
"""
import json

from openai import AsyncOpenAI

from config import settings
from tools.guard import guarded_exec


# ============================================================
# 工具定义：告诉模型它能调用什么
# ============================================================

TOOLS = [{
    "type": "function",
    "function": {
        "name": "exec_terminal",
        "description": (
            "在用户的 Arch Linux 上执行一条终端命令，并返回命令的输出。"
            "只读命令会自动执行；写操作会先询问用户是否同意；"
            "灾难命令会被系统直接拒绝。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的命令，比如 ls -la、cat ~/file.txt",
                },
                "timeout": {
                    "type": "integer",
                    "description": "超时秒数，默认 10",
                },
            },
            "required": ["command"],
        },
    },
}]


# ============================================================
# 简单问答（不带工具）
# ============================================================

async def ask(client: AsyncOpenAI, message: str) -> str:
    """一次性问，返回完整回复。给 HTTP /chat 用。"""
    resp = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": message}],
    )
    return resp.choices[0].message.content


async def ask_stream(client: AsyncOpenAI, message: str):
    """流式问，逐块 yield 文本。给普通聊天用（不涉及工具）。"""
    stream = await client.chat.completions.create(
        model=settings.deepseek_model,
        messages=[{"role": "user", "content": message}],
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ============================================================
# 工具调用的格式化：把执行结果转成模型能读的字符串
# ============================================================

def format_tool_result(result: dict) -> str:
    """
    把 guarded_exec 的返回值，转成一段字符串，交给模型。

    模型看不懂 dict，它要的是文字。所以我们把四种情况分别写成一句话：
      - 被规则拒绝（denied）
      - 被用户拒绝（rejected）
      - 超时
      - 正常执行（带 stdout/stderr/exit_code）
    """
    if result.get("denied"):
        return "（系统拒绝）这条命令命中了灾难规则，未执行。"

    if result.get("rejected"):
        return "（用户拒绝）用户不同意执行这条命令。"

    if result.get("timeout"):
        return f"（超时）命令在超时前未完成。\nstdout:\n{result['stdout']}\nstderr:\n{result['stderr']}"

    # 正常执行
    parts = []
    parts.append(f"exit_code: {result['exit_code']}")
    if result["stdout"]:
        parts.append(f"stdout:\n{result['stdout']}")
    if result["stderr"]:
        parts.append(f"stderr:\n{result['stderr']}")
    return "\n".join(parts)


async def handle_tool_call(name: str, arguments: str, confirm_fn) -> str:
    """
    处理一个 tool_call。

    参数：
        name      : 工具名，比如 "exec_terminal"
        arguments : 参数字符串，比如 '{"command": "ls -la"}'
        confirm_fn: 询问用户的回调
    """
    args = json.loads(arguments)

    if name == "exec_terminal":
        command = args["command"]
        timeout = args.get("timeout", 10)
        print(f"[tool] exec_terminal command = {command!r}")   # 调试 log，可删
        result = await guarded_exec(command, confirm_fn, timeout=timeout)
        return format_tool_result(result)

    return f"（未知工具）{name}"

# ============================================================
# 带工具的完整对话循环
# ============================================================

async def chat_with_tools(
    client: AsyncOpenAI,
    user_message: str,
    confirm_fn,
    max_rounds: int = 5,
):
    """
    带工具的对话（流式版）。

    这是一个 async generator，每次 yield 一小段文本给调用方。
    调用方用 `async for chunk in chat_with_tools(...)` 拿。

    流程：
        1. 把用户消息加入历史
        2. 流式调模型，边收边 yield 文本，同时收集 tool_calls
        3. 如果模型没调工具 → 结束
        4. 如果模型调了工具 → 执行工具，结果加进历史，回到第 2 步
        5. 最多循环 max_rounds 轮
    """
    messages = [{"role": "user", "content": user_message}]

    for _ in range(max_rounds):
        stream = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            tools=TOOLS,
            stream=True,
        )

        collected_content = ""
        # tool_calls 按 index 收集：{index: {id, name, arguments}}
        tool_calls_buffer: dict[int, dict] = {}

        async for chunk in stream:
            delta = chunk.choices[0].delta

            # 文本块：直接 yield 给调用方
            if delta.content:
                collected_content += delta.content
                yield delta.content

            # tool_calls 块：按 index 拼接
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls_buffer:
                        tool_calls_buffer[idx] = {
                            "id": "",
                            "name": "",
                            "arguments": "",
                        }
                    buf = tool_calls_buffer[idx]
                    if tc.id:
                        buf["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            buf["name"] = tc.function.name
                        if tc.function.arguments:
                            buf["arguments"] += tc.function.arguments

        # 这一轮流完了

        # 没有工具调用 → 模型已经给出了最终回答，结束
        if not tool_calls_buffer:
            return

        # 有工具调用：把这一轮的 assistant 消息加进历史
        messages.append({
            "role": "assistant",
            "content": collected_content or None,
            "tool_calls": [
                {
                    "id": buf["id"],
                    "type": "function",
                    "function": {
                        "name": buf["name"],
                        "arguments": buf["arguments"],
                    },
                }
                for buf in tool_calls_buffer.values()
            ],
        })

        # 逐个执行工具，结果加进历史
        for buf in tool_calls_buffer.values():
            result_str = await handle_tool_call(
                buf["name"], buf["arguments"], confirm_fn
            )
            messages.append({
                "role": "tool",
                "tool_call_id": buf["id"],
                "content": result_str,
            })

        # 循环回去，带着工具结果再调一次模型

    yield "（已达到最大工具调用轮数）"