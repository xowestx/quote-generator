import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF

# ==========================================
# 1. CORE DATA LOADING ENGINE (GOOGLE SHEETS)
# ==========================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1uyZXYMvaeuH-ZQOxHgpdyXiC2vlvUHtK3Cmde63cnUY/edit?usp=sharing"

@st.cache_data(ttl=60)
def load_all_tabs(base_url):
    try:
        sheet_id = base_url.split("/d/")[1].split("/")[0]
        
        fact_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=FACT"
        products_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=PRODUCTS"
        rates_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=RATES"
        clients_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=CLIENT_NAME"
        terms_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet=TERMS_%26_CONDITIONS"
        
        # Read data natively from your live spreadsheet tabs
        facts = pd.read_csv(fact_url)
        products = pd.read_csv(products_url)
        rates = pd.read_csv(rates_url)
        clients = pd.read_csv(clients_url)
        terms = pd.read_csv(terms_url)
        
        # Strip trailing/leading spaces from column names and string content safely
        for df in [facts, products, rates, clients, terms]:
            df.columns = [str(c).strip() for c in df.columns]
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].astype(str).str.strip()
                
        return facts, products, rates, clients, terms
    except Exception as e:
        st.error(f"Error accessing Google Sheet tabs. Details: {e}")
        return None, None, None, None, None

# ==========================================
# 2. APPLICATION INTERFACE & INITIALIZATION
# ==========================================
st.set_page_config(page_title="O West Extra Works Configurator", layout="wide")

# Manual hard-reset button to immediately wipe server cache memory
if st.sidebar.button("🔄 Hard Reset & Fetch Latest Data"):
    st.cache_data.clear()
    st.rerun()

st.title("🏗️ Extra Works Quotation Engine")

df_fact, df_products, df_rates, df_clients, df_terms = load_all_tabs(GSHEET_URL)

if 'staged_items' not in st.session_state:
    st.session_state.staged_items = []

if df_fact is not None and not df_fact.empty:
    # --- SECTION 1: ASSET & CLIENT ANCHORING ---
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        # Pulls 'Unit ID' dynamically by column positioning to protect against header typos
        unit_id_col = df_fact.columns[0]
        selected_unit = st.selectbox("Select Unit ID", df_fact[unit_id_col].unique())
        unit_meta = df_fact[df_fact[unit_id_col] == selected_unit].iloc[0]
        
    with col_u2:
        # Match client data dynamically by row position index (removes 'Client Name' header dependency)
        client_unit_col = df_clients.columns[2] if len(df_clients.columns) > 2 else df_clients.columns[-1]
        matched_client = df_clients[df_clients[client_unit_col] == selected_unit]
        
        default_client_name = ""
        if not matched_client.empty:
            # Safely picks the first data cell value in the matched row as the name
            default_client_name = matched_client.iloc[0].values[0]
            
        client_name = st.text_input("Client Name Reference", value=str(default_client_name))

    # Metric Context Display Panel (Safe fallback retrieval mapping strings)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Zone", str(unit_meta.values[2] if len(unit_meta) > 2 else "N/A"))
    m2.metric("Unit Structural Profiling", str(unit_meta.values[4] if len(unit_meta) > 4 else "N/A"))
    m3.metric("Built Up Area (BUA)", f"{unit_meta.values[7] if len(unit_meta) > 7 else 0} sqm")
    m4.metric("Garden Area", f"{unit_meta.values[11] if len(unit_meta) > 11 else 0} sqm")
    
    st.divider()

    # --- SECTION 2: WORK CATALOG CONFIGURATOR ---
    st.subheader("2. Add Engineering Option Scope")
    
    # Safe positional fallback extract for Unit Type criteria variables
    active_unit_type = str(unit_meta.values[4] if len(unit_meta) > 4 else "").strip().upper()
    prod_type_col = df_products.columns[2] if len(df_products.columns) > 2 else df_products.columns[0]
    filtered_catalog_by_type = df_products[df_products[prod_type_col].str.upper() == active_unit_type]
    
    if filtered_catalog_by_type.empty:
        st.warning("No structural profile filters matched perfectly. Loading comprehensive catalog list.")
        filtered_catalog_by_type = df_products

    col_p1, col_p2, col_p3 = st.columns(3)
    
    with col_p1:
        cat_col = df_products.columns[1] if len(df_products.columns) > 1 else df_products.columns[0]
        chosen_cat = st.selectbox("Work Category Scope", filtered_catalog_by_type[cat_col].unique())
        filtered_by_cat = filtered_catalog_by_type[filtered_catalog_by_type[cat_col] == chosen_cat]
        
    with col_p2:
        desc_col = df_products.columns[6] if len(df_products.columns) > 6 else df_products.columns[-1]
        chosen_variant = st.selectbox("Architectural Product Specification", filtered_by_cat[desc_col].unique())
        product_record = filtered_by_cat[filtered_by_cat[desc_col] == chosen_variant].iloc[0]
        
    with col_p3:
        rate_cat_col = df_rates.columns[0]
        category_rates = df_rates[df_rates[rate_cat_col].str.upper() == str(chosen_cat).upper()]
        if category_rates.empty:
            category_rates = df_rates
            
        rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
        chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates[rate_opt_col].unique())
        rate_record = category_rates[category_rates[rate_opt_col] == chosen_term_option].iloc[0]

    # --- PRICING METRIC ENGINE ---
    try:
        # Grab target product area parameter using physical position index
        target_item_area = float(product_record.values[5] if len(product_record) > 5 else 0)
    except:
        target_item_area = 0.0
        
    try:
        # Grab target finance configuration rate using physical position index
        rate_val = str(rate_record.values[1] if len(rate_record) > 1 else 0).replace(',', '').replace('$', '').strip()
        unit_base_cost_rate = float(rate_val)
    except:
        unit_base_cost_rate = 0.0
        
    calculated_line_item_total = target_item_area * unit_base_cost_rate

    st.info(f"📐 **Calculation Engine:** {target_item_area} sqm × {unit_base_cost_rate:,.2f} EGP = **{calculated_line_item_total:,.2f} EGP**")

    if st.button("➕ Stage Engineering Line Item to Scope Summary", use_container_width=True):
        st.session_state.staged_items.append({
            'Product ID': product_record.values[0],
            'Category': chosen_cat,
            'Description': chosen_variant,
            'Area (sqm)': target_item_area,
            'Rate Factor': unit_base_cost_rate,
            'Financing Options': chosen_term_option,
            'Calculated_Price': calculated_line_item_total
        })
        st.toast("Line item successfully appended.")
        st.rerun()

    st.divider()

    # --- SECTION 3: BOQ QUANTITY STAGING & OUTPUT PACKAGE GENERATION ---
    st.subheader("3. Technical Bill of Quantities & Commercial Summary")
    
    if st.session_state.staged_items:
        summary_df = pd.DataFrame(st.session_state.staged_items)
        st.dataframe(summary_df[['Product ID', 'Category', 'Description', 'Area (sqm)', 'Rate Factor', 'Financing Options', 'Calculated_Price']], use_container_width=True)
        
        aggregate_commercial_sum = summary_df['Calculated_Price'].sum()
        st.metric("Total Quotation Capital Sum (EGP)", f"{aggregate_commercial_sum:,.2f} EGP")
        
        if st.button("❌ Reset Work Scope Form"):
            st.session_state.staged_items = []
            st.rerun()
            
        if client_name:
            # Build Professional PDF Output Package
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "ORASCOM DEVELOPMENT - O WEST", ln=True, align="C")
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, f"Date generated: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
            pdf.cell(0, 10, f"Client Reference Name: {client_name}", ln=True)
            pdf.cell(0, 10, f"Unit ID Assignment: {selected_unit}", ln=True)
            pdf.ln(8)
            
            # Print Table Section Headers
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(25, 8, "Product ID", border=1)
            pdf.cell(35, 8, "Category", border=1)
            pdf.cell(75, 8, "Scope Description", border=1)
            pdf.cell(20, 8, "Area (m2)", border=1)
            pdf.cell(35, 8, "Price (EGP)", border=1, ln=True)
            
            # Populate Table Matrix Content Data Rows
            pdf.set_font("Helvetica", "", 9)
            for _, item_row in summary_df.iterrows():
                pdf.cell(25, 8, str(item_row['Product ID']), border=1)
                pdf.cell(35, 8, str(item_row['Category']), border=1)
                pdf.cell(75, 8, str(item_row['Description'])[:42], border=1)
                pdf.cell(20, 8, str(item_row['Area (sqm)']), border=1)
                pdf.cell(35, 8, f"{item_row['Calculated_Price']:,.2f}", border=1, ln=True)
                
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, f"Total Summary Value: {aggregate_commercial_sum:,.2f} EGP", ln=True)
            pdf.ln(6)
            
            # Dynamic Legal Contract Terms Appender Block
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, "Legal Framework & Strategic Project Adjustments:", ln=True)
            pdf.set_font("Helvetica", "", 8)
            
            terms_opt_col = df_terms.columns[1] if len(df_terms.columns) > 1 else df_terms.columns[0]
            terms_text_col = df_terms.columns[2] if len(df_terms.columns) > 2 else df_terms.columns[-1]
            
            processed_legal_terms = summary_df['Financing Options'].unique()
            for rule_term in processed_legal_terms:
                matched_legal_text_blocks = df_terms[df_terms[terms_opt_col] == rule_term][terms_text_col].values
                if len(matched_legal_text_blocks) > 0:
                    pdf.multi_cell(0, 4, str(matched_legal_text_blocks[0]))
                    pdf.ln(2)
            
            compiled_pdf_payload = pdf.output(dest="S").encode("latin-1", errors="ignore")
            
            st.download_button(
                label="📄 Download PDF Proposal Package",
                data=compiled_pdf_payload,
                file_name=f"O_West_Proposal_{client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        else:
            st.warning("Ensure the client identification entry field is complete.")
    else:
        st.write("No active physical extensions currently staged inside calculation layout.")
else:
    st.info("Awaiting structural backend database connection strings...")
