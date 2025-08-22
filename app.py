import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import select, or_, and_
from sqlalchemy.exc import SQLAlchemyError
from streamlit_sortables import sort_items

from db import SessionLocal, init_db, Task, StatusEnum

st.set_page_config(page_title="Kanban Board", layout="wide")
init_db()

# ------------- Helpers -------------
def get_session():
    return SessionLocal()

def status_order(s):
    order = ["Backlog", "In Progress", "Blocked", "Done"]
    try:
        return order.index(s)
    except ValueError:
        return 99

def status_to_enum(s):
    mapping = {
        "Backlog": StatusEnum.Backlog,
        "In Progress": StatusEnum.InProgress,
        "Blocked": StatusEnum.Blocked,
        "Done": StatusEnum.Done,
    }
    return mapping[s]

def enum_to_status(e):
    return {
        StatusEnum.Backlog: "Backlog",
        StatusEnum.InProgress: "In Progress",
        StatusEnum.Blocked: "Blocked",
        StatusEnum.Done: "Done",
    }[e]

# ------------- Sidebar: Filters / Import / Export -------------
with st.sidebar:
    st.title("⚙️ Controls")
    # Filters
    st.subheader("Filters")
    status_filter = st.multiselect(
        "Status", ["Backlog", "In Progress", "Blocked", "Done"],
        default=["Backlog", "In Progress", "Blocked", "Done"]
    )
    assignee_filter = st.text_input("Assignee contains")
    tag_filter = st.text_input("Tag contains")
    search = st.text_input("Search in title/description")

    col_from, col_to = st.columns(2)
    with col_from:
        from_date = st.date_input("Due from", value=None)
    with col_to:
        to_date = st.date_input("Due to", value=None)

    st.markdown("---")
    st.subheader("Bulk actions")
    exp = st.button("⬇️ Export CSV")
    up = st.file_uploader("⬆️ Import CSV", type=["csv"])

# ------------- Header & Create/Edit -------------
st.title("📌 Streamlit Kanban (Advanced) — with Drag & Drop")
st.caption("Drag tasks between columns, filter & persist to SQLite.")

with st.expander("➕ Create New Task", expanded=False):
    with st.form("new_task"):
        c1, c2, c3 = st.columns([3,2,1])
        with c1:
            title = st.text_input("Title", placeholder="e.g., Unit Standards Presentation")
        with c2:
            assignee = st.text_input("Assignee", placeholder="e.g., Alfred")
        with c3:
            priority = st.selectbox("Priority (1=High)", [1,2,3,4,5], index=2)

        description = st.text_area("Description", placeholder="What needs to be done?")
        c4, c5, c6 = st.columns(3)
        with c4:
            due = st.date_input("Due date", value=None)
        with c5:
            status = st.selectbox("Status", ["Backlog","In Progress","Blocked","Done"], index=0)
        with c6:
            tags = st.text_input("Tags (comma-separated)", placeholder="training, finance")

        submitted = st.form_submit_button("Create Task")
        if submitted:
            if not title.strip():
                st.warning("Title is required.")
            else:
                with get_session() as db:
                    t = Task(
                        title=title.strip(),
                        assignee=assignee.strip() or None,
                        priority=int(priority),
                        description=description.strip() or None,
                        due_date=due,
                        status=status_to_enum(status),
                        tags=(tags or None)
                    )
                    db.add(t)
                    db.commit()
                    st.success("Task created.")

# ------------- Load tasks (apply filters) -------------
def load_tasks():
    with get_session() as db:
        stmt = select(Task)
        filters = []
        if status_filter:
            filters.append(Task.status.in_([status_to_enum(s) for s in status_filter]))
        if assignee_filter:
            filters.append(Task.assignee.ilike(f"%{assignee_filter}%"))
        if tag_filter:
            filters.append(Task.tags.ilike(f"%{tag_filter}%"))
        if search:
            filters.append(or_(Task.title.ilike(f"%{search}%"), Task.description.ilike(f"%{search}%")))
        if from_date:
            filters.append(Task.due_date >= from_date)
        if to_date:
            filters.append(Task.due_date <= to_date)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(Task.status.asc(), Task.sort_index.asc(), Task.priority.asc(), Task.due_date.asc().nulls_last())
        tasks = db.execute(stmt).scalars().all()
        rows = []
        for t in tasks:
            rows.append({
                "id": t.id,
                "title": t.title,
                "status": enum_to_status(t.status),
                "priority": t.priority,
                "assignee": t.assignee or "",
                "due_date": t.due_date.isoformat() if t.due_date else "",
                "tags": t.tags or "",
                "description": t.description or "",
                "sort_index": t.sort_index or 0,
            })
        return pd.DataFrame(rows)

df = load_tasks()

# ------------- Export / Import -------------
if exp:
    st.download_button("Download CSV", data=df.to_csv(index=False).encode("utf-8"), file_name="tasks_export.csv", mime="text/csv")

if up is not None:
    try:
        import_df = pd.read_csv(up)
        required = {"title"}
        if not required.issubset(set([c.lower() for c in import_df.columns])):
            st.error("CSV must include at least a 'title' column.")
        else:
            # normalize columns
            columns = {c: c.lower() for c in import_df.columns}
            import_df.rename(columns=columns, inplace=True)
            with get_session() as db:
                for _, r in import_df.iterrows():
                    t = Task(
                        title=str(r.get("title","")).strip(),
                        status=status_to_enum(str(r.get("status","Backlog")).strip() or "Backlog"),
                        priority=int(r.get("priority",3)),
                        assignee=(str(r.get("assignee")) if pd.notna(r.get("assignee")) else None),
                        description=(str(r.get("description")) if pd.notna(r.get("description")) else None),
                        tags=(str(r.get("tags")) if pd.notna(r.get("tags")) else None),
                    )
                    due = r.get("due_date")
                    if pd.notna(due):
                        try:
                            t.due_date = pd.to_datetime(due).date()
                        except Exception:
                            pass
                    db.add(t)
                db.commit()
            st.success("Imported tasks from CSV.")
    except Exception as e:
        st.error(f"Import failed: {e}")

# ------------- DnD Board UI -------------
statuses = ["Backlog", "In Progress", "Blocked", "Done"]
columns = []
df["due_str"] = df["due_date"].fillna("").astype(str)

df_sorted = df.sort_values(by=["status", "sort_index", "priority", "due_date"], na_position="last")

for status in statuses:
    subset = df_sorted[df_sorted["status"] == status]

    items = [
        {
            "id": int(row_id),
            "title": f"{title} (prio: {priority}, due: {due})"
        }
        for row_id, title, priority, due in zip(
            subset["id"], subset["title"], subset["priority"], subset["due_str"]
        )
    ]
    
    columns.append({"name": status, "items": items})

st.subheader("Board")

new_columns = sort_items(
    columns,
    multi_containers=True,
    direction="horizontal",
    key="kanban"
)


header_cols = st.columns(4)
for i, h in enumerate(statuses):
    with header_cols[i]:
        st.markdown(f"**{h}**")


if new_columns is not None and new_columns != columns:

    updates = []
    for col_idx, col in enumerate(new_columns):
        status_name = statuses[col_idx]
        for sort_index, item in enumerate(col["items"]):
            updates.append({
                "id": item["id"],
                "status": status_to_enum(status_name),
                "sort_index": sort_index
            })

    
    with get_session() as db:
        task_ids = [u["id"] for u in updates]
        tasks = db.execute(select(Task).where(Task.id.in_(task_ids))).scalars().all()
        task_dict = {t.id: t for t in tasks}

        for u in updates:
            t = task_dict.get(u["id"])
            if t:
                t.status = u["status"]
                t.sort_index = u["sort_index"]
                db.add(t)

        db.commit()
    st.experimental_rerun()


st.markdown("---")
st.subheader("Edit / Delete Selected Task")


choices = [f"#{r.id} — {r.title}" for _, r in df.sort_values(by=["status","sort_index"]).iterrows()]
selected = st.selectbox("Select a task", [""] + choices, index=0)

def parse_selected(sel):
    if not sel or not sel.startswith("#"):
        return None
    try:
        return int(sel.split("—")[0].strip().lstrip("#"))
    except Exception:
        return None

task_id = parse_selected(selected)
if task_id:
    with get_session() as db:
        t = db.get(Task, task_id)

    with st.form(f"edit_form_{task_id}"):
        c1, c2, c3 = st.columns([3,2,1])
        title = c1.text_input("Title", value=t.title)
        assignee = c2.text_input("Assignee", value=t.assignee or "")
        priority = c3.selectbox("Priority", [1,2,3,4,5], index=(t.priority-1 if t.priority and 1 <= t.priority <= 5 else 2))
        description = st.text_area("Description", value=t.description or "")
        c4, c5, c6 = st.columns(3)
        due_val = pd.to_datetime(t.due_date).date() if t.due_date else None
        due = c4.date_input("Due date", value=due_val)
        status = c5.selectbox("Status", statuses, index=statuses.index(enum_to_status(t.status)))
        tags = c6.text_input("Tags", value=t.tags or "")

        c7, c8 = st.columns(2)
        save = c7.form_submit_button("Save")
        delete = c8.form_submit_button("Delete")

        if save:
            with get_session() as db:
                t = db.get(Task, task_id)
                t.title = title.strip() or t.title
                t.assignee = assignee.strip() or None
                t.priority = int(priority)
                t.description = description.strip() or None
                t.due_date = due
                t.status = status_to_enum(status)
                t.tags = tags.strip() or None
                db.add(t)
                db.commit()
            st.success("Saved.")
            st.experimental_rerun()
        if delete:
            with get_session() as db:
                t = db.get(Task, task_id)
                if t:
                    db.delete(t)
                    db.commit()
            st.success("Deleted.")
            st.experimental_rerun()
