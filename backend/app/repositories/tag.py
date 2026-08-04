from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tag import Tag


def get_tag_by_name(db: Session, name: str) -> Tag | None:
    statement = select(Tag).where(Tag.name == name)
    return db.scalar(statement)


def create_tag(db: Session, name: str) -> Tag:
    tag = Tag(name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag