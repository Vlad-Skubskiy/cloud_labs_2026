import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Не задано змінну середовища в DATABASE_URL")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_size=10, max_overflow=5, pool_timeout=5, pool_recycle=1800)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()