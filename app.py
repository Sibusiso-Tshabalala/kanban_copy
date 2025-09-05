import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import select, or_, and_
from db import SessionLocal, init_db, Task, StatusEnum
from streamlit_sortables import sort_items

# ---------------- Setup ----------------
st.set_page_config(page_title="Advanced Kanban Board", layout="wide")
init_db()

def get_session():
    return SessionLocal()

STATUS_MAP = {"Backlog": StatusEnum.Backlog, "In Progress": StatusEnum.InProgress,
              "Blocked": StatusEnum.Blocked, "Done": StatusEnum.Done}
REVERSE_STATUS_MAP = {v: k for k, v in STATUS_MAP.items()}

def status_to_enum(s): return STATUS_MAP.get(s, StatusEnum.Backlog)
def enum_to_status(e): return REVERSE_STATUS_MAP.get(e, "Backlog")

# ---------------- Sidebar ----------------
with st.sidebar:
    st.title("⚙️ Controls")
    st.subheader("Filters")
    status_filter = st.multiselect("Status", list(STATUS_MAP.keys()), default=list(STATUS_MAP.keys()))
    assignee_filter = st.text_input("Assignee contains")
    tag_filter = st.text_input("Tag contains")
    search = st.text_input("Search in title/description")
    col_from, col_to = st.columns(2)
    with col_from: from_date = st.date_input("Due from", value=None)
    with col_to: to_date = st.date_input("Due to", value=None)
    st.markdown("---")
    st.subheader("Bulk actions")
    export_csv = st.button("⬇️ Export CSV")
    import_csv = st.file_uploader("⬆️ Import CSV", type=["csv"])

# ---------------- Load tasks ----------------
def load_tasks(filters=None):
    with get_session() as db:
        stmt = select(Task)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(Task.status.asc(), Task.sort_index.asc(),
                             Task.priority.asc(), Task.due_date.asc().nulls_last())
        tasks = db.execute(stmt).scalars().all()
    rows = []
    for t in tasks:
        rows.append({"Id": t.id, "Title": t.title, "Status": enum_to_status(t.status),
                     "Priority": t.priority, "Assignee": t.assignee or "",
                     "Due Date": t.due_date.isoformat() if t.due_date else "",
                     "Tags": t.tags or "", "Description": t.description or "",
                     "Sort Index": t.sort_index or 0, "Hours Spent": getattr(t,"hours_logged",0.0)})
    df = pd.DataFrame(rows)
    for col, default in [("Id",""),("Title",""),("Status","Backlog"),("Priority",3),
                         ("Assignee",""),("Due Date",""),("Tags",""),("Description",""),
                         ("Sort Index",0),("Hours Spent",0.0)]:
        if col not in df.columns: df[col]=default
    return df

def apply_filters(): 
    filters=[]
    if status_filter: filters.append(Task.status.in_([status_to_enum(s) for s in status_filter]))
    if assignee_filter: filters.append(Task.assignee.ilike(f"%{assignee_filter}%"))
    if tag_filter: filters.append(Task.tags.ilike(f"%{tag_filter}%"))
    if search: filters.append(or_(Task.title.ilike(f"%{search}%"), Task.description.ilike(f"%{search}%")))
    if from_date: filters.append(Task.due_date >= from_date)
    if to_date: filters.append(Task.due_date <= to_date)
    return filters

df = load_tasks(apply_filters())

# ---------------- Export CSV ----------------
if export_csv:
    st.download_button("Download CSV", data=df.to_csv(index=False).encode("utf-8"),
                       file_name="tasks_export.csv", mime="text/csv")

# ---------------- Import CSV ----------------
if import_csv:
    try:
        import_df = pd.read_csv(import_csv)
        if "title" not in [c.lower() for c in import_df.columns]:
            st.error("CSV must include 'title'")
        else:
            import_df.rename(columns={c.lower(): c.lower() for c in import_df.columns}, inplace=True)
            with get_session() as db:
                for _, r in import_df.iterrows():
                    t = Task(
                        title=str(r.get("title","")).strip(),
                        status=status_to_enum(str(r.get("status","Backlog")).strip()),
                        priority=int(r.get("priority",3)),
                        assignee=str(r.get("assignee")).strip() if pd.notna(r.get("assignee")) else None,
                        description=str(r.get("description")).strip() if pd.notna(r.get("description")) else None,
                        tags=str(r.get("tags")).strip() if pd.notna(r.get("tags")) else None,
                        hours_logged=float(r.get("hours_spent",0.0))
                    )
                    due = r.get("due_date")
                    if pd.notna(due): t.due_date=pd.to_datetime(due, errors="coerce").date()
                    db.add(t)
                db.commit()
            st.success("Imported tasks successfully!")
    except Exception as e: st.error(f"Import failed: {e}")

# ---------------- Create New Task ----------------
with st.expander("➕ Create New Task", expanded=False):
    with st.form("new_task_form"):
        c1,c2,c3=st.columns([3,2,1])
        with c1: title=st.text_input("Title")
        with c2: assignee=st.text_input("Assignee")
        with c3: priority=st.selectbox("Priority",[1,2,3,4,5],index=2)
        description=st.text_area("Description")
        c4,c5=st.columns(2)
        with c4: due=st.date_input("Due Date", value=None)
        with c5: status=st.selectbox("Status", list(STATUS_MAP.keys()))
        hours=st.number_input("Hours Spent", min_value=0.0, value=0.0, step=0.25)
        submitted=st.form_submit_button("Create Task")
        if submitted and title.strip():
            try:
                with get_session() as db:
                    t=Task(title=title.strip(), assignee=assignee.strip() or None, priority=int(priority),
                           description=description.strip() or None, due_date=due, status=status_to_enum(status),
                           hours_logged=hours)
                    db.add(t)
                    db.commit()
                st.success("Task created!")
            except Exception as e: st.error(f"Failed to create task: {e}")

# ---------------- View Mode ----------------
view_mode = st.radio("View Mode", ["Kanban Board","Column View"], index=0)
statuses = list(STATUS_MAP.keys())

# ----------- Initialize Kanban in session state -----------
if "kanban_state" not in st.session_state:
    st.session_state.kanban_state = {}
    for status in statuses:
        subset = df[df["Status"]==status]
        st.session_state.kanban_state[status] = [
            {"id": str(rid), "label": f"{title} (prio:{priority}, due:{due}, hrs:{hours})"}
            for rid,title,priority,due,hours in zip(subset["Id"],subset["Title"],subset["Priority"],subset["Due Date"],subset["Hours Spent"])
        ]

# ---------- Kanban Board ----------
if view_mode=="Kanban Board":
    columns_data=[{"name":status,"items":st.session_state.kanban_state[status]} for status in statuses]
    new_columns = sort_items(columns_data, multi_containers=True, direction="horizontal", key="kanban_board")
    header_cols = st.columns(len(statuses))
    for i,h in enumerate(statuses): 
        with header_cols[i]: st.markdown(f"**{h}**")

    # Update DB only if items moved
    if new_columns != columns_data:
        updates=[]
        for col in new_columns:
            status_name=col["name"]
            for sort_index,item in enumerate(col["items"]):
                updates.append({"id":int(item["id"]),"status":status_to_enum(status_name),"sort_index":sort_index})
        with get_session() as db:
            tasks=db.execute(select(Task).where(Task.id.in_([u["id"] for u in updates]))).scalars().all()
            task_dict={t.id:t for t in tasks}
            for u in updates:
                t=task_dict.get(u["id"])
                if t: t.status=t.status=t.status_to_enum(u["status"]); t.sort_index=u["sort_index"]; db.add(t)
            db.commit()
        # Mutate session_state in place
        for col in new_columns:
            st.session_state.kanban_state[col["name"]]=col["items"]

# ---------- Column View ----------
else:
    st.subheader("Column View (Spreadsheet)")
    try:
        edited_df=st.data_editor(df.drop(columns=["Sort Index"]), use_container_width=True)
        if st.button("Save Changes"):
            with get_session() as db:
                for _, row in edited_df.iterrows():
                    t=db.get(Task,row["Id"])
                    if t:
                        t.title=row["Title"]; t.assignee=row["Assignee"] or None
                        t.priority=int(row["Priority"]); t.status=status_to_enum(row["Status"])
                        t.due_date=pd.to_datetime(row["Due Date"], errors="coerce").date() if row["Due Date"] else None
                        t.tags=row["Tags"]; t.description=row["Description"]; t.hours_logged=float(row["Hours Spent"])
                        db.add(t)
                db.commit()
            st.success("Changes saved!")
    except Exception as e: st.error(f"Failed to display/edit column view: {e}")
