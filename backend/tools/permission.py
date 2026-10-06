"""
终端权限层

判断一条命令应该：
  - auto    : 直接执行（只读白名单 + 路径都在工作区内）
  - confirm : 问用户（写操作、工作区外只读、其他不确定情况）
  - deny    : 直接拒绝（灾难命令，不给确认机会）

设计原则：
  1. 不信任模型，不信任外部数据（爬虫内容、用户输入等）
  2. 只读白名单是白名单，不是黑名单 —— 不在名单里的默认要问
  3. 工作区边界是硬约束 —— 只读命令跑出工作区也要问
  4. 无法判断时，倾向 confirm（安全默认）
  5. 灾难命令连问都不问，直接拒 —— 用户也可能手滑点同意
"""
import os
import re
import shlex


# ============================================================
# 配置
# ============================================================

# 工作区根目录：AI 的主要活动范围
# 只读命令的目标路径如果跑出这个目录，会从 auto 升到 confirm
WORKSPACE_ROOT = os.path.realpath(os.path.expanduser("~/Games/Nian"))


# ============================================================
# 规则一：灾难命令（deny）
# ============================================================

# 命中任意一条，直接拒绝，不给用户确认的机会。
# 理由：用户也可能手滑点同意，灾难命令连问都不该问。
DANGEROUS_PATTERNS = [
    # 删除根目录 / 家目录 / 通配所有
    r"\brm\b[^\n]*\s+/(\s|$|\*)",           # rm ... /  或  rm ... /*
    r"\brm\b[^\n]*\s+~(\s|$|/\*)",          # rm ... ~  或  rm ... ~/*
    # 格式化磁盘
    r"\bmkfs(\.\w+)?\b",                     # mkfs / mkfs.ext4 / ...
    # dd 写盘
    r"\bdd\b[^\n]*\b(if|of)=",               # dd if=... / dd of=...
    # fork bomb
    r":\(\)\s*\{.*\}.*:",
    # 关机 / 重启
    r"\b(shutdown|reboot|halt|poweroff)\b",
    # 直接写裸盘设备
    r">\s*/dev/(sd|nvme|hd|vd|mmcblk)",
]


# ============================================================
# 规则二：只读命令白名单（auto 候选）
# ============================================================

# 只把"明确只读"的命令放进来。
# 注意以下命令故意不放：
#   - find   : 有 -exec、-delete 参数，能执行 / 删除
#   - git    : 有 commit、push 等写操作
#   - python : 能执行任意代码
#   - touch/mkdir/rm/mv/cp : 都是写操作，走 confirm
# echo 放进来是因为它本身只打印，如果带 > 重定向会被 shell 操作符检查拦住。
READONLY_COMMANDS = {
    # 查看文件
    "ls", "cat", "head", "tail", "wc", "stat", "file", "tree",
    # 搜索
    "grep", "which", "whereis",
    # 路径
    "pwd", "realpath", "readlink", "basename", "dirname",
    # 系统信息
    "uname", "whoami", "id", "hostname", "date", "uptime", "free",
    "lscpu", "lsblk", "lspci",
    # 进程 / 磁盘
    "ps", "df", "du",
    # 环境 / 打印
    "env", "printenv", "echo",
}


# ============================================================
# 规则三：shell 操作符
# ============================================================

# 出现以下任意一个，命令就不再是"纯只读"，直接升到 confirm。
# 理由：
#   >  >>  : 重定向写入，会改文件
#   <      : 输入重定向，可能读到工作区外
#   |      : 管道，后半段命令可能不是只读
#   && || ;: 串联，任一段可能不是只读
#   `  $(  : 命令替换，括号里可以藏任意东西
#   &      : 后台执行，脱离控制
SHELL_OPERATORS = [">", ">>", "<", "|", "&&", "||", ";", "`", "$(", "&"]


# ============================================================
# 函数
# ============================================================

def _has_dangerous(command: str) -> bool:
    """检查命令是否命中灾难特征（正则匹配）"""
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def _find_shell_operator(command: str) -> str | None:
    """
    返回命令里命中的第一个 shell 操作符，没有就返回 None。
    返回操作符本身（而不是 True/False），是为了在 reason 里告诉用户具体是哪个。
    """
    for op in SHELL_OPERATORS:
        if op in command:
            return op
    return None

def _parse_tokens(command: str) -> list[str] | None:
    """
    按 shell 语法拆 token。
    比如 'ls -la "my dir"' → ['ls', '-la', 'my dir']
    解析失败（引号不闭合等）返回 None。
    """
    try:
        return shlex.split(command)
    except ValueError:
        return None


def _extract_paths(tokens: list[str]) -> list[str]:
    """
    从 tokens 里粗略提取"看起来像路径"的参数。
    跳过第一个 token（命令名）和以 - 开头的选项。

    识别规则：
      - 以 / 开头（绝对路径）
      - 以 ~ 开头（家目录）
      - 以 ./ 或 ../ 开头（显式相对路径）
      - 包含 /（如 src/main.py）
    """
    paths = []
    for token in tokens[1:]:        # 跳过命令名
        if token.startswith("-"):   # 跳过选项
            continue
        if (
            token.startswith("/")
            or token.startswith("~")
            or token.startswith("./")
            or token.startswith("../")
            or "/" in token
        ):
            paths.append(token)
    return paths


def _resolve(path: str) -> str | None:
    """
    把路径解析成绝对路径（不做存在性检查）。
    - ~ 展开成家目录
    - 相对路径按工作区根目录拼
    - 失败返回 None
    """
    try:
        expanded = os.path.expanduser(path)
        if not os.path.isabs(expanded):
            expanded = os.path.join(WORKSPACE_ROOT, expanded)
        return os.path.realpath(expanded)
    except Exception:
        return None


def _is_inside_workspace(path: str) -> bool:
    """判断某个路径是否在工作区根目录之内"""
    resolved = _resolve(path)
    if resolved is None:
        # 解析失败，保守处理：当成工作区外
        return False
    try:
        # commonpath 避免 /home/user/Nian2 被误判为在 /home/user/Nian 内
        common = os.path.commonpath([resolved, WORKSPACE_ROOT])
        return common == WORKSPACE_ROOT
    except ValueError:
        # 路径不兼容（Linux 上少见）
        return False


# ============================================================
# 核心函数
# ============================================================

def classify(command: str) -> tuple[str, str]:
    """
    判断一条命令属于哪一类，返回 (level, reason)。

    level: "auto" / "confirm" / "deny"
    reason: 人话解释为什么是这个 level，给用户看的

    判断顺序（按最危险优先）：
      1. 命中灾难规则         → deny
      2. 包含 shell 操作符    → confirm
      3. 命令名不在只读白名单 → confirm
      4. 只读命令但路径出工作区 → confirm
      5. 以上都不是           → auto
    """
    # 第一步：灾难命令
    if _has_dangerous(command):
        return ("deny", "命中灾难规则，禁止执行")

    # 第二步：shell 操作符
    op = _find_shell_operator(command)
    if op:
        return ("confirm", f"含 shell 操作符 `{op}`，可能改变行为")

    # 第三步：拆 token，看命令名
    tokens = _parse_tokens(command)
    if not tokens:
        return ("confirm", "命令解析失败（引号不闭合等），保守处理")

    cmd_name = tokens[0]
    if cmd_name not in READONLY_COMMANDS:
        return ("confirm", f"命令 `{cmd_name}` 不在只读白名单")

    # 第四步：路径检查
    paths = _extract_paths(tokens)
    for path in paths:
        if not _is_inside_workspace(path):
            return ("confirm", f"路径 `{path}` 在工作区外")

    # 全部通过
    return ("auto", "只读白名单命令，路径都在工作区内")