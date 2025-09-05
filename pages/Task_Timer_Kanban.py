import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import select
from db import SessionLocal, init_db, Task, StatusEnum

st.set_page_config(page_title="Kanban Excel Board", layout="wide")
init_db()

def get_session():
    return SessionLocal()

def enum_to_status(e):
    return {
        StatusEnum.Backlog: "Backlog",
        StatusEnum.InProgress: "In Progress",
        StatusEnum.Blocked: "Blocked",
        StatusEnum.Done: "Done",
    }[e]

def status_to_enum(s):
    mapping = {
        "Backlog": StatusEnum.Backlog,
        "In Progress": StatusEnum.InProgress,
        "Blocked": StatusEnum.Blocked,
        "Done": StatusEnum.Done,
    }
    return mapping[s]

def load_tasks():
    with get_session() as db:
        tasks = db.execute(select(Task)).scalars().all()
        rows = []
        for t in tasks:
            rows.append({
                "id": t.id,
                "Title": t.title,
                "Status": enum_to_status(t.status),
                "Assignee": t.assignee or "",
                "Priority": t.priority,
                "Due Date": t.due_date.isoformat() if t.due_date else "",
                "Hours Spent": getattr(t, "hours_logged", 0.0)
            })
        return pd.DataFrame(rows)

st.title("📊 Kanban Excel Board")
df = load_tasks()

st.subheader("Editable Spreadsheet")
edited_df = st.data_editor(df, num_rows="dynamic", key="kanban_excel_sheet", use_container_width=True)

if st.button("Save Changes"):
    with get_session() as db:
        for _, row in edited_df.iterrows():
            t = db.get(Task, int(row["id"]))
            if t:
                t.title = row["Title"]
                t.assignee = row["Assignee"]
                t.priority = int(row["Priority"])
                t.due_date = pd.to_datetime(row["Due Date"]).date() if row["Due Date"] else None
                t.status = status_to_enum(row["Status"])
                t.hours_logged = float(row["Hours Spent"])
                db.add(t)
        db.commit()
    st.success("Changes saved!")
    st.experimental_rerun()
