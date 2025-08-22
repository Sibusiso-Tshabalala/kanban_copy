from sqlalchemy import create_engine, Column, Integer, String, Text, Date, DateTime, Enum
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
import enum
import os

# ---- Database URL ----
DB_PATH = os.environ.get("KANBAN_DB_PATH", "kanban.db")
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URI, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

class StatusEnum(enum.Enum):
    Backlog = "Backlog"
    InProgress = "In Progress"
    Blocked = "Blocked"
    Done = "Done"

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.Backlog, index=True, nullable=False)
    priority = Column(Integer, default=3)  # 1 (High) .. 5 (Low)
    assignee = Column(String(100), nullable=True, index=True)
    due_date = Column(Date, nullable=True, index=True)
    tags = Column(String(200), nullable=True)  # comma-separated
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    sort_index = Column(Integer, default=0)  # ordering within a column

    def tag_list(self):
        return [t.strip() for t in (self.tags or '').split(',') if t.strip()]

def init_db():
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Lightweight migration: ensure 'sort_index' exists
    with engine.connect() as conn:
        cols = conn.execute("PRAGMA table_info(tasks);").fetchall()
        names = [c[1] for c in cols]
        if "sort_index" not in names:
            conn.execute("ALTER TABLE tasks ADD COLUMN sort_index INTEGER DEFAULT 0;")
            conn.commit()
