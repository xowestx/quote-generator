import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}
list_id = st.secrets["CLICKUP_LIST_ID"]

# Use the correct search endpoint
r = requests.get(
    f"https://api.clickup.com/api/v2/list/{list_id}/task",
    headers=headers,
    params={
        "statuses": ["new case"],
    },
)

if r.status_code == 200:
    tasks = r.json().get("tasks", [])
    st.success(f"Connected. {len(tasks)} 'new case' tasks found.")
    for t in tasks[:20]:
        st.write(f"• {t['name']}")
else:
    st.error(f"Status {r.status_code}: {r.text}")
