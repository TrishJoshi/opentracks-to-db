from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# --- CONFIGURATION ---
# Update these with your actual credentials and IP for Container 1
DB_USER = "importer_user"
DB_PASSWORD = "h1oxVUHxX8QzSX"
DB_HOST = "192.168.0.30" # IP of your track-db container
DB_PORT = "5432"
DB_NAME = "life_db"

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
