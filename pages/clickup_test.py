import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}

# Search all tasks in workspace with specific criteria
r = requests.get(
    "https://api.clickup.com/api/v2/team/90152601622/task",
    headers=headers,
    params={
        "list_ids": ["901525752306"],
        "page": 0,
    },
)

if r.status_code == 200:
    tasks = r.json().get("tasks", [])
    st.success(f"Connected. {len(tasks)} tasks found.")
    for t in tasks[:20]:
        st.write(f"• {t['name']}")
else:
    st.error(f"Status {r.status_code}: {r.text}")
