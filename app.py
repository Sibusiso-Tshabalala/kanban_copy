import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import select, or_, and_
from streamlit_sortables import sort_items
from db import SessionLocal, init_db, Task, StatusEnum
import base64

# ------------------- Setup -------------------
st.set_page_config(page_title="Advanced Kanban Board", layout="wide")
init_db()

def get_session():
    return SessionLocal()

# ------------------- Embed Logo -------------------


def get_logo_base64(path="logo.png"):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

logo_base64 = get_logo_base64()
# ------------------- Custom Styling -------------------
st.markdown(f"""
    <style>
    .company-logo {{
        display: flex;
        align-items: center;
        margin-bottom: 20px;
    }}
    .company-logo img {{
        height: 70px;
        margin-right: 15px;
    }}
    .company-logo h2 {{
        margin: 0;
        color: #003366;
    }}
    .kanban-header {{
        background-color: #003366;
        color: white;
        padding: 8px;
        border-radius: 6px;
        text-align: center;
        font-weight: bold;
    }}
    .sortable-item {{
        background-color: #f0f6ff !important;
        border: 1px solid #003366 !important;
        border-radius: 8px !important;
        padding: 8px !important;
        margin: 4px 0 !important;
        color: #003366 !important;
        font-weight: 500;
    }}
    .sortable-item:hover {{
        background-color: #dceaff !important;
        cursor: grab !important;
    }}
    </style>
    <div class="company-logo">
        <img src="data:image/png;base64,{logo_base64}">
        <h2>MULUMA MANAGEMENT CONSULTING GROUP</h2>
    </div>
""", unsafe_allow_html=True)


# ------------------- Helpers -------------------
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

# ------------------- Sidebar -------------------
with st.sidebar:
    st.title("⚙️ Controls")
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
    export_csv = st.button("⬇️ Export CSV")
    import_csv = st.file_uploader("⬆️ Import CSV", type=["csv"])

# ------------------- Load Tasks -------------------
def load_tasks(filters=None):
    with get_session() as db:
        stmt = select(Task)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(
            Task.status.asc(), Task.sort_index.asc(),
            Task.priority.asc(), Task.due_date.asc().nulls_last()
        )
        tasks = db.execute(stmt).scalars().all()
        rows = []
        for t in tasks:
            rows.append({
                "Id": t.id,
                "Title": t.title,
                "Status": enum_to_status(t.status),
                "Priority": t.priority,
                "Assignee": t.assignee or "",
                "Due Date": t.due_date.isoformat() if t.due_date else "",
                "Tags": t.tags or "",
                "Description": t.description or "",
                "Sort Index": t.sort_index or 0,
                "Hours Spent": getattr(t, "hours_logged", 0.0),
            })
        return pd.DataFrame(rows)

# ------------------- Apply Filters -------------------
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

df = load_tasks(filters=filters)

# ------------------- Export CSV -------------------
if export_csv:
    st.download_button(
        "Download CSV", data=df.to_csv(index=False).encode("utf-8"),
        file_name="tasks_export.csv", mime="text/csv"
    )

# ------------------- Import CSV -------------------
if import_csv:
    try:
        import_df = pd.read_csv(import_csv)
        required = {"title"}
        if not required.issubset({c.lower() for c in import_df.columns}):
            st.error("CSV must include at least 'title'")
        else:
            import_df.rename(columns={c: c.lower() for c in import_df.columns}, inplace=True)
            with get_session() as db:
                for _, r in import_df.iterrows():
                    t = Task(
                        title=str(r.get("title", "")).strip(),
                        status=status_to_enum(str(r.get("status", "Backlog")).strip()),
                        priority=int(r.get("priority", 3)),
                        assignee=str(r.get("assignee")).strip() if pd.notna(r.get("assignee")) else None,
                        description=str(r.get("description")).strip() if pd.notna(r.get("description")) else None,
                        tags=str(r.get("tags")).strip() if pd.notna(r.get("tags")) else None,
                        hours_logged=float(r.get("hours_spent", 0.0)),
                    )
                    due = r.get("due_date")
                    if pd.notna(due):
                        try:
                            t.due_date = pd.to_datetime(due).date()
                        except Exception:
                            pass
                    db.add(t)
                db.commit()
            st.success("Imported tasks successfully!")
            st.rerun()
    except Exception as e:
        st.error(f"Import failed: {e}")

# ------------------- Create New Task -------------------
with st.expander("➕ Create New Task", expanded=False):
    with st.form("new_task_form"):
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            title = st.text_input("Title")
        with c2:
            assignee = st.text_input("Assignee")
        with c3:
            priority = st.selectbox("Priority", [1, 2, 3, 4, 5], index=2)
        description = st.text_area("Description")
        c4, c5 = st.columns(2)
        with c4:
            due = st.date_input("Due Date")
        with c5:
            status = st.selectbox("Status", ["Backlog", "In Progress", "Blocked", "Done"])
        hours = st.number_input("Hours Spent", min_value=0.0, value=0.0, step=0.25)
        submitted = st.form_submit_button("Create Task")
        if submitted and title.strip():
            with get_session() as db:
                t = Task(
                    title=title.strip(),
                    assignee=assignee.strip() or None,
                    priority=int(priority),
                    description=description.strip() or None,
                    due_date=due,
                    status=status_to_enum(status),
                    hours_logged=hours,
                )
                db.add(t)
                db.commit()
            st.success("Task created!")
            st.rerun()

# ------------------- View Mode -------------------
view_mode = st.radio("View Mode", ["Kanban Board", "Column View"], index=0)
statuses = ["Backlog", "In Progress", "Blocked", "Done"]

# ---------- Kanban ----------
if view_mode == "Kanban Board":
    if "kanban_state" not in st.session_state:
        st.session_state.kanban_state = {}
        for status in statuses:
            subset = df[df["Status"] == status]
            st.session_state.kanban_state[status] = [
                f"{rid}:: {title} (prio:{priority}, due:{due}, hrs:{hours})"
                for rid, title, priority, due, hours in zip(
                    subset["Id"], subset["Title"], subset["Priority"],
                    subset["Due Date"], subset["Hours Spent"]
                )
            ]

    columns_data = [
        {"name": status, "items": st.session_state.kanban_state[status]}
        for status in statuses
    ]
    new_columns = sort_items(
        columns_data, multi_containers=True, direction="horizontal", key="kanban_board"
    )

    header_cols = st.columns(len(statuses))
    for i, h in enumerate(statuses):
        with header_cols[i]:
            st.markdown(f"<div class='kanban-header'>{h}</div>", unsafe_allow_html=True)

    # Update DB only if items moved
    if new_columns and new_columns != columns_data:
        updates = []
        for col in new_columns:
            status_name = col["name"]
            for sort_index, item in enumerate(col["items"]):
                task_id = int(item.split("::", 1)[0])  # extract ID
                updates.append({
                    "id": task_id,
                    "status": status_to_enum(status_name),
                    "sort_index": sort_index,
                })

        with get_session() as db:
            tasks = db.execute(
                select(Task).where(Task.id.in_([u["id"] for u in updates]))
            ).scalars().all()
            task_dict = {t.id: t for t in tasks}
            for u in updates:
                t = task_dict.get(u["id"])
                if t:
                    t.status = u["status"]
                    t.sort_index = u["sort_index"]
                    db.add(t)
            db.commit()

        for col in new_columns:
            st.session_state.kanban_state[col["name"]] = col["items"]

        st.rerun()

    # ---------- Task actions ----------
    st.markdown("---")
    st.subheader("📝 Task Actions")

    for status in statuses:
        if st.session_state.kanban_state[status]:
            with st.expander(f"{status} Tasks"):
                for item in st.session_state.kanban_state[status]:
                    task_id = int(item.split("::", 1)[0])
                    col1, col2, col3 = st.columns([4, 1, 1])
                    with col1:
                        st.text(item.split("::", 1)[1])
                    with col2:
                        if st.button("✏️ Edit", key=f"edit_{task_id}"):
                            st.session_state.editing_task = task_id
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{task_id}"):
                            with get_session() as db:
                                db.query(Task).filter(Task.id == task_id).delete()
                                db.commit()
                            st.session_state.kanban_state[status] = [
                                i for i in st.session_state.kanban_state[status]
                                if not i.startswith(f"{task_id}::")
                            ]
                            st.success(f"Task {task_id} deleted!")
                            st.rerun()

    # ---------- Edit form ----------
    if "editing_task" in st.session_state:
        task_id = st.session_state.editing_task
        with get_session() as db:
            task = db.get(Task, task_id)
        if task:
            with st.expander(f"✏️ Editing Task {task_id}", expanded=True):
                with st.form(f"edit_form_{task_id}"):
                    title = st.text_input("Title", task.title)
                    assignee = st.text_input("Assignee", task.assignee or "")
                    priority = st.selectbox("Priority", [1, 2, 3, 4, 5], index=task.priority-1)
                    description = st.text_area("Description", task.description or "")
                    due = st.date_input("Due Date", task.due_date or date.today())
                    status = st.selectbox("Status", statuses, index=statuses.index(enum_to_status(task.status)))
                    hours = st.number_input("Hours Spent", min_value=0.0, value=task.hours_logged or 0.0, step=0.25)
                    save = st.form_submit_button("💾 Save Changes")
                if save:
                    with get_session() as db:
                        t = db.get(Task, task_id)
                        if t:
                            t.title = title.strip()
                            t.assignee = assignee.strip() or None
                            t.priority = int(priority)
                            t.description = description.strip() or None
                            t.due_date = due
                            t.status = status_to_enum(status)
                            t.hours_logged = hours
                            db.add(t)
                            db.commit()
                    st.success(f"Task {task_id} updated!")
                    del st.session_state.editing_task
                    st.rerun()

else:
    st.subheader("Column View (Spreadsheet)")
    st.dataframe(df.drop(columns=["Sort Index"]))
