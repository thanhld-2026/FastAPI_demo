from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag
from app.schemas.tag import TagCreate


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())


def get(db: Session, tag_id: int) -> Tag | None:
    return db.get(Tag, tag_id)


def get_by_name(db: Session, name: str) -> Tag | None:
    return db.scalar(select(Tag).where(Tag.name == name))


def get_many(db: Session, tag_ids: list[int]) -> list[Tag]:
    if not tag_ids:
        return []
    return list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))).all())


def create(db: Session, data: TagCreate) -> Tag:
    tag = Tag(name=data.name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete(db: Session, tag: Tag) -> None:
    db.delete(tag)
    db.commit()
