import asyncio
from tools.terminal import exec_terminal

async def main():
    cases = [
        # 1. 普通只读
        "pwd",
        # 2. 带管道
        "ls ~/Games/Nian | grep -i nian",
        # 3. 命令不存在
        "notacommand",
        # 4. 权限错误（stderr 有输出，exit_code 非 0）
        "cat /etc/shadow",
        # 5. 退出码非 0 但不是超时
        "ls /nonexistent",
        # 6. 多条命令串联
        "echo hello && echo world",
        # 7. 写操作（建临时文件）
        "touch /tmp/nian_test && ls /tmp/nian_test",
        # 8. 环境变量
        "echo $HOME",
        # 9. 超时
        ("sleep 10", 2),
        # 10. 中文输出
        "echo 你好世界",
    ]

    for c in cases:
        if isinstance(c, tuple):
            cmd, timeout = c
        else:
            cmd, timeout = c, 10

        r = await exec_terminal(cmd, timeout)
        print(f"\n>>> {cmd}")
        print(f"    exit_code={r['exit_code']}  timeout={r['timeout']}")
        print(f"    stdout={r['stdout'][:200]!r}")
        print(f"    stderr={r['stderr'][:200]!r}")

asyncio.run(main())