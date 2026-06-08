import streamlit as st
import pandas as pd

# 1. CENTRALIZED ROOM PRICE CONFIGURATION
# This eliminates "multiplier" logic and maps the exact Room-Package string to its price.
ROOM_PRICES = {
    "RECEPTION - P1": 225193.10,
    "RECEPTION - P2": 204637.62,
    "RECEPTION - P3": 183530.38,
    "LIVING ROOM - P1": 204958.27,
    "LIVING ROOM - P2": 196108.33,
    "LIVING ROOM - P3": 193405.19,
    "DINING ROOM - P1": 201455.32,
    "DINING ROOM - P2": 245996.63,
    "MASTER BEDROOM - P1": 230736.11,
    "MASTER BEDROOM - P2": 194754.34,
    "MASTER BEDROOM - P3": 230557.03,
    "KIDS BEDROOM - P1": 199236.18,
    "KIDS BEDROOM - P2": 182723.31,
    "NANNY'S ROOM": 31914.96,
    "TERRACE - P1": 31262.77,
    "TERRACE - P2": 12829.63,
    "TERRACE - P3": 9803.42,
    "OUTDOORS - P1": 49704.38,
    "OUTDOORS - P2": 64153.21,
}

def render_furniture_calculator():
    st.header("Furniture Selection Calculator")

    # Initialize Session State for rows
    if 'rows' not in st.session_state:
        st.session_state.rows = [{'room': list(ROOM_PRICES.keys())[0], 'qty': 1}]

    def add_row():
        st.session_state.rows.append({'room': list(ROOM_PRICES.keys())[0], 'qty': 1})

    # Render Rows
    total_cost = 0
    for i, row in enumerate(st.session_state.rows):
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            # Using a unique key prevents the "glitching" where states mix between rows
            st.session_state.rows[i]['room'] = st.selectbox(
                f"Room Selection {i+1}", 
                options=list(ROOM_PRICES.keys()), 
                key=f"room_{i}"
            )
        with col2:
            st.session_state.rows[i]['qty'] = st.number_input(
                f"Qty {i+1}", min_value=1, value=row['qty'], key=f"qty_{i}"
            )
        with col3:
            price = ROOM_PRICES[st.session_state.rows[i]['room']]
            row_total = price * st.session_state.rows[i]['qty']
            st.write(f"**P {row_total:,.2f}**")
            total_cost += row_total

    if st.button("Add Another Room"):
        add_row()
        st.rerun()

    st.divider()
    st.subheader(f"Total Furniture Cost: P {total_cost:,.2f}")

# Main App Execution
if __name__ == "__main__":
    render_furniture_calculator()
