"""
ORM 模型定义

职责：定义数据库里有哪些表、每张表有哪些字段。

一个类 = 一张表
一个类属性 = 一个字段
一个实例 = 一行数据
"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db import Base


class Message(Base):
    """
    对话消息表。

    存每一轮对话的消息，包括：
      - 用户说的
      - 模型说的
      - 工具执行结果
      - 系统消息（暂时没用）

    通过 role 区分是谁说的话。
    """
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 角色：user / assistant / tool / system
    # 长度限制 20，够用且省空间
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    # 消息内容
    # Text 类型无长度上限，适合长文本
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 创建时间，默认当前 UTC 时间
    # default=datetime.utcnow 是"插入时如果没有值就填这个"
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self) -> str:
        """调试用：print(Message) 时显示的样子"""
        return f"<Message id={self.id} role={self.role!r}>"
