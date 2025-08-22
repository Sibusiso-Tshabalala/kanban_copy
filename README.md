# Streamlit Kanban (Advanced, with SQLite)

A modern Kanban app built with **Python + Streamlit + SQLite (SQLAlchemy)**.

## Features
- Columns: Backlog, In Progress, Blocked, Done
- Create, edit, delete tasks
- Move tasks across columns (single-click)
- Search, filter by assignee, status, date range, and tags
- Priority, due date, description, and tags (comma-separated)
- Bulk CSV import/export
- Persistent storage in `kanban.db` (SQLite)
- Responsive 3/4-column layout with Streamlit cards

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Notes
- DB file is created automatically on first run.
- You can switch to Postgres/MySQL by updating the SQLALCHEMY_DATABASE_URI in `db.py`.
