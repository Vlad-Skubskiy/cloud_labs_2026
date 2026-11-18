from sqlalchemy import Column, Index, Integer, String, text

from database import Base


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)
    job_id = Column(String(36), nullable=True)

    __table_args__ = (Index("uq_items_job_id", "job_id", unique=True),)


def ensure_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(727001)"))
        Base.metadata.create_all(bind=conn)
        conn.execute(text("ALTER TABLE items ADD COLUMN IF NOT EXISTS job_id VARCHAR(36)"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_items_job_id ON items (job_id)"))
