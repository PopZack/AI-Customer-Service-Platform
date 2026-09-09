"""通用 Repository 基类: 封装常见 CRUD 操作。

各模块的具体 repository 继承 BaseRepository[Model] 即可获得基础 CRUD,
复杂查询在子类中扩展。
"""
from typing import Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """泛型 Repository 基类。"""

    def __init__(self, session: AsyncSession, model: Type[ModelT]):
        self.session = session
        self.model = model

    async def get_by_id(self, item_id: int) -> ModelT | None:
        """按主键查询。"""
        return await self.session.get(self.model, item_id)

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """分页查询全部。"""
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelT:
        """新建记录。"""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, instance: ModelT, **kwargs) -> ModelT:
        """更新记录字段。"""
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance: ModelT) -> None:
        """删除记录。"""
        await self.session.delete(instance)
        await self.session.flush()
