import requests
import streamlit as st

st.title("ClickUp connection test")

headers = {"Authorization": st.secrets["CLICKUP_TOKEN"]}
list_id = st.secrets["CLICKUP_LIST_ID"]

st.write(f"List ID: {list_id}")

# Try fetching with different parameters
r = requests.get(
    f"https://api.clickup.com/api/v2/list/{list_id}/task",
    headers=headers,
)

st.write(f"Status: {r.status_code}")
st.write(f"Response: {r.json()}")
