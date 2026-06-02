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
        
        # Helper function to grab CSVs safely
        def get_csv(sheet_name):
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
            return pd.read_csv(url)
            
        facts = get_csv("FACT")
        products = get_csv("PRODUCTS")
        rates = get_csv("RATES")
        terms = get_csv("TERMS_%26_CONDITIONS")
        
        # Try CLIENT_NAME first. If Google gives us the FACT tab by mistake, try CLIENT NAME with a space.
        clients = get_csv("CLIENT_NAME")
        if not any('NAME' in str(c).upper() or 'CLIENT' in str(c).upper() for c in clients.columns):
            clients = get_csv("CLIENT%20NAME") # Try with a space
        
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
    client_unit_col = next((c for c in df_clients.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), df_clients.columns[-1] if not df_clients.empty else None)
    
    # --- SECTION 1: ASSET CONTEXT ANCHORING ---
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        # Use CLIENT_NAME tab for the dropdown list, filtering out empty/NaNs
        if client_unit_col:
            valid_units = [u for u in df_clients[client_unit_col].unique() if str(u).strip() and str(u).strip().upper() not in ['NAN', 'NONE']]
        else:
            valid_units = df_fact[fact_unit_id_col].unique()
        
        # Sort the list alphabetically for easier navigation
        valid_units = sorted(list(set(valid_units)), key=lambda x: str(x))
        
        selected_unit = st.selectbox("Select Unit ID", valid_units)
        
        # Fetch unit metadata from FACT tab safely (in case client is missing from FACT)
        unit_meta_df = df_fact[df_fact[fact_unit_id_col] == selected_unit]
        unit_meta = unit_meta_df.iloc[0] if not unit_meta_df.empty else {}
        
    with col_u2:
        # Strip spaces, dashes, slashes, and underscores to handle ANY typo in the database
        def super_clean(text):
            return re.sub(r'[\s\-_/]+', '', str(text)).upper()
            
        safe_selected_unit = super_clean(selected_unit)
        db_client_name = ""
        
        # Safely determine the client name column index
        name_col_idx = 0 
        for i, col in enumerate(df_clients.columns):
            if 'NAME' in str(col).upper() or 'CLIENT' in str(col).upper():
                name_col_idx = i
                break
                
        # Horizontal Row Scanner: Find the unit ID, then grab the name from that exact row
        for row_idx in range(len(df_clients)):
            row = df_clients.iloc[row_idx]
            cleaned_cells = [super_clean(cell) for cell in row]
            
            if safe_selected_unit in cleaned_cells:
                raw_name = row.iloc[name_col_idx]
                
                # Failsafe: If the extracted name happens to equal the Unit ID, pick the actual text name
                if super_clean(raw_name) == safe_selected_unit:
                    for cell in row:
                        if super_clean(cell) != safe_selected_unit and str(cell).strip() not in ['', 'NAN', 'NONE']:
                            raw_name = cell
                            break
                            
                db_client_name = str(raw_name).strip()
                break
                    
        client_name = st.text_input("Client Name Reference (Optional)", value=db_client_name)

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

    # --- SECTION 2: REQUEST TYPE & ENGINEERING SCOPE ---
    st.subheader("2. Define Engineering Scope")
    
    request_options = [
        "Roof Room", "Pool Standard", "Pool Customized", "Interior Standard Package", 
        "Interior Customized Package", "Interior Modification", "Kitchen", "Closets", 
        "Landscape", "Furniture", "Closing Double Height", "Land Extension", 
        "Exterior Painting", "Glass House", "Elevator", "A.C", "Shutters", 
        "Fence & Gates", "Pergola", "Landscape Modifications", "SOG", "Closing Elevator Shaft"
    ]
    
    selected_request_type = st.selectbox("Select Official Request Type", request_options)
    
    # -----------------------------------------------------------
    # BRANCH A: DATABASE CATALOG WORKFLOW (ROOF ROOM) - SIMPLIFIED
    # -----------------------------------------------------------
    if selected_request_type == "Roof Room":
        prod_id_col = df_products.columns[0]
        prod_unit_type_col = next((c for c in df_products.columns if 'UNIT TYPE' in c.upper()), df_products.columns[2])
        design_type_col = next((c for c in df_products.columns if 'DESIGN TYPE' in c.upper()), df_products.columns[3])
        prod_opt_link_col = next((c for c in df_products.columns if 'OPTION LINK' in c.upper() or 'DESIGN OPTION' in c.upper()), df_products.columns[4])
        prod_area_col = next((c for c in df_products.columns if 'AREA' in c.upper()), df_products.columns[5])
        desc_col_text = next((c for c in df_products.columns if 'DESCRIPTION' in c.upper()), df_products.columns[6])
        cat_col = next((c for c in df_products.columns if 'CATEGORY' in c.upper()), df_products.columns[1])
        
        target_unit_type = str(unit_type).strip().upper()
        target_design_type = str(unit_design_type).strip().upper()
        target_design_opt = str(unit_design_opt).strip().upper()
        
        filtered_catalog = df_products.copy()
        
        if target_unit_type and target_unit_type not in ['NAN', 'NONE', '']:
            mask = filtered_catalog[prod_unit_type_col].astype(str).str.upper().apply(lambda x: target_unit_type in x)
            if mask.any(): filtered_catalog = filtered_catalog[mask]
                
        if target_design_type and target_design_type not in ['NAN', 'NONE', '']:
            mask = filtered_catalog[design_type_col].astype(str).str.upper().apply(lambda x: target_design_type in x)
            if mask.any(): filtered_catalog = filtered_catalog[mask]
                
        if target_design_opt and target_design_opt not in ['NAN', 'NONE', '']:
            mask = filtered_catalog[prod_opt_link_col].astype(str).str.upper().apply(lambda x: target_design_opt in x)
            if mask.any(): filtered_catalog = filtered_catalog[mask]
                
        if filtered_catalog.empty:
            filtered_catalog = df_products

        # Simplified UI Layout
        col_vr, col_fin = st.columns([2, 1])
        
        with col_vr:
            def format_scope(idx):
                row = filtered_catalog.loc[idx]
                return f"{row[prod_area_col]} sqm - {row[desc_col_text]}"
                
            chosen_idx = st.selectbox("Specific Scope Variant", filtered_catalog.index, format_func=format_scope)
            product_record = filtered_catalog.loc[chosen_idx]
            chosen_cat = str(product_record.get(cat_col, "Roof Room"))

        with col_fin:
            rate_cat_col = df_rates.columns[0]
            category_rates = df_rates[df_rates[rate_cat_col].str.upper() == chosen_cat.upper()]
            if category_rates.empty:
                category_rates = df_rates
                
            rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
            rate_val_col = df_rates.columns[1]
            chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates[rate_opt_col].unique())
            rate_record = category_rates[category_rates[rate_opt_col] == chosen_term_option].iloc[0]

        try:
            target_item_qty = float(product_record[prod_area_col])
        except:
            target_item_qty = 0.0
            
        try:
            rate_val = str(rate_record[rate_val_col]).replace(',', '').replace('$', '').strip()
            unit_base_cost_rate = float(rate_val)
        except:
            unit_base_cost_rate = 0.0
            
        calculated_line_item_total = target_item_qty * unit_base_cost_rate

        st.metric("Total Quotation Capital Sum (EGP)", f"{calculated_line_item_total:,.2f} EGP")

        # Background staging - Bypasses manual '+' button entirely
        st.session_state.staged_items = [{
            'Product ID': product_record[prod_id_col],
            'Category': chosen_cat,
            'Description': f"[{product_record[design_type_col]} - {product_record[prod_opt_link_col]}] {product_record[desc_col_text]}",
            'Unit': 'SQM',
            'QTY': target_item_qty,
            'Rate Factor': unit_base_cost_rate,
            'Financing Options': chosen_term_option,
            'Calculated_Price': calculated_line_item_total
        }]

    # -----------------------------------------------------------
    # BRANCH B: MANUAL CUSTOM ENTRY WORKFLOW (ALL OTHER TYPES)
    # -----------------------------------------------------------
    else:
        st.markdown("### 📝 Custom Item Entry Form")
        
        custom_desc = st.text_area("Description *", help="Long answer text")
        
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            custom_unit_sel = st.selectbox("Unit *", ["SQM", "LM", "NO.", "LS", "Other"])
            if custom_unit_sel == "Other":
                custom_unit = st.text_input("Specify Unit *")
            else:
                custom_unit = custom_unit_sel
                
            custom_qty = st.number_input("QTY *", min_value=0.0, value=1.0, format="%.2f")
            
        with col_m2:
            custom_rate = st.number_input("Rate (EGP) *", min_value=0.0, value=0.0, format="%.2f")
            
            # Fetch all available financing options from RATES tab for consistency
            rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
            all_financing_opts = df_rates[rate_opt_col].unique()
            custom_financing = st.selectbox("Financing & Installment Plan", all_financing_opts)
            
        custom_total = custom_qty * custom_rate
        st.info(f"📐 **Run Details:** {custom_qty} {custom_unit} × {custom_rate:,.2f} EGP = **{custom_total:,.2f} EGP**")
        
        if st.button("➕ Stage Custom Line Item", use_container_width=True):
            if not custom_desc.strip():
                st.warning("⚠️ Please enter a Description before staging the item.")
            else:
                st.session_state.staged_items.append({
                    'Product ID': "CUSTOM",
                    'Category': selected_request_type,
                    'Description': custom_desc,
                    'Unit': custom_unit,
                    'QTY': custom_qty,
                    'Rate Factor': custom_rate,
                    'Financing Options': custom_financing,
                    'Calculated_Price': custom_total
                })
                st.toast("Custom line item pinned successfully.")
                st.rerun()

    st.divider()

    # --- SECTION 3: BOQ BILL OF QUANTITIES SUMMARY (ONLY FOR NON-ROOF ROOM ITEMS) ---
    if selected_request_type != "Roof Room":
        st.subheader("3. Technical Bill of Quantities & Commercial Summary")
        
        if st.session_state.staged_items:
            summary_df = pd.DataFrame(st.session_state.staged_items)
            st.dataframe(summary_df[['Product ID', 'Category', 'Description', 'Unit', 'QTY', 'Rate Factor', 'Financing Options', 'Calculated_Price']], use_container_width=True)
            
            aggregate_commercial_sum = summary_df['Calculated_Price'].sum()
            st.metric("Total Quotation Capital Sum (EGP)", f"{aggregate_commercial_sum:,.2f} EGP")
            
            st.markdown("##### Manage Staged Items")
            del_col1, del_col2, del_col3 = st.columns([2, 1, 1])
            with del_col1:
                item_to_remove = st.selectbox(
                    "Select Line Item to Remove", 
                    range(len(st.session_state.staged_items)), 
                    format_func=lambda x: f"{st.session_state.staged_items[x]['Product ID']} - {st.session_state.staged_items[x]['Category']}"
                )
            with del_col2:
                st.write("") 
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
        else:
            st.write("No active engineering metrics currently staged inside calculation layout.")
            
    # --- EXPORT BUTTONS (SHARED FOR BOTH PATHS) ---
    if st.session_state.staged_items:
        final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
        
        summary_df = pd.DataFrame(st.session_state.staged_items)
        aggregate_commercial_sum = summary_df['Calculated_Price'].sum()
        
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            if st.button("🌐 Generate Official Google Doc via Webhook", use_container_width=True, type="primary"):
                with st.spinner("Transmitting to Google Workspace..."):
                    payload = {
                        "unitId": selected_unit,
                        "clientName": final_client_name,
                        "zone": str(zone_name),
                        "requestType": selected_request_type, 
                        "items": []
                    }
                    
                    for item in st.session_state.staged_items:
                        payload["items"].append({
                            "description": item["Description"],
                            "unit": item["Unit"],
                            "qty": item["QTY"],
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

        with col_export2:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            pdf.cell(0, 10, "ORASCOM DEVELOPMENT - O WEST", ln=True, align="C")
            pdf.set_font("Helvetica", "", 12)
            pdf.cell(0, 10, f"Date generated: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
            pdf.cell(0, 10, f"Client Reference Name: {final_client_name}", ln=True)
            pdf.cell(0, 10, f"Unit ID Assignment: {selected_unit}", ln=True)
            pdf.cell(0, 10, f"Request Type: {selected_request_type}", ln=True)
            pdf.ln(8)
            
            # Adjusted PDF Header Widths to accommodate Unit and QTY
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(20, 8, "Product ID", border=1)
            pdf.cell(30, 8, "Category", border=1)
            pdf.cell(75, 8, "Scope Description", border=1)
            pdf.cell(15, 8, "Unit", border=1)
            pdf.cell(15, 8, "QTY", border=1)
            pdf.cell(35, 8, "Price (EGP)", border=1, ln=True)
            
            pdf.set_font("Helvetica", "", 9)
            for _, item_row in summary_df.iterrows():
                pdf.cell(20, 8, str(item_row['Product ID']), border=1)
                pdf.cell(30, 8, str(item_row['Category'])[:15], border=1) # Trim to fit width
                pdf.cell(75, 8, str(item_row['Description'])[:42], border=1)
                pdf.cell(15, 8, str(item_row['Unit']), border=1)
                pdf.cell(15, 8, str(item_row['QTY']), border=1)
                pdf.cell(35, 8, f"{item_row['Calculated_Price']:,.2f}", border=1, ln=True)
                
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 12)
            pdf.cell(0, 10, f"Total Summary Value: {aggregate_commercial_sum:,.2f} EGP", ln=True)
            pdf.ln(6)
            
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
            
            pdf_out = pdf.output(dest="S")
            # FPDF2 vs Legacy FPDF check to prevent AttributeError
            if isinstance(pdf_out, str):
                compiled_pdf_payload = pdf_out.encode("latin-1", errors="ignore")
            else:
                compiled_pdf_payload = bytes(pdf_out)
            
            st.download_button(
                label="📄 Download Quick PDF Preview",
                data=compiled_pdf_payload,
                file_name=f"O_West_Proposal_{final_client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
else:
    st.info("Awaiting structural backend database connection strings...")
