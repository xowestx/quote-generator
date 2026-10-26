import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}
list_id = st.secrets["CLICKUP_LIST_ID"]

# Fetch all tasks including closed
r = requests.get(
    f"https://api.clickup.com/api/v2/list/{list_id}/task",
    headers=headers,
    params={"include_closed": "true"},
)

if r.status_code == 200:
    all_tasks = r.json()["tasks"]
    st.success(f"Connected. {len(all_tasks)} total tasks found.")
    
    st.write("### All tasks in Cost Team:")
    for t in all_tasks[:20]:
        status = t.get("status", {}).get("status", "No status")
        st.write(f"• {t['name']} — Status: {status}")
else:
    st.error(f"Failed with status {r.status_code}: {r.text}")
