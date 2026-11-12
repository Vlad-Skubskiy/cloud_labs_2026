from fastapi import FastAPI, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

class ItemOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    description: str | None = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.get("/items", response_model=list[ItemOut])
def get_items(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), db: Session = Depends(get_db),):
    return (
        db.query(models.Item)
        .order_by(models.Item.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )


@app.get("/items/{item_id}", response_model=ItemOut)
def get_item_by_id(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/items", response_model=ItemOut)
def post_item(name: str, description: str | None = None, db: Session = Depends(get_db)):
    db_item = models.Item(name=name, description=description)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item