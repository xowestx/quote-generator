import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import re
import requests
import json

# ==========================================
# 1. CORE DATA LOADING ENGINE (GOOGLE SHEETS)
# ==========================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1uyZXYMvaeuH-ZQOxHgpdyXiC2vlvUHtK3Cmde63cnUY/edit?usp=sharing"

# Hardcoded Webhook URL
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzzt5KDoxG9DbYPXzFe7HiYJ6WgYdpsYE65p7Zuwnq6PycZdvbtGyCe_8G1OwwM3cxP/exec"

@st.cache_data(ttl=60)
def load_all_tabs(base_url):
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
        
        # CORE FIX: Destroy all NaN (blank) cells immediately so Python never throws a TypeError
        for df in [facts, products, rates, clients, terms]:
            df.columns = [str(c).strip() for c in df.columns]
            
            # Fill numeric columns with 0 and non-numeric with empty strings to prevent dtype conflicts
            num_cols = df.select_dtypes(include=['number']).columns
            df[num_cols] = df[num_cols].fillna(0)
            
            obj_cols = df.select_dtypes(exclude=['number']).columns
            df[obj_cols] = df[obj_cols].fillna('')
            
            for col in df.select_dtypes(include=['object']).columns:
                df[col] = df[col].astype(str).str.strip()
                
        return facts, products, rates, clients, terms
    except Exception as e:
        st.error(f"Error accessing Google Sheet tabs. Details: {e}")
        return None, None, None, None, None

# ==========================================
# 2. APPLICATION INTERFACE
# ==========================================
st.set_page_config(page_title="O West Extra Works Configurator", layout="wide")

if st.sidebar.button("🔄 Hard Reset & Fetch Latest Data"):
    st.cache_data.clear()
    st.rerun()

st.title("🏗️ Extra Works Quotation Engine")

df_fact, df_products, df_rates, df_clients, df_terms = load_all_tabs(GSHEET_URL)

if 'staged_items' not in st.session_state:
    st.session_state.staged_items = []

if df_fact is not None and not df_fact.empty:
    
    fact_unit_id_col = next((c for c in df_fact.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), df_fact.columns[0])
    
    # --- SECTION 1: ASSET CONTEXT ANCHORING ---
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        selected_unit = st.selectbox("Select Unit ID", df_fact[fact_unit_id_col].unique())
        unit_meta = df_fact[df_fact[fact_unit_id_col] == selected_unit].iloc[0]
        
    with col_u2:
        # 🚀 SUPER FUZZY MATCHING LOGIC
        # Strip spaces, dashes, slashes, and underscores to handle ANY typo in the database
        def super_clean(text):
            return re.sub(r'[\s\-_/]+', '', str(text)).upper()
            
        safe_selected_unit = super_clean(selected_unit)
        
        # Identify Client Name column reliably
        client_name_col = next((c for c in df_clients.columns if 'NAME' in str(c).upper() or 'CLIENT' in str(c).upper()), df_clients.columns[0])
        
        db_client_name = ""
        # Search every single column in the clients sheet for the fuzzy Unit ID
        for col in df_clients.columns:
            cleaned_col = df_clients[col].apply(super_clean)
            matched_rows = df_clients[cleaned_col == safe_selected_unit]
            
            if not matched_rows.empty:
                raw_name = matched_rows.iloc[0][client_name_col]
                cleaned_raw = super_clean(raw_name)
                
                # Ensure we didn't just extract the Unit ID or a blank value by accident
                if cleaned_raw != safe_selected_unit and cleaned_raw not in ['NAN', 'NONE', '']:
                    db_client_name = str(raw_name).strip()
                    break # Success! Match found.
                    
        client_name = st.text_input("Client Name Reference", value=db_client_name)

    unit_type = unit_meta.get('Unit Type', '')
    unit_design_type = unit_meta.get('Design Type', '')
    unit_design_opt = unit_meta.get('Design Options', '')
    unit_bua = unit_meta.get('Built Up Area', 0)
    zone_name = unit_meta.get('Zone', 'Unknown Zone')
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unit Profile", str(unit_type) if unit_type else "N/A")
    m2.metric("Native Design Options", str(unit_design_opt) if unit_design_opt else "N/A")
    m3.metric("Native Design Type", str(unit_design_type) if unit_design_type else "N/A")
    m4.metric("Built Up Area (BUA)", f"{unit_bua} sqm")
    
    st.divider()

    # --- SECTION 2: CUMULATIVE SMART FILTER ---
    st.subheader("2. Add Engineering Option Scope")
    
    # Locate product columns safely (moved up for broader access)
    prod_id_col = df_products.columns[0]
    prod_unit_type_col = next((c for c in df_products.columns if 'UNIT TYPE' in c.upper()), df_products.columns[2])
    design_type_col = next((c for c in df_products.columns if 'DESIGN TYPE' in c.upper()), df_products.columns[3])
    prod_opt_link_col = next((c for c in df_products.columns if 'OPTION LINK' in c.upper() or 'DESIGN OPTION' in c.upper()), df_products.columns[4])
    prod_area_col = next((c for c in df_products.columns if 'AREA' in c.upper()), df_products.columns[5])
    desc_col_text = next((c for c in df_products.columns if 'DESCRIPTION' in c.upper()), df_products.columns[6])
    
    target_unit_type = str(unit_type).strip().upper()
    target_design_type = str(unit_design_type).strip().upper()
    target_design_opt = str(unit_design_opt).strip().upper()
    
    # 1. Base Copy
    filtered_catalog = df_products.copy()
    
    # 2. Filter by Unit Type (If applicable)
    if target_unit_type and target_unit_type not in ['NAN', 'NONE', '']:
        mask = filtered_catalog[prod_unit_type_col].astype(str).str.upper().apply(lambda x: target_unit_type in x)
        if mask.any():
            filtered_catalog = filtered_catalog[mask]
            
    # 3. Narrow by Design Type (If applicable)
    if target_design_type and target_design_type not in ['NAN', 'NONE', '']:
        mask = filtered_catalog[design_type_col].astype(str).str.upper().apply(lambda x: target_design_type in x)
        if mask.any():
            filtered_catalog = filtered_catalog[mask]
            
    # 4. Narrow by Design Option Link (If applicable)
    if target_design_opt and target_design_opt not in ['NAN', 'NONE', '']:
        mask = filtered_catalog[prod_opt_link_col].astype(str).str.upper().apply(lambda x: target_design_opt in x)
        if mask.any():
            filtered_catalog = filtered_catalog[mask]
            
    if filtered_catalog.empty:
        st.warning("No specific architectural matches found. Loading full catalog.")
        filtered_catalog = df_products

    # 4-Column Layout to include the Specific Variant Selection
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    
    with col_p1:
        cat_col = next((c for c in df_products.columns if 'CATEGORY' in c.upper()), df_products.columns[1])
        chosen_cat = st.selectbox("Work Category Scope", filtered_catalog[cat_col].unique())
        filtered_by_cat = filtered_catalog[filtered_catalog[cat_col] == chosen_cat]
        
    with col_p2:
        chosen_option_link = st.selectbox("Design Option Link Specification", filtered_by_cat[prod_opt_link_col].unique())
        filtered_by_link = filtered_by_cat[filtered_by_cat[prod_opt_link_col] == chosen_option_link]
        
    with col_p3:
        chosen_design_type = st.selectbox("Design Type Grouping", filtered_by_link[design_type_col].unique())
        filtered_by_design = filtered_by_link[filtered_by_link[design_type_col] == chosen_design_type]
        
    with col_p4:
        # Create a display format combining Area and Description for pinpoint product selection
        def format_scope(idx):
            row = filtered_by_design.loc[idx]
            return f"{row[prod_area_col]} sqm - {row[desc_col_text]}"
            
        chosen_idx = st.selectbox("Specific Scope Variant", filtered_by_design.index, format_func=format_scope)
        product_record = filtered_by_design.loc[chosen_idx]

    # --- LIVE PRODUCT & ASSET DATA PREVIEW PANEL ---
    st.markdown("### 🔍 Product Specification Match Preview")
    preview_box = st.container(border=True)
    with preview_box:
        cp1, cp2, cp3, cp4 = st.columns(4)
        cp1.write(f"👤 **Registered Sheet Client:** \n`{db_client_name if db_client_name else 'Unassigned'}`")
        cp2.write(f"🆔 **Product ID Match:** \n`{product_record[prod_id_col]}`")
        cp3.write(f"📐 **Product Area:** \n`{product_record[prod_area_col]} sqm`")
        cp4.write(f"📝 **Scope Variant:** \n{product_record[desc_col_text]}")

    # Finance / Installment Lookup Context Block
    st.markdown("#### Financing Structure")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        rate_cat_col = df_rates.columns[0]
        category_rates = df_rates[df_rates[rate_cat_col].str.upper() == str(chosen_cat).upper()]
        if category_rates.empty:
            category_rates = df_rates
            
        rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
        rate_val_col = df_rates.columns[1]
        chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates[rate_opt_col].unique())
        rate_record = category_rates[category_rates[rate_opt_col] == chosen_term_option].iloc[0]

    # --- COMMERCIAL CALCULATION LOGIC ---
    try:
        target_item_area = float(product_record[prod_area_col])
    except:
        target_item_area = 0.0
        
    try:
        rate_val = str(rate_record[rate_val_col]).replace(',', '').replace('$', '').strip()
        unit_base_cost_rate = float(rate_val)
    except:
        unit_base_cost_rate = 0.0
        
    calculated_line_item_total = target_item_area * unit_base_cost_rate

    with col_f2:
        st.metric("Dynamic Price Run Calculation", f"{calculated_line_item_total:,.2f} EGP")
    st.info(f"📐 **Run Details:** {target_item_area} sqm × {unit_base_cost_rate:,.2f} EGP = **{calculated_line_item_total:,.2f} EGP**")

    if st.button("➕ Stage Engineering Line Item to Scope Summary", use_container_width=True):
        st.session_state.staged_items.append({
            'Product ID': product_record[prod_id_col],
            'Category': chosen_cat,
            'Description': f"[{product_record[design_type_col]} - {product_record[prod_opt_link_col]}] {product_record[desc_col_text]}",
            'Area (sqm)': target_item_area,
            'Rate Factor': unit_base_cost_rate,
            'Financing Options': chosen_term_option,
            'Calculated_Price': calculated_line_item_total
        })
        st.toast("Line item pinned successfully.")
        st.rerun()

    st.divider()

    # --- SECTION 3: BOQ BILL OF QUANTITIES SUMMARY & EXPORT GENERATOR ---
    st.subheader("3. Technical Bill of Quantities & Commercial Summary")
    
    if st.session_state.staged_items:
        summary_df = pd.DataFrame(st.session_state.staged_items)
        st.dataframe(summary_df[['Product ID', 'Category', 'Description', 'Area (sqm)', 'Rate Factor', 'Financing Options', 'Calculated_Price']], use_container_width=True)
        
        aggregate_commercial_sum = summary_df['Calculated_Price'].sum()
        st.metric("Total Quotation Capital Sum (EGP)", f"{aggregate_commercial_sum:,.2f} EGP")
        
        # --- NEW FEATURE: INDIVIDUAL ITEM DELETION ---
        st.markdown("##### Manage Staged Items")
        del_col1, del_col2, del_col3 = st.columns([2, 1, 1])
        with del_col1:
            item_to_remove = st.selectbox(
                "Select Line Item to Remove", 
                range(len(st.session_state.staged_items)), 
                format_func=lambda x: f"{st.session_state.staged_items[x]['Product ID']} - {st.session_state.staged_items[x]['Category']}"
            )
        with del_col2:
            st.write("") # Spacing to align with selectbox
            st.write("")
            if st.button("🗑️ Remove Selected Item", use_container_width=True):
                st.session_state.staged_items.pop(item_to_remove)
                st.toast("Item removed from BOQ.")
                st.rerun()
        with del_col3:
            st.write("") 
            st.write("")
            if st.button("❌ Reset Entire BOQ", type="secondary", use_container_width=True):
                st.session_state.staged_items = []
                st.rerun()
                
        st.divider()
        # ---------------------------------------------
        
        # Allow export even if client name is empty
        final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
        
        col_export1, col_export2 = st.columns(2)
        
        # ----------------------------------------------------
        # WEBHOOK EXPORT BUTTON (GOOGLE DOCS)
        # ----------------------------------------------------
        with col_export1:
            if st.button("🌐 Generate Official Google Doc via Webhook", use_container_width=True, type="primary"):
                with st.spinner("Transmitting to Google Workspace..."):
                    # Prepare JSON payload matching what your Apps Script needs
                    payload = {
                        "unitId": selected_unit,
                        "clientName": final_client_name,
                        "zone": str(zone_name),
                        "requestType": "Roof Room", # Updated to specifically request Roof Room terms
                        "items": []
                    }
                    
                    for item in st.session_state.staged_items:
                        payload["items"].append({
                            "description": item["Description"],
                            "unit": "sqm",
                            "qty": item["Area (sqm)"],
                            "rate": item["Rate Factor"]
                        })
                        
                    try:
                        headers = {"Content-Type": "application/json"}
                        response = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            if response_data.get("status") == "success":
                                st.success("✅ Quotation Generated Successfully!")
                                st.markdown(f"**[📄 Click Here to Open the Generated Google Doc]({response_data.get('docUrl')})**")
                            else:
                                st.error(f"Apps Script Error: {response_data.get('message')}")
                        else:
                            st.error(f"HTTP Error {response.status_code}: Failed to reach Google Apps Script.")
                    except Exception as e:
                        st.error(f"Connection failed: {e}")

        # ----------------------------------------------------
        # STANDARD FPDF EXPORT BUTTON
        # ----------------------------------------------------
        with col_export2:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "ORASCOM DEVELOPMENT - O WEST", ln=True, align="C")
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, f"Date generated: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
            pdf.cell(0, 10, f"Client Reference Name: {final_client_name}", ln=True)
            pdf.cell(0, 10, f"Unit ID Assignment: {selected_unit}", ln=True)
            pdf.ln(8)
            
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(25, 8, "Product ID", border=1)
            pdf.cell(35, 8, "Category", border=1)
            pdf.cell(75, 8, "Scope Description", border=1)
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
            
            # --- FIX FOR FPDF / FPDF2 VERSION CONFLICT ---
            pdf_out = pdf.output(dest="S")
            # If it's a string (Legacy FPDF), encode it. If it's a bytearray (Modern FPDF2), just convert to bytes.
            if isinstance(pdf_out, str):
                compiled_pdf_payload = pdf_out.encode("latin-1", errors="ignore")
            else:
                compiled_pdf_payload = bytes(pdf_out)
            # ---------------------------------------------
            
            st.download_button(
                label="📄 Download Quick PDF Preview",
                data=compiled_pdf_payload,
                file_name=f"O_West_Proposal_{final_client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    else:
        st.write("No active engineering metrics currently staged inside calculation layout.")
else:
    st.info("Awaiting structural backend database connection strings...")
