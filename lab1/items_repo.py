from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

import models


def insert_item(db: Session, name: str, description: str | None, dedupe_id: str | None) -> tuple[int, bool]:
    if dedupe_id is None:
        item = models.Item(name=name, description=description)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item.id, True

    stmt = (
        pg_insert(models.Item)
        .values(name=name, description=description, job_id=dedupe_id)
        .on_conflict_do_nothing(index_elements=["job_id"])
        .returning(models.Item.id)
    )
    item_id = db.execute(stmt).scalar_one_or_none()
    if item_id is not None:
        db.commit()
        return item_id, True

    db.rollback()
    existing = db.execute(select(models.Item.id).where(models.Item.job_id == dedupe_id)).scalar_one()
    return existing, False
