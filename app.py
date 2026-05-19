import streamlit as st
import pandas as pd
from datetime import datetime
import uuid
from fpdf import FPDF

# --- DATABASE SETUP ---
def initialize_database():
    if 'units_df' not in st.session_state:
        st.session_state.units_df = pd.DataFrame({
            'Unit_ID': ['U-1001', 'U-1002', 'U-2001'],
            'Zone': ['WHYT', 'WHYT', 'Tulwa'],
            'Unit_Type': ['Standalone Villa', 'Townhouse', 'Standalone Villa'],
            'Roof_Area': [120.5, 65.0, 150.0],
            'Garden_Area': [350.0, 120.0, 400.0],
        })
    if 'products_df' not in st.session_state:
        st.session_state.products_df = pd.DataFrame({
            'Product_ID': ['P-01', 'P-02', 'P-03'],
            'Category': ['Pools', 'Pools', 'Roof Rooms'],
            'Variant_Name': ['Infinity Pool', 'Plunge Pool', 'Deluxe Roof Suite'],
            'Valid_Unit_Type': ['Standalone Villa', 'Townhouse', 'Standalone Villa'],
            'Base_Rate': [5000, 35000, 1500], 
            'Multiplier_Column': ['Garden_Area', 'Flat', 'Roof_Area']
        })
    if 'current_quote_items' not in st.session_state:
        st.session_state.current_quote_items = []

# --- PDF GENERATOR ---
def create_pdf(client_name, unit_id, items_df, total):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", "B", 16)
    pdf.cell(0, 10, "Extra Works Quotation", ln=True, align="C")
    pdf.set_font("helvetica", "", 12)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
    pdf.cell(0, 10, f"Client: {client_name}", ln=True)
    pdf.cell(0, 10, f"Unit ID: {unit_id}", ln=True)
    pdf.ln(10)
    
    # Table Header
    pdf.set_font("helvetica", "B", 12)
    pdf.cell(80, 10, "Product", border=1)
    pdf.cell(40, 10, "Category", border=1)
    pdf.cell(40, 10, "Price", border=1, ln=True)
    
    # Table Rows
    pdf.set_font("helvetica", "", 12)
    for _, row in items_df.iterrows():
        pdf.cell(80, 10, str(row['Variant_Name']), border=1)
        pdf.cell(40, 10, str(row['Category']), border=1)
        pdf.cell(40, 10, f"${row['Calculated_Price']:,.2f}", border=1, ln=True)
        
    pdf.ln(10)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, f"Total: ${total:,.2f}", ln=True)
    
    return pdf.output(dest="S").encode("latin-1")

# --- APP LAYOUT ---
st.set_page_config(page_title="Quotation Tool", layout="wide")
initialize_database()

st.title("📝 Build Quotation")

col1, col2 = st.columns(2)
selected_unit = col1.selectbox("Select Unit", st.session_state.units_df['Unit_ID'])
client_name = col2.text_input("Client Name")

unit_data = st.session_state.units_df[st.session_state.units_df['Unit_ID'] == selected_unit].iloc[0]
unit_type = unit_data['Unit_Type']

st.subheader("Add Products")
valid_products = st.session_state.products_df[st.session_state.products_df['Valid_Unit_Type'] == unit_type]

cat_col, prod_col, btn_col = st.columns([2, 2, 1])
category = cat_col.selectbox("Category", valid_products['Category'].unique())
filtered_vars = valid_products[valid_products['Category'] == category]
product = prod_col.selectbox("Product", filtered_vars['Variant_Name'])

if btn_col.button("➕ Add Item", use_container_width=True):
    prod_data = filtered_vars[filtered_vars['Variant_Name'] == product].iloc[0]
    base = prod_data['Base_Rate']
    mult = prod_data['Multiplier_Column']
    price = base if mult == 'Flat' else base * unit_data[mult]
    
    st.session_state.current_quote_items.append({
        'Category': category, 'Variant_Name': product, 'Calculated_Price': price
    })
    st.rerun()

st.divider()
st.subheader("Current Quote")
if st.session_state.current_quote_items:
    df = pd.DataFrame(st.session_state.current_quote_items)
    st.dataframe(df, use_container_width=True)
    total_price = df['Calculated_Price'].sum()
    st.metric("Total", f"${total_price:,.2f}")
    
    if client_name:
        pdf_bytes = create_pdf(client_name, selected_unit, df, total_price)
        st.download_button(
            label="📄 Generate & Download PDF Quote",
            data=pdf_bytes,
            file_name=f"Quote_{client_name.replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary"
        )
    else:
        st.warning("Enter a Client Name to generate the PDF.")