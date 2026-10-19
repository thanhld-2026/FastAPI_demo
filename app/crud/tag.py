from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Tag


def list_tags(db: Session) -> list[Tag]:
    return list(db.scalars(select(Tag).order_by(Tag.name)).all())
