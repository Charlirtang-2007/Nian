"""
数据库连接层

职责：
  1. 创建异步 engine（连接池）
  2. 提供 session 工厂
  3. 定义 Base（所有 ORM 模型的基类）
  4. 提供 FastAPI 依赖 get_session

这个文件只管“怎么连数据库”，不管“存什么数据”（那是 models.py）
也不管“怎么用数据”（那是各个业务代码）
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# ============================================================
# 数据库地址
# ============================================================

# SQLite 文件放在 backend 目录下
# 格式：sqlite+aiosqlite:///<路径>
#   - sqlite       : 数据库类型
#   - aiosqlite    : 用哪个驱动（异步版）
#   - ///          : 三斜杠表示相对路径
DATABASE_URL = "sqlite+aiosqlite:///nian.db"


# ============================================================
# Engine：进程级单例，管理连接池
# ============================================================

engine = create_async_engine(
    DATABASE_URL,
    echo=False,   # 改成 True 会打印所有 SQL，调试用
)


# ============================================================
# Session 工厂：每次要操作数据库，从这里生成一个 session
# ============================================================

# expire_on_commit=False 的含义：
#   默认情况下，commit 后 session 里的对象会"过期"，下次访问属性要重新查库
#   设成 False，commit 后对象还能直接读，省一次查询
SessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ============================================================
# Base：所有 ORM 模型的基类
# ============================================================

class Base(DeclarativeBase):
    """
    所有表模型的基类。
    models.py 里的 Message 会继承它，SQLAlchemy 通过它收集所有表的信息。
    """
    pass


# ============================================================
# FastAPI 依赖：给路由用
# ============================================================

async def get_session():
    """
    生成一个 session，用完自动关闭。
    用法：
        @app.post("/xxx")
        async def xxx(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with SessionLocal() as session:
        yield session
