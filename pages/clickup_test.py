import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}

# Search for tasks in Cost Team with Cost Status = "New Request"
r = requests.get(
    "https://api.clickup.com/api/v2/team/90152601622/search/tasks",
    headers=headers,
    params={
        "list_ids": ["901525752306"],
        "statuses": ["new case"],
        "include_closed": False
    },
)

if r.status_code == 200:
    data = r.json()
    tasks = data.get("tasks", [])
    st.success(f"Connected. {len(tasks)} tasks found.")
    for t in tasks[:20]:
        st.write(f"• {t['name']}")
else:
    st.error(f"Status {r.status_code}: {r.text}")
