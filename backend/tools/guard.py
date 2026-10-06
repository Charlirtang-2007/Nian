"""
工具编排层

职责：把"判断"和"执行"串起来。

流程：
    command 进来
      ↓
    classify(command) → auto / confirm / deny
      ↓
    auto    → 直接 exec_terminal
    deny    → 返回拒绝，不执行
    confirm → 调 confirm_fn 问用户，同意才 exec_terminal

设计原则：
  1. 本模块不判断权限（permission.py 管）
  2. 本模块不执行命令（terminal.py 管）
  3. 本模块只做编排：根据判断结果，决定走哪条路
  4. "怎么问用户"通过 confirm_fn 参数传入，本模块不关心细节

返回值统一为 dict：
    {
        "stdout": str,
        "stderr": str,
        "exit_code": int,
        "timeout": bool,
        "denied": bool,     # 规则拒绝（命中灾难规则）
        "rejected": bool,   # 用户拒绝（confirm 时用户点了不同意）
    }
"""
from typing import Awaitable, Callable

from tools.permission import classify
from tools.terminal import exec_terminal


# confirm_fn 的类型签名：
# 输入 (command, reason)，返回 True（同意）/ False（拒绝）
# 用 Awaitable 表示它是个 async 函数
ConfirmFn = Callable[[str, str], Awaitable[bool]]


def _result(
    stdout: str = "",
    stderr: str = "",
    exit_code: int = -1,
    timeout: bool = False,
    denied: bool = False,
    rejected: bool = False,
) -> dict:
    """
    构造统一格式的返回值。
    正常执行时直接复用 exec_terminal 的返回，只补 denied/rejected 两个 False。
    """
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "timeout": timeout,
        "denied": denied,
        "rejected": rejected,
    }


async def guarded_exec(
    command: str,
    confirm_fn: ConfirmFn,
    timeout: int = 10,
) -> dict:
    """
    带权限控制的命令执行入口。

    参数：
        command    : 要执行的命令字符串
        confirm_fn : 询问用户的回调，签名 async (command, reason) -> bool
        timeout    : 命令超时秒数，默认 10

    返回：
        统一格式 dict（见模块顶部注释）
    """
    # 第一步：判断权限类型
    level, reason = classify(command)

    # ---- deny：灾难命令，直接拒绝，不问用户 ----
    if level == "deny":
        return _result(
            stderr=f"命令被拒绝：{reason}",
            denied=True,
        )

    # ---- auto：只读白名单 + 工作区内，直接执行 ----
    if level == "auto":
        r = await exec_terminal(command, timeout)
        return _result(
            stdout=r["stdout"],
            stderr=r["stderr"],
            exit_code=r["exit_code"],
            timeout=r["timeout"],
        )

    # ---- confirm：问用户 ----
    ok = await confirm_fn(command, reason)

    if not ok:
        return _result(
            stderr=f"用户拒绝执行({reason})",
            rejected=True,
        )

    # 用户同意，执行
    r = await exec_terminal(command, timeout)
    return _result(
        stdout=r["stdout"],
        stderr=r["stderr"],
        exit_code=r["exit_code"],
        timeout=r["timeout"],
    )
