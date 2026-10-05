# 标准库：异步 I/O，用来创建子进程、处理超时
import asyncio
# 标准库：操作系统接口，用来杀进程组
import os
# 标准库：信号常量，SIGKILL 表示“强制杀死”
import signal


async def exec_terminal(command: str, timeout: int = 10) -> dict:
    """
    执行一条终端命令，返回结构化结果。

    输入：
        command: 命令字符串，比如 "ls -la"
        timeout: 超时秒数，默认 10

    输出：
        {
            "stdout": str,      # 标准输出
            "stderr": str,      # 标准错误
            "exit_code": int,   # 退出码，0 表示成功，-1 表示后端自身出错
            "timeout": bool,    # 是否因超时被杀
        }
    """
    try:
        # ========== 第一步：启动子进程 ==========
        # create_subprocess_shell：
        #   把整条命令交给 /bin/sh -c "命令" 执行
        #   所以支持管道、重定向、通配符等 shell 语法
        # stdout=PIPE, stderr=PIPE：
        #   把子进程的输出写进管道，而不是打到终端
        #   这样后面可以用 communicate() 读到输出内容
        # start_new_session=True：
        #   让子进程成为新进程组的组长
        #   超时时可以 kill 整个进程组，连孙子进程一起杀，不留僵尸
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,   # 捕获标准输出
            stderr=asyncio.subprocess.PIPE,   # 捕获标准错误
            start_new_session=True,
        )

        try:
            # ========== 第二步：等进程结束（带超时） ==========
            # proc.communicate()：
            #   等子进程结束，并把管道里的 stdout / stderr 全部读完
            #   用 communicate 而不是 wait，是为了避免管道缓冲区满导致死锁
            # asyncio.wait_for(..., timeout=timeout)：
            #   给 communicate 加一个超时闹钟
            #   超时未完成则抛出 asyncio.TimeoutError
            # await 期间事件循环去处理其他请求，不阻塞主程序
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            # 走到这里说明正常结束，没超时
            timed_out = False

        except asyncio.TimeoutError:
            # ========== 第三步：超时处理（杀进程组） ==========
            # 命令卡死了（比如 sleep 1000），必须强制清理
            # os.getpgid(proc.pid)：
            #   拿到子进程所属的进程组 ID
            #   因为设了 start_new_session=True，这个进程组 ID 就等于子进程的 pid
            # os.killpg(pgid, SIGKILL)：
            #   给整个进程组发 SIGKILL
            #   SIGKILL 无法被捕获、无法被忽略，操作系统直接干掉
            #   杀整组是为了连子进程启动的孙子进程一起带走，不留孤儿
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)

            # 再调一次 communicate：
            #   把子进程被杀前产生的残余输出捞回来
            #   同时回收僵尸进程（不回收的话，进程表里会残留一条记录）
            stdout_bytes, stderr_bytes = await proc.communicate()
            # 标记：这次是被超时杀掉的
            timed_out = True

        # ========== 第四步：结构化返回 ==========
        # decode("utf-8", errors="replace")：
        #   子进程输出是 bytes，转成字符串给前端
        #   命令输出不一定是合法 UTF-8（比如 cat 二进制文件）
        #   errors="replace" 表示遇到无法解码的字节用 � 替代，不抛异常
        # proc.returncode：
        #   退出码，0 表示成功，非 0 表示失败，-9 表示被 SIGKILL 杀死
        return {
            "stdout": stdout_bytes.decode("utf-8", errors="replace"),
            "stderr": stderr_bytes.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode,
            "timeout": timed_out,
        }

    except Exception as e:
        # ========== 兜底：连子进程都没起来 ==========
        # 比如 shell 本身有问题、系统资源耗尽、权限不足等
        # 返回 exit_code: -1 作为约定俗成的“后端内部错误”标记
        # 这个兜底保证函数永不向外抛异常，调用方可以放心用
        return {
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
            "timeout": False,
        }
