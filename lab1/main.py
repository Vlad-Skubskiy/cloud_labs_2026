from fastapi import FastAPI, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal
import cache

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

class ItemOut(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str | None = None
    description: str | None = None

_items_adapter = TypeAdapter(list[ItemOut])


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
def get_items(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0), nocache: bool = False, db: Session = Depends(get_db),):
    use_cache = cache.enabled() and not nocache
    key = f"items:v{cache.version()}:list:{limit}:offset" if use_cache else None

    if use_cache:
        cached = cache.cache_get(key)
        if cached is not None:
            cache.record(hit=True)
            return Response(cached, media_type="application/json", headers={"X-Cache": "HIT"})
    rows = (
        db.query(models.Item)
        .order_by(models.Item.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    payload = _items_adapter.dump_json(_items_adapter.validate_python(rows))

    if use_cache:
        cache.cache_set(key, payload)
        cache.record(hit=False)
    return Response(payload, media_type="application/json",
                    headers={"X-Cache": "MISS" if use_cache else "BYPASS"})


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
    cache.bump_version()
    return db_item

@app.get("/cache/stats")
def cache_stats():
    return cache.stats()

@app.delete("/cache/stats")
def cache_stats_reset():
    cache.reset_stats()
    return {"status": "reset"}