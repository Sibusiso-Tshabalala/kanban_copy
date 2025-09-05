from sqlalchemy import create_engine, Column, Integer, String, Date, Enum, Float
from sqlalchemy.orm import sessionmaker, declarative_base
import enum

Base = declarative_base()
engine = create_engine("sqlite:///tasks.db", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)

class StatusEnum(enum.Enum):
    Backlog = "Backlog"
    InProgress = "In Progress"
    Blocked = "Blocked"
    Done = "Done"

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    assignee = Column(String, nullable=True)
    priority = Column(Integer, default=3)
    description = Column(String, nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(Enum(StatusEnum), default=StatusEnum.Backlog)
    tags = Column(String, nullable=True)
    sort_index = Column(Integer, default=0)
    hours_logged = Column(Float, default=0.0)  # hours spent
    start_time = Column(Date, nullable=True)   # optional for timer simulation

def init_db():
    Base.metadata.create_all(bind=engine)
