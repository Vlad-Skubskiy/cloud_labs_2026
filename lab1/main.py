from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
import models
from database import engine, SessionLocal

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health_check():
    return {
        "status": "good"
    }

@app.get("/items")
def get_items(db: Session = Depends(get_db)):
    return db.query(models.Item).all()

@app.post("/items")
def post_item(name: str, description: str = None, db: Session = Depends(get_db)):
    db_item = models.Item(name=name, description=description)
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item