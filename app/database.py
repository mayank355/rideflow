import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL")

# The engine manages the actual connection pool to Postgres
engine = create_engine(DATABASE_URL)

# SessionLocal is a factory — each request gets its own Session instance from this
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base is the parent class every SQLAlchemy model inherits from.
# It's how SQLAlchemy knows "these Python classes correspond to database tables."
Base = declarative_base()


def get_db():
    """
    Dependency-injected into routes via FastAPI's Depends().
    Ensures every request gets a fresh DB session and it's always closed
    afterward — even if the request raises an exception.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
