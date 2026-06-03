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

# Fallback clear if old schema exists to prevent crashes
if st.session_state.staged_items and 'Calculated_Price' in st.session_state.staged_items[0]:
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
        
        # Fetch unit metadata from FACT tab safely
        unit_meta_df = df_fact[df_fact[fact_unit_id_col] == selected_unit]
        unit_meta = unit_meta_df.iloc[0] if not unit_meta_df.empty else {}
        
    with col_u2:
        def super_clean(text):
            return re.sub(r'[\s\-_/]+', '', str(text)).upper()
            
        safe_selected_unit = super_clean(selected_unit)
        db_client_name = ""
        
        name_col_idx = 0 
        for i, col in enumerate(df_clients.columns):
            if 'NAME' in str(col).upper() or 'CLIENT' in str(col).upper():
                name_col_idx = i
                break
                
        for row_idx in range(len(df_clients)):
            row = df_clients.iloc[row_idx]
            cleaned_cells = [super_clean(cell) for cell in row]
            
            if safe_selected_unit in cleaned_cells:
                raw_name = row.iloc[name_col_idx]
                
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
    # BRANCH A: DATABASE CATALOG WORKFLOW (ROOF ROOM ONLY)
    # -----------------------------------------------------------
    if selected_request_type == "Roof Room":
        prod_area_col = next((c for c in df_products.columns if 'AREA' in c.upper()), df_products.columns[5])
        desc_col_text = next((c for c in df_products.columns if 'DESCRIPTION' in c.upper()), df_products.columns[6])
        cat_col = next((c for c in df_products.columns if 'CATEGORY' in c.upper()), df_products.columns[1])
        
        target_unit_type = str(unit_type).strip().upper()
        target_design_type = str(unit_design_type).strip().upper()
        target_design_opt = str(unit_design_opt).strip().upper()
        
        filtered_catalog = df_products.copy()
        
        # Filtering logic...
        prod_unit_type_col = next((c for c in df_products.columns if 'UNIT TYPE' in c.upper()), df_products.columns[2])
        design_type_col = next((c for c in df_products.columns if 'DESIGN TYPE' in c.upper()), df_products.columns[3])
        prod_opt_link_col = next((c for c in df_products.columns if 'OPTION LINK' in c.upper() or 'DESIGN OPTION' in c.upper()), df_products.columns[4])
        
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

        # UI Layout for Roof Room
        col_vr, col_fin = st.columns([2, 1])
        
        with col_vr:
            def format_scope(idx):
                row = filtered_catalog.loc[idx]
                return f"{row[prod_area_col]} sqm - {row[desc_col_text]}"
                
            chosen_idx = st.selectbox("Select Roof Room Variant", filtered_catalog.index, format_func=format_scope)
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
        
        custom_roof_description = f'Required Fees for adding {target_item_qty} m2 Roof Room as per attached Drawings " Core and Shell "'
        
        # Save exact format needed for PDF and Webhook
        st.session_state.staged_items = [{
            'No.': 1,
            'Description': custom_roof_description,
            'Unit': 'LS',
            'QTY': 1.0,
            'Rate': calculated_line_item_total,
            'Total Amount': calculated_line_item_total,
            'Financing Options': chosen_term_option # Hidden from table but kept for terms generator
        }]
        
        # Render BOQ Table for Roof Room
        st.markdown("### 📊 Generated BOQ Summary")
        summary_df = pd.DataFrame([{k: v for k, v in st.session_state.staged_items[0].items() if k != 'Financing Options'}])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        
        subtotal = calculated_line_item_total
        vat = subtotal * 0.14
        total_with_vat = subtotal + vat

        col_t1, col_t2 = st.columns(2)
        col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
        col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

    # -----------------------------------------------------------
    # BRANCH B: DYNAMIC DATA EDITOR WORKFLOW (ALL OTHER TYPES)
    # -----------------------------------------------------------
    else:
        st.markdown(f"### 📝 Custom BOQ Entry Table: {selected_request_type}")
        st.info("💡 **Tip:** Type smoothly in the center! The read-only preview tables on the left and right calculate your 'No.' and 'Total Amount' instantly.")
        
        # Isolate the editable table data perfectly to prevent refresh loop deletion
        if 'custom_boq_data' not in st.session_state or st.session_state.get('last_type') != selected_request_type:
            # --- SPECIAL HANDLING FOR LAND EXTENSION ---
            if selected_request_type == "Land Extension":
                initial_data = [{
                    'Description': 'Required Fees for Adding land extension area of for a/m unit as per attached Drawings.',
                    'Unit': 'M2',
                    'QTY': 0.0,  # User types the actual area here
                    'Rate': 55000.0  # Fixed standard rate
                }]
            else:
                initial_data = [{
                    'Description': '',
                    'Unit': 'LS',
                    'QTY': 1.0,
                    'Rate': 0.0
                }]
            
            st.session_state.custom_boq_data = pd.DataFrame(initial_data)
            st.session_state.last_type = selected_request_type
        
        # Split layout to show No. Preview, Editor, and Total Preview side-by-side
        col_no, col_editor, col_total = st.columns([0.4, 3.5, 1.1])
        
        with col_editor:
            # Interactive grid with ONLY the editable columns to ensure 100% stable input
            edited_df = st.data_editor(
                st.session_state.custom_boq_data,
                key="custom_boq_editor",
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Description": st.column_config.TextColumn("Description"),
                    "Unit": st.column_config.SelectboxColumn("Unit", options=["SQM", "M2", "LM", "NO.", "LS", "Other"], default="LS"),
                    "QTY": st.column_config.NumberColumn("QTY", min_value=0.0, default=1.0),
                    "Rate": st.column_config.NumberColumn("Rate", min_value=0.0, default=0.0)
                }
            )
        
        # Safely compute Totals downstream into a completely separate dataframe for exporting
        final_df = edited_df.copy()
        final_df['QTY'] = pd.to_numeric(final_df['QTY'], errors='coerce').fillna(0.0)
        final_df['Rate'] = pd.to_numeric(final_df['Rate'], errors='coerce').fillna(0.0)
        final_df['Total Amount'] = final_df['QTY'] * final_df['Rate']
        final_df.insert(0, 'No.', range(1, len(final_df) + 1))
        
        with col_no:
            # Display read-only No. calculation on the left side of the editor
            st.dataframe(
                final_df[['No.']],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "No.": st.column_config.NumberColumn("No.")
                }
            )

        with col_total:
            # Display read-only calculation next to the right side of the editor
            st.dataframe(
                final_df[['Total Amount']],
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Total Amount": st.column_config.NumberColumn("Total Amount", format="%.2f EGP")
                }
            )
        
        # Sync to the overarching staged items system for Webhook and PDF building
        st.session_state.staged_items = final_df.to_dict('records')
        summary_df = final_df
        
        # Calculate Subtotal & VAT for custom grid
        subtotal = final_df['Total Amount'].sum()
        vat = subtotal * 0.14
        total_with_vat = subtotal + vat
        
        if selected_request_type == "Land Extension":
            st.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
        else:
            col_t1, col_t2 = st.columns(2)
            col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

    st.divider()

    # --- SECTION 3: EXPORT BUTTONS (SHARED) ---
    if st.session_state.staged_items and not summary_df.empty:
        final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
        
        st.markdown("##### Finalize Document Details")
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
                            "description": item.get("Description", ""),
                            "unit": item.get("Unit", "LS"),
                            "qty": item.get("QTY", 1.0),
                            "rate": item.get("Rate", 0.0)
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
            
            # Simple 6-column PDF Header
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(10, 8, "No.", border=1, align="C")
            pdf.cell(90, 8, "Description", border=1)
            pdf.cell(15, 8, "Unit", border=1, align="C")
            pdf.cell(15, 8, "QTY", border=1, align="C")
            pdf.cell(30, 8, "Rate", border=1, align="C")
            pdf.cell(30, 8, "Total", border=1, align="C", ln=True)
            
            pdf.set_font("Helvetica", "", 9)
            for _, item_row in summary_df.iterrows():
                pdf.cell(10, 8, str(item_row.get('No.', '')), border=1, align="C")
                pdf.cell(90, 8, str(item_row.get('Description', ''))[:45], border=1)
                pdf.cell(15, 8, str(item_row.get('Unit', '')), border=1, align="C")
                pdf.cell(15, 8, str(item_row.get('QTY', '')), border=1, align="C")
                pdf.cell(30, 8, f"{item_row.get('Rate', 0):,.2f}", border=1, align="R")
                pdf.cell(30, 8, f"{item_row.get('Total Amount', 0):,.2f}", border=1, align="R", ln=True)
                
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 8, f"Total Value: {subtotal:,.2f} EGP", ln=True)
            
            if selected_request_type != "Land Extension":
                pdf.cell(0, 8, f"Total Value (Including 14% VAT): {total_with_vat:,.2f} EGP", ln=True)
                
            pdf.ln(4)
            
            # Terms and Conditions (Only pulls if Financing Options exists on Roof Room)
            if 'Financing Options' in st.session_state.staged_items[0]:
                pdf.set_font("Helvetica", "B", 11)
                pdf.cell(0, 8, "Legal Framework & Strategic Project Adjustments:", ln=True)
                pdf.set_font("Helvetica", "", 8)
                
                terms_opt_col = df_terms.columns[1] if len(df_terms.columns) > 1 else df_terms.columns[0]
                terms_text_col = df_terms.columns[2] if len(df_terms.columns) > 2 else df_terms.columns[-1]
                
                rule_term = st.session_state.staged_items[0].get('Financing Options')
                matched_legal_text_blocks = df_terms[df_terms[terms_opt_col] == rule_term][terms_text_col].values
                if len(matched_legal_text_blocks) > 0:
                    pdf.multi_cell(0, 4, str(matched_legal_text_blocks[0]))
                    pdf.ln(2)
            
            # Safe PDF Export (Prevents AttributeError entirely)
            try:
                pdf_out = pdf.output(dest="S")
                # Depending on fpdf library version, it returns a string or a bytearray
                if isinstance(pdf_out, str):
                    compiled_pdf_payload = pdf_out.encode("latin-1", errors="ignore")
                else:
                    compiled_pdf_payload = bytes(pdf_out)
            except AttributeError:
                # Absolute fallback if encode fails due to bytearray attribute error
                compiled_pdf_payload = bytes(pdf.output(dest="S"))
            
            st.download_button(
                label="📄 Download Quick PDF Preview",
                data=compiled_pdf_payload,
                file_name=f"O_West_Proposal_{final_client_name.replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
else:
    st.info("Awaiting structural backend database connection strings...")
