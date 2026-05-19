import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF

# ==========================================
# 1. CORE DATA LOADING ENGINE (GOOGLE SHEETS)
# ==========================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1uyZXYMvaeuH-ZQOxHgpdyXiC2vlvUHtK3Cmde63cnUY/edit?usp=sharing"

@st.cache_data(ttl=300)
def load_all_tabs(base_url):
    """Converts a standard Google Sheet share link into a direct pandas CSV export link for each tab."""
    try:
        sheet_id = base_url.split("/d/")[1].split("/")[0]
        
        fact_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=FACT"
        products_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=PRODUCTS"
        rates_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=RATES"
        clients_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=CLIENT_NAME"
        terms_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=TERMS_%26_CONDITIONS"
        
        facts = pd.read_csv(fact_url)
        products = pd.read_csv(products_url)
        rates = pd.read_csv(rates_url)
        clients = pd.read_csv(clients_url)
        terms = pd.read_csv(terms_url)
        
        # Strip invisible spaces from column names safely
        facts.columns = [str(c).strip() for c in facts.columns]
        products.columns = [str(c).strip() for c in products.columns]
        rates.columns = [str(c).strip() for c in rates.columns]
        clients.columns = [str(c).strip() for c in clients.columns]
        terms.columns = [str(c).strip() for c in terms.columns]
            
        # Force map key column names to match the application logic securely
        clients.columns = [
            'Client Name' if 'CLIENT' in col.upper() else 
            'Unit ID' if 'UNIT' in col.upper() else col 
            for col in clients.columns
        ]
        
        facts.rename(columns=lambda x: 'Unit ID' if 'UNIT' in x.upper() else ('Unit Type' if 'TYPE' in x.upper() else x), inplace=True)
        products.rename(columns=lambda x: 'Unit Type' if 'TYPE' in x.upper() else x, inplace=True)
        
        # Clean specific cell text string values to prevent matching mismatches
        facts['Unit ID'] = facts['Unit ID'].astype(str).str.strip()
        facts['Unit Type'] = facts['Unit Type'].astype(str).str.strip()
        products['Unit Type'] = products['Unit Type'].astype(str).str.strip()
        clients['Unit ID'] = clients['Unit ID'].astype(str).str.strip()
        
        return facts, products, rates, clients, terms
    except Exception as e:
        st.error(f"Error accessing Google Sheet tabs. Details: {e}")
        return None, None, None, None, None

df_fact, df_products, df_rates, df_clients, df_terms = load_all_tabs(GSHEET_URL)

if 'staged_items' not in st.session_state:
    st.session_state.staged_items = []

# ==========================================
# 2. APPLICATION INTERFACE
# ==========================================
st.set_page_config(page_title="O West Extra Works Configurator", layout="wide")
st.title("🏗️ Extra Works Quotation Engine")

if df_fact is not None and not df_fact.empty:
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        selected_unit = st.selectbox("Select Unit ID", df_fact['Unit ID'].unique())
        unit_meta = df_fact[df_fact['Unit ID'] == selected_unit].iloc[0]
        
    with col_u2:
        matched_client = df_clients[df_clients['Unit ID'] == str(selected_unit).strip()]
        default_client_name = ""
        if not matched_client.empty:
            default_client_name = matched_client.iloc[0]['Client Name']
            
        client_name = st.text_input("Client Name Reference", value=default_client_name)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Zone", str(unit_meta.get('Zone', 'N/A')))
    m2.metric("Unit Structural Profiling", str(unit_meta.get('Unit Type', 'N/A')))
    m3.metric("Built Up Area (BUA)", f"{unit_meta.get('Built Up Area', 0)} sqm")
    m4.metric("Garden Area", f"{unit_meta.get('Garden Area', 0)} sqm")
    
    st.divider()

    st.subheader("2. Add Engineering Option Scope")
    
    active_unit_type = str(unit_meta['Unit Type']).strip().upper()
    filtered_catalog_by_type = df_products[df_products['Unit Type'].astype(str).str.strip().str.upper() == active_unit_type]
    
    if filtered_catalog_by_type.empty:
        st.warning(f"No entry found matching exactly '{unit_meta['Unit Type']}' in PRODUCTS sheet. Showing full list as fallback.")
        filtered_catalog_by_type = df_products

    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        chosen_cat = st.selectbox("Work Category Scope", filtered_catalog_by_type['Category'].unique())
        filtered_by_cat = filtered_catalog_by_type[filtered_catalog_by_type['Category'] == chosen_cat]
        
    with col_p2:
        chosen_variant = st.selectbox("Architectural Product Specification", filtered_by_cat['Description'].unique())
        product_record = filtered_by_cat[filtered_by_cat['Description'] == chosen_variant].iloc[0]
        
    with col_p3:
        category_rates = df_rates[df_rates['Category'].astype(str).str.strip().str.upper() == str(chosen_cat).strip().str.upper()]
        if category_rates.empty:
            category_rates = df_rates
        chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates['Options'].unique())
        rate_record = category_rates[category_rates['Options'] == chosen_term_option].iloc[0]

    try:
        target_item_area = float(product_record.get('Area (sqm)', 0))
    except:
        target_item_area = 0.0
        
    try:
        rate_val = str(rate_record.get('Rate (per sqm)', 0)).replace(',', '').replace('$', '').strip()
        unit_base_cost_rate = float(rate_val)
    except:
        unit_base_cost_rate = 0.0
        
    calculated_line_item_total = target_item_area * unit_base_cost_rate

    st.info(f"📐 **Calculation Run Logic:** {target_item_area} sqm (Product Area Block) × {unit_base_cost_rate:,.2f} EGP (Rate Scale Factor) = **{calculated_line_item_total:,.2f} EGP**")

    if st.button("➕ Stage Engineering Line Item to Scope Summary", use_container_width=True):
        st.session_state.staged_items.append({
            'Product ID': product_record['Product ID'],
            'Category': chosen_cat,
            'Description': chosen_variant,
            'Area (sqm)': target_item_area,
            'Rate Factor': unit_base_cost_rate,
            'Financing Options': chosen_term_option,
            'Calculated_Price': calculated_line_item_total
        })
        st.toast("Line item appended to calculation stack.")
        st.rerun()

    st.divider()

    st.subheader("3. Technical Bill of Quantities & Commercial Summary")
    
    if st.session_state.staged_items:
        summary_df = pd.DataFrame(st.session_state.staged_items)
        st.dataframe(summary_df[['Product ID', 'Category', 'Description', 'Area (sqm)', 'Rate Factor', 'Financing Options', 'Calculated_Price']], use_container_width=True)
        
        aggregate_commercial_sum = summary_df['Calculated_Price'].sum()
        st.metric("Total Quotation Capital Sum (EGP)", f"{aggregate_commercial_sum:,.2f} EGP")
        
        if st.button("❌ Reset Work Scope Form Layout Stack"):
            st.session_state.staged_items = []
            st.rerun()
            
        if client_name:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "ORASCOM DEVELOPMENT - O WEST", ln=True, align="C")
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, f"Date generated: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
            pdf.cell(0, 10, f"Client Structural Reference Name: {client_name}", ln=True)
            pdf.cell(0, 10, f"Property Asset Unit Assignment ID: {selected_unit}", ln=True)
            pdf.ln(8)
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(25, 8, "Product ID", border=1)
            pdf.cell(35, 8, "Category", border=1)
            pdf.cell(75, 8, "Scope Description Variant", border=1)
            pdf.cell(20, 8, "Area (m2)", border=1)
            pdf.cell(35, 8, "Price (EGP)", border=1, ln=True)
            
            pdf.set_font("Helvetica", "", 9)
            for _, item_row in summary_df.iterrows():
                pdf.cell(25, 8, str(item_row['Product ID']), border=1)
                pdf.cell(35, 8, str(item_row['Category']), border=1)
                pdf.cell(75, 8, str(item_row['Description'])[:42], border=1)
                pdf.cell(20, 8, str(item_row['Area (sqm)']), border=1)
                pdf.cell(35, 8, f"{item_row['Calculated_Price']:,.2f}", border=1, ln=True)
                
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, f"Total Aggregate Summary Value: {aggregate_commercial_sum:,.2f} EGP", ln=True)
            pdf.ln(6)
            
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Legal Framework, Commitments, & Strategic Project Adjustments:", ln=True)
            pdf.set_font("Helvetica", "", 8)
            
            processed_legal_terms = summary_df['Financing Options'].unique()
            for rule_term in processed_legal_terms:
                matched_legal_text_blocks = df_terms[df_terms['Options'].astype(str).str.strip() == str(rule_term).strip()]['TERM'].values
                if len(matched_legal_text_blocks) > 0:
                    pdf.multi_cell(0, 4, str(matched_legal_text_blocks[0]))
                    pdf.ln(2)
            
            compiled_pdf_payload = pdf.output(dest="S").encode("latin-1", errors="ignore")
            
            st.download_button(
                label="📄 Finalize Contract Formulation & Download PDF Proposal Package",
                data=compiled_pdf_payload,
                file_name=f"O_West_Proposal_{client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("Ensure the client identification entry field is complete before initializing document processing pipeline loops.")
    else:
        st.write("No active physical extensions currently staged inside current calculation template.")
else:
    st.info("Awaiting structural backend connection strings parsing engine runtime...")