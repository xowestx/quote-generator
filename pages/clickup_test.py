import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}
list_id = st.secrets["CLICKUP_LIST_ID"]

r = requests.get(
    f"https://api.clickup.com/api/v2/list/{list_id}/task",
    headers=headers,
    params={"include_closed": "false"},
)

if r.status_code == 200:
    tasks = r.json()["tasks"]
    st.success(f"Connected. {len(tasks)} open tasks found.")
    for t in tasks[:20]:
        st.write(f"• {t['name']}")
else:
    st.error(f"Failed with status {r.status_code}: {r.text}")