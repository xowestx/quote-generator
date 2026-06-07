import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import re
import requests
import json
import base64
import io
import time

# Import PDF Merger
try:
    from pypdf import PdfWriter
    has_pypdf = True
except ImportError:
    has_pypdf = False

# ==========================================
# 1. CORE DATA LOADING ENGINE (GOOGLE SHEETS)
# ==========================================
GSHEET_URL = "https://docs.google.com/spreadsheets/d/1uyZXYMvaeuH-ZQOxHgpdyXiC2vlvUHtK3Cmde63cnUY/edit?usp=sharing"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzzt5KDoxG9DbYPXzFe7HiYJ6WgYdpsYE65p7Zuwnq6PycZdvbtGyCe_8G1OwwM3cxP/exec"

@st.cache_data(ttl=60)
def load_all_tabs(base_url):
    try:
        sheet_id = base_url.split("/d/")[1].split("/")[0]
        
        def get_csv(sheet_name):
            url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
            return pd.read_csv(url)
            
        facts = get_csv("FACT")
        products = get_csv("PRODUCTS")
        rates = get_csv("RATES")
        terms = get_csv("TERMS_%26_CONDITIONS")
        
        clients = get_csv("CLIENT_NAME")
        if not any('NAME' in str(c).upper() or 'CLIENT' in str(c).upper() for c in clients.columns):
            clients = get_csv("CLIENT%20NAME")
        
        for df in [facts, products, rates, clients, terms]:
            df.columns = [str(c).strip() for c in df.columns]
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

if 'doc_url' not in st.session_state:
    st.session_state.doc_url = None
if 'pdf_url' not in st.session_state:
    st.session_state.pdf_url = None

if st.sidebar.button("🔄 Hard Reset & Fetch Latest Data"):
    st.cache_data.clear()
    st.session_state.doc_url = None
    st.session_state.pdf_url = None
    st.rerun()

st.title("🏗️ Extra Works Quotation Engine")

df_fact, df_products, df_rates, df_clients, df_terms = load_all_tabs(GSHEET_URL)

if 'staged_items' not in st.session_state:
    st.session_state.staged_items = []

if st.session_state.staged_items and 'Calculated_Price' in st.session_state.staged_items[0]:
    st.session_state.staged_items = []

if df_fact is not None and not df_fact.empty:
    
    fact_unit_id_col = next((c for c in df_fact.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), df_fact.columns[0])
    client_unit_col = next((c for c in df_clients.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), df_clients.columns[-1] if not df_clients.empty else None)
    
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        if client_unit_col:
            valid_units = [u for u in df_clients[client_unit_col].unique() if str(u).strip() and str(u).strip().upper() not in ['NAN', 'NONE']]
        else:
            valid_units = df_fact[fact_unit_id_col].unique()
        
        valid_units = sorted(list(set(valid_units)), key=lambda x: str(x))
        selected_unit = st.selectbox("Select Unit ID", valid_units)
        
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

    st.subheader("2. Define Engineering Scope")
    
    request_options = [
        "Roof Room", "Pool Standard", "Pool Customized", "Interior Standard Package", 
        "Interior Customized Package", "Interior Modification", "Kitchen", "Closets", 
        "Landscape", "Furniture", "Closing Double Height", "Land Extension", 
        "Exterior Painting", "Glass House", "Elevator", "A.C", "Shutters", 
        "Fence & Gates", "Pergola", "Landscape Modifications", "SOG", "Closing Elevator Shaft"
    ]
    
    selected_request_type = st.selectbox("Select Official Request Type", request_options)
    if st.session_state.get('last_master_request') != selected_request_type:
        st.session_state.staged_items = []
        st.session_state.last_master_request = selected_request_type

    if selected_request_type == "Roof Room":
        prod_area_col = next((c for c in df_products.columns if 'AREA' in c.upper()), df_products.columns[5])
        desc_col_text = next((c for c in df_products.columns if 'DESCRIPTION' in c.upper()), df_products.columns[6])
        cat_col = next((c for c in df_products.columns if 'CATEGORY' in c.upper()), df_products.columns[1])
        
        target_unit_type = str(unit_type).strip().upper()
        target_design_type = str(unit_design_type).strip().upper()
        target_design_opt = str(unit_design_opt).strip().upper()
        
        filtered_catalog = df_products.copy()
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
                
        if filtered_catalog.empty: filtered_catalog = df_products

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
            if category_rates.empty: category_rates = df_rates
            rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
            rate_val_col = df_rates.columns[1]
            chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates[rate_opt_col].unique())
            rate_record = category_rates[category_rates[rate_opt_col] == chosen_term_option].iloc[0]

        try: target_item_qty = float(product_record[prod_area_col])
        except: target_item_qty = 0.0
            
        try:
            rate_val = str(rate_record[rate_val_col]).replace(',', '').replace('$', '').strip()
            unit_base_cost_rate = float(rate_val)
        except: unit_base_cost_rate = 0.0
            
        calculated_line_item_total = target_item_qty * unit_base_cost_rate
        formatted_qty = int(target_item_qty) if target_item_qty.is_integer() else target_item_qty
        custom_roof_description = f'Required Fees for adding {formatted_qty} m2 Roof Room as per attached Drawings " Core and Shell "'
        
        financing_name_suffix = " - 6 months" if "6" in str(chosen_term_option) else " - 24 months" if "24" in str(chosen_term_option) else " - 2 Years"
        resolved_request_name = "Roof Room" + financing_name_suffix
        
        st.session_state.staged_items = [{
            'No.': 1, 'Description': custom_roof_description, 'Unit': 'LS', 'QTY': 1.0, 
            'Rate': calculated_line_item_total, 'Total Amount': calculated_line_item_total,
            'Financing Options': chosen_term_option, 'Lookup Name': resolved_request_name
        }]
        
        st.markdown("### 📊 Generated BOQ Summary")
        summary_df = pd.DataFrame([{k: v for k, v in st.session_state.staged_items[0].items() if k not in ['Financing Options', 'Lookup Name']}])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)
        
        subtotal = calculated_line_item_total
        vat = subtotal * 0.14
        total_with_vat = subtotal + vat

        col_t1, col_t2 = st.columns(2)
        col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
        col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

    elif selected_request_type == "Furniture":
        st.markdown("### 🛋️ Furniture Package Generator")
        st.info("💡 **Rule Engine:** Select inputs below. The system automatically allocates rooms and applies Master/Kids split logic.")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1: fur_unit_type = st.selectbox("Unit Typology", ["1 Bedroom", "2 Bedrooms", "3 Bedrooms", "3 Bedrooms+N", "3 Bedrooms+N+F", "4 Bedrooms+N"])
        with col_f2: fur_package = st.selectbox("Furniture Package", ["Luxury [L]", "Deluxe [D]", "Rent [R]"])
        with col_f3: fur_outdoors = st.selectbox("Include Outdoors?", ["Yes", "No"])
            
        def get_fur_rate(keyword, pkg_code):
            if "NANNY" in keyword:
                match = df_rates[df_rates.iloc[:,0].astype(str).str.upper().str.contains("NANNY", na=False)]
                if not match.empty: return float(str(match.iloc[0, 1]).replace(',', '').replace('$', '').strip())
                return 31914.96
            match = df_rates[(df_rates.iloc[:,0].astype(str).str.upper().str.contains(keyword, na=False)) & (df_rates.iloc[:,2].astype(str).str.strip().str.upper() == pkg_code)]
            if not match.empty: return float(str(match.iloc[0, 1]).replace(',', '').replace('$', '').strip())
            fallbacks = {
                "RECEPTION_L": 225193.10, "RECEPTION_D": 168894.83, "RECEPTION_R": 126671.12,
                "LIVING_L": 204958.27, "LIVING_D": 153718.70, "LIVING_R": 115289.03,
                "DINING_L": 245996.63, "DINING_D": 184497.47, "DINING_R": 138373.10,
                "MASTER BEDROOM_L": 230736.11, "MASTER BEDROOM_D": 173052.08, "MASTER BEDROOM_R": 129789.06,
                "KIDS BEDROOM_L": 199236.18, "KIDS BEDROOM_D": 149427.14, "KIDS BEDROOM_R": 112070.35,
                "TERRACE_L": 31262.77, "TERRACE_D": 12829.63, "TERRACE_R": 9803.42,
                "OUTDOORS_L": 64153.21, "OUTDOORS_D": 48114.91, "OUTDOORS_R": 36086.18
            }
            return fallbacks.get(f"{keyword}_{pkg_code}", 0.0)

        if st.button("➕ Generate Furniture Package BOQ", type="primary", use_container_width=True):
            pkg_code = "L" if "Luxury" in fur_package else "D" if "Deluxe" in fur_package else "R"
            rooms_to_add = []
            
            rooms_to_add.append({"desc": "Reception", "qty": 1.0, "rate": get_fur_rate("RECEPTION", pkg_code)})
            rooms_to_add.append({"desc": "Dining Room", "qty": 1.0, "rate": get_fur_rate("DINING", pkg_code)})
            rooms_to_add.append({"desc": "Terrace", "qty": 1.0, "rate": get_fur_rate("TERRACE", pkg_code)})
            
            if fur_outdoors == "Yes": rooms_to_add.append({"desc": "Outdoors", "qty": 1.0, "rate": get_fur_rate("OUTDOORS", pkg_code)})
            if "+N" in fur_unit_type: rooms_to_add.append({"desc": "Nanny's Room", "qty": 1.0, "rate": get_fur_rate("NANNY", pkg_code)})
            if "+F" in fur_unit_type: rooms_to_add.append({"desc": "Living Room", "qty": 1.0, "rate": get_fur_rate("LIVING", pkg_code)})
                
            num_beds = int(fur_unit_type[0])
            rooms_to_add.append({"desc": "Master Bedroom", "qty": 1.0, "rate": get_fur_rate("MASTER BEDROOM", pkg_code)})
            if num_beds > 1: rooms_to_add.append({"desc": "Kids Bedroom", "qty": float(num_beds - 1), "rate": get_fur_rate("KIDS BEDROOM", pkg_code)})
                
            outdoor_text = ", + Outdoor" if fur_outdoors == "Yes" else ""
            fur_request_name = f"{fur_unit_type}, {fur_package}{outdoor_text}"

            new_staged = []
            for idx, r in enumerate(rooms_to_add):
                total = r["qty"] * r["rate"]
                full_desc = f"Supply and install Furniture for {r['desc']} as per attached design."
                new_staged.append({
                    'No.': idx + 1, 'Description': full_desc, 'Unit': 'LS', 'QTY': r["qty"], 'Rate': r["rate"],
                    'Total Amount': total, 'Lookup Name': fur_request_name
                })
            
            st.session_state.staged_items = new_staged
            st.toast("Furniture package generated successfully!")

        if st.session_state.staged_items:
            st.markdown("### 📊 Generated BOQ Summary")
            summary_df = pd.DataFrame([{k: v for k, v in item.items() if k != 'Lookup Name'} for item in st.session_state.staged_items])
            st.dataframe(summary_df, use_container_width=True, hide_index=True)
            
            subtotal = summary_df['Total Amount'].sum()
            vat = subtotal * 0.14
            total_with_vat = subtotal + vat

            col_t1, col_t2 = st.columns(2)
            col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")
            
            if st.button("❌ Clear Furniture Package", type="secondary"):
                st.session_state.staged_items = []
                st.rerun()

            # ==========================================
            # 🚀 BULK EXPORT ENGINE (ALL 36 PACKAGES)
            # ==========================================
            st.markdown("---")
            st.markdown("### 🚀 Bulk Export Engine")
            st.warning("⚠️ **Warning:** Generating all 36 PDFs involves heavy processing and API calls. This process will take a few minutes. Please do not close the window while the progress bar is running.")
            
            if st.button("🔥 Generate & Export All 36 Options (One-Click)", type="primary", use_container_width=True):
                if not has_pypdf:
                    st.error("🚨 Critical Error: You MUST add 'pypdf' to your GitHub requirements.txt file to combine Furniture PDFs!")
                    st.stop()
                    
                # Define iteration matrices
                typologies = ["1 Bedroom", "2 Bedrooms", "3 Bedrooms", "3 Bedrooms+N", "3 Bedrooms+N+F", "4 Bedrooms+N"]
                packages = ["Luxury [L]", "Deluxe [D]", "Rent [R]"]
                outdoors = ["Yes", "No"]
                total_iters = len(typologies) * len(packages) * len(outdoors)
                
                # UI Feedback setup
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
                headers = {"Content-Type": "application/json"}
                success_count = 0
                current_iter = 0
                
                for t in typologies:
                    for p in packages:
                        for o in outdoors:
                            current_iter += 1
                            
                            # 1. Resolve Package Codes & Variables
                            pkg_code_letter = "L" if "Luxury" in p else "D" if "Deluxe" in p else "R"
                            payload_pkg_code = "P1" if pkg_code_letter == "L" else "P2" if pkg_code_letter == "D" else "P3"
                            
                            outdoor_text = ", + Outdoor" if o == "Yes" else ""
                            fur_request_name = f"{t}, {p}{outdoor_text}"
                            status_text.text(f"⚙️ Compiling {current_iter}/{total_iters}: {fur_request_name}...")
                            
                            # 2. Build Automated BOQ for this specific combination
                            rooms_to_add = [
                                {"desc": "Reception", "qty": 1.0, "rate": get_fur_rate("RECEPTION", pkg_code_letter)},
                                {"desc": "Dining Room", "qty": 1.0, "rate": get_fur_rate("DINING", pkg_code_letter)},
                                {"desc": "Terrace", "qty": 1.0, "rate": get_fur_rate("TERRACE", pkg_code_letter)}
                            ]
                            if o == "Yes": rooms_to_add.append({"desc": "Outdoors", "qty": 1.0, "rate": get_fur_rate("OUTDOORS", pkg_code_letter)})
                            if "+N" in t: rooms_to_add.append({"desc": "Nanny's Room", "qty": 1.0, "rate": get_fur_rate("NANNY", pkg_code_letter)})
                            if "+F" in t: rooms_to_add.append({"desc": "Living Room", "qty": 1.0, "rate": get_fur_rate("LIVING", pkg_code_letter)})
                            
                            num_beds = int(t[0])
                            rooms_to_add.append({"desc": "Master Bedroom", "qty": 1.0, "rate": get_fur_rate("MASTER BEDROOM", pkg_code_letter)})
                            if num_beds > 1: rooms_to_add.append({"desc": "Kids Bedroom", "qty": float(num_beds - 1), "rate": get_fur_rate("KIDS BEDROOM", pkg_code_letter)})
                            
                            staged_items_payload = []
                            for r in rooms_to_add:
                                staged_items_payload.append({
                                    "description": f"Supply and install Furniture for {r['desc']} as per attached design.",
                                    "unit": "LS", "qty": r["qty"], "rate": r["rate"]
                                })
                                
                            # 3. Trigger Webhook (Doc Generation)
                            payload = {
                                "action": "generateDocOnly",
                                "packageCode": payload_pkg_code,
                                "unitId": selected_unit,
                                "clientName": final_client_name,
                                "zone": str(zone_name),
                                "requestType": fur_request_name,
                                "items": staged_items_payload
                            }
                            
                            try:
                                res = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                                res_data = res.json()
                                
                                if res_data.get("status") == "success":
                                    # 4. PyPDF Merge inside memory
                                    merger = PdfWriter()
                                    merger.append(io.BytesIO(base64.b64decode(res_data["docBase64"])))
                                    
                                    for room_b64 in res_data.get("roomBase64s", []):
                                        try:
                                            merger.append(io.BytesIO(base64.b64decode(room_b64)))
                                        except Exception:
                                            pass
                                            
                                    output_pdf = io.BytesIO()
                                    merger.write(output_pdf)
                                    
                                    # 5. Trigger Webhook (Upload Final Merged PDF)
                                    up_payload = {
                                        "action": "uploadPdf",
                                        "docName": res_data["docName"],
                                        "base64Pdf": base64.b64encode(output_pdf.getvalue()).decode('utf-8'),
                                        "serialNumber": res_data["serialNumber"],
                                        "unitId": selected_unit,
                                        "clientName": final_client_name,
                                        "requestType": fur_request_name,
                                        "grandTotal": res_data["grandTotal"],
                                        "zone": str(zone_name)
                                    }
                                    
                                    up_res = requests.post(WEBHOOK_URL, data=json.dumps(up_payload), headers=headers)
                                    if up_res.json().get("status") == "success":
                                        success_count += 1
                                        
                            except Exception as e:
                                st.toast(f"Error on {fur_request_name}: {e}", icon="🚨")
                                
                            # Update Progress Bar and throttle to protect API limits
                            progress_bar.progress(current_iter / total_iters)
                            time.sleep(1) # Protects Google Workspace from Rate Limiting
                            
                # Final Completion Status
                if success_count == total_iters:
                    status_text.success(f"✅ SUCCESS! All {success_count} packages compiled and synced to Google Workspace.")
                else:
                    status_text.warning(f"⚠️ Process finished. {success_count} out of {total_iters} succeeded. Check your workspace.")

    else:
        st.markdown(f"### 📝 Custom BOQ Entry Table: {selected_request_type}")
        st.info("💡 **Tip:** Type smoothly in the center! The read-only previews calculate No., Unit, Rate, and Total instantly.")
        
        if 'custom_boq_data' not in st.session_state or st.session_state.get('last_type') != selected_request_type:
            if selected_request_type == "Land Extension":
                initial_data = [{'Description': 'Required Fees for Adding land extension area of for a/m unit as per attached Drawings.', 'Unit': 'M2', 'QTY': 0.0, 'Rate': 55000.0}]
            elif selected_request_type == "Pergola":
                initial_data = [{'Type': 'Musky', 'Description': 'Supply & Install Musky Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture.', 'Area / QTY (NO.)': 10.0, 'prev_Type': 'Musky'}]
            else:
                initial_data = [{'Description': '', 'Unit': 'LS', 'QTY': 1.0, 'Rate': 0.0}]
            st.session_state.custom_boq_data = pd.DataFrame(initial_data)
            st.session_state.last_type = selected_request_type
        
        if selected_request_type == "Pergola":
            col_no, col_editor, col_total = st.columns([0.4, 3.5, 1.1])
            if 'prev_Type' not in st.session_state.custom_boq_data.columns: st.session_state.custom_boq_data['prev_Type'] = st.session_state.custom_boq_data['Type']
                
            with col_editor:
                edited_df = st.data_editor(
                    st.session_state.custom_boq_data, key="custom_boq_editor", num_rows="dynamic", use_container_width=True, hide_index=True,
                    column_order=["Type", "Description", "Area / QTY (NO.)"],
                    column_config={"Type": st.column_config.SelectboxColumn("Type", options=["Musky", "Pitch Pine", "Khashamonium", "Retractable"], default="Musky"), "Description": st.column_config.TextColumn("Description"), "Area / QTY (NO.)": st.column_config.NumberColumn("Area / QTY (NO.)", min_value=0.0, default=10.0)}
                )
                
            PERGOLA_RULES = {
                "Musky": {"rate": 4320.0, "desc": 'Supply & Install Musky Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture.'},
                "Pitch Pine": {"rate": 7080.0, "desc": 'Supply & Install Pitch pine Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture.'},
                "Khashamonium": {"rate": 11200.0, "desc": 'Supply & Install Khashamonium Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture.'},
                "Retractable": {"rate": 67500.0, "desc": 'Supply and install a landscape retractable pergola as per attached drawings including Motor and Fabric.'}
            }
            
            final_rows = []
            has_changes = False
            if 'prev_Type' not in edited_df.columns: edited_df['prev_Type'] = edited_df['Type'].fillna('Musky')

            for idx, row in edited_df.iterrows():
                p_type = row.get("Type", "Musky")
                prev_type = row.get("prev_Type", "")
                current_desc = str(row.get("Description", "")).strip()
                
                if pd.isna(prev_type) or p_type != prev_type:
                    resolved_desc = PERGOLA_RULES[p_type]["desc"]
                    edited_df.at[idx, "Description"] = resolved_desc
                    edited_df.at[idx, "prev_Type"] = p_type
                    if p_type == "Retractable": edited_df.at[idx, "Area / QTY (NO.)"] = 1.0
                    else: edited_df.at[idx, "Area / QTY (NO.)"] = 10.0
                    has_changes = True
                else: resolved_desc = current_desc
                
                qty_input = float(row.get("Area / QTY (NO.)", 10.0))
                
                if p_type == "Retractable":
                    unit = "Item"
                    qty = int(qty_input) if qty_input > 0 else 1
                    rate = 67500.0
                    total = qty * rate
                else:
                    base_rate = PERGOLA_RULES[p_type]["rate"]
                    if qty_input < 10.0: unit, qty, rate, total = "LS", 1.0, 10.0 * base_rate, 10.0 * base_rate
                    else: unit, qty, rate, total = "SQM", qty_input, base_rate, qty_input * base_rate
                        
                final_rows.append({'No.': idx + 1, 'Type': p_type, 'Description': resolved_desc, 'Area / QTY (NO.)': qty_input, 'Unit': unit, 'QTY': qty, 'Rate': rate, 'Total Amount': total, 'prev_Type': p_type})
                
            if has_changes:
                st.session_state.custom_boq_data = edited_df
                st.rerun()
            else:
                st.session_state.custom_boq_data = edited_df
                
            final_df = pd.DataFrame(final_rows)
            with col_no: st.dataframe(final_df[['No.']], hide_index=True, use_container_width=True)
            with col_total: st.dataframe(final_df[['Unit', 'Rate', 'Total Amount']], hide_index=True, use_container_width=True, column_config={"Rate": st.column_config.NumberColumn("Rate", format="%.2f EGP"), "Total Amount": st.column_config.NumberColumn("Total", format="%.2f EGP")})

        else:
            col_no, col_editor, col_total = st.columns([0.4, 3.5, 1.1])
            with col_editor:
                edited_df = st.data_editor(
                    st.session_state.custom_boq_data, key="custom_boq_editor", num_rows="dynamic", use_container_width=True, hide_index=True,
                    column_config={"Description": st.column_config.TextColumn("Description"), "Unit": st.column_config.SelectboxColumn("Unit", options=["SQM", "M2", "LM", "NO.", "LS", "Other"], default="LS"), "QTY": st.column_config.NumberColumn("QTY", min_value=0.0, default=1.0), "Rate": st.column_config.NumberColumn("Rate", min_value=0.0, default=0.0)}
                )
            
            final_df = edited_df.copy()
            final_df['QTY'] = pd.to_numeric(final_df['QTY'], errors='coerce').fillna(0.0)
            final_df['Rate'] = pd.to_numeric(final_df['Rate'], errors='coerce').fillna(0.0)
            final_df['Total Amount'] = final_df['QTY'] * final_df['Rate']
            final_df.insert(0, 'No.', range(1, len(final_df) + 1))
            
            with col_no: st.dataframe(final_df[['No.']], hide_index=True, use_container_width=True)
            with col_total: st.dataframe(final_df[['Total Amount']], hide_index=True, use_container_width=True, column_config={"Total Amount": st.column_config.NumberColumn("Total Amount", format="%.2f EGP")})

        st.session_state.staged_items = final_df.to_dict('records')
        summary_df = final_df
        
        subtotal = final_df['Total Amount'].sum()
        vat = subtotal * 0.14
        total_with_vat = subtotal + vat
        
        col_t1, col_t2 = st.columns(2)
        if selected_request_type == "Land Extension": col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
        else:
            col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

    st.divider()

    # --- SECTION 4: EXPORT BUTTONS (SHARED) ---
    if st.session_state.staged_items:
        summary_df = pd.DataFrame(st.session_state.staged_items)
        if not summary_df.empty:
            final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
            st.markdown("##### Finalize Document Details")
            col_export1, col_export2 = st.columns(2)
            
            with col_export1:
                if st.button("🌐 Generate Official Google Doc via Webhook", use_container_width=True, type="primary"):
                    with st.spinner("Transmitting to Google Workspace..."):
                        
                        resolved_req_name = selected_request_type
                        if selected_request_type in ["Roof Room", "Furniture"] and 'Lookup Name' in st.session_state.staged_items[0]:
                            resolved_req_name = st.session_state.staged_items[0]['Lookup Name']

                        payload = {
                            "action": "standard",
                            "unitId": selected_unit,
                            "clientName": final_client_name,
                            "zone": str(zone_name),
                            "requestType": resolved_req_name, 
                            "items": []
                        }
                        
                        for item in st.session_state.staged_items:
                            payload["items"].append({
                                "description": item.get("Description", ""),
                                "unit": item.get("Unit", "LS"),
                                "qty": item.get("QTY", 1.0),
                                "rate": item.get("Rate", 0.0)
                            })
                            
                        # Set up two-way PDF merger specifically for Furniture
                        if selected_request_type == "Furniture":
                            if not has_pypdf:
                                st.error("🚨 Critical Error: You MUST add 'pypdf' to your GitHub requirements.txt file to combine Furniture PDFs!")
                            else:
                                payload["action"] = "generateDocOnly"
                                fur_package_name = st.session_state.staged_items[0].get('Lookup Name', '')
                                if "[L]" in fur_package_name: pkg_code = "P1"
                                elif "[D]" in fur_package_name: pkg_code = "P2"
                                elif "[R]" in fur_package_name: pkg_code = "P3"
                                else: pkg_code = "P1"
                                payload["packageCode"] = pkg_code
                                
                        try:
                            headers = {"Content-Type": "application/json"}
                            response = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                            
                            if response.status_code == 200:
                                response_data = response.json()
                                
                                # Process standard quote
                                if response_data.get("status") == "success" and selected_request_type != "Furniture":
                                    st.success("✅ Quotation Generated Successfully!")
                                    st.session_state.doc_url = response_data.get('docUrl')
                                    st.session_state.pdf_url = response_data.get('pdfUrl')
                                    st.rerun()
                                    
                                # Process advanced 2-way Furniture PDF merge
                                elif response_data.get("status") == "success" and selected_request_type == "Furniture":
                                    st.toast("Compiling Room Designs. This may take 10-15 seconds...")
                                    
                                    merger = PdfWriter()
                                    
                                    # Base64 decode main doc
                                    main_pdf_bytes = base64.b64decode(response_data["docBase64"])
                                    merger.append(io.BytesIO(main_pdf_bytes))
                                    
                                    # Base64 decode and append all room docs
                                    for room_b64 in response_data.get("roomBase64s", []):
                                        room_bytes = base64.b64decode(room_b64)
                                        try:
                                            merger.append(io.BytesIO(room_bytes))
                                        except Exception: pass
                                            
                                    output_pdf = io.BytesIO()
                                    merger.write(output_pdf)
                                    merged_bytes = output_pdf.getvalue()
                                    
                                    # Upload final PDF back to Drive
                                    upload_payload = {
                                        "action": "uploadPdf",
                                        "docName": response_data["docName"],
                                        "base64Pdf": base64.b64encode(merged_bytes).decode('utf-8'),
                                        "serialNumber": response_data["serialNumber"],
                                        "unitId": selected_unit,
                                        "clientName": final_client_name,
                                        "requestType": resolved_req_name,
                                        "grandTotal": response_data["grandTotal"],
                                        "zone": str(zone_name)
                                    }
                                    
                                    up_res = requests.post(WEBHOOK_URL, data=json.dumps(upload_payload), headers=headers)
                                    up_data = up_res.json()
                                    
                                    if up_data.get("status") == "success":
                                        st.success("✅ Quotation and Room Designs Compiled Successfully!")
                                        st.session_state.doc_url = response_data['docUrl']
                                        st.session_state.pdf_url = up_data['pdfUrl']
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to save final PDF: {up_data.get('message')}")
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
                
                disp_req_name = selected_request_type
                if selected_request_type in ["Roof Room", "Furniture"] and 'Lookup Name' in st.session_state.staged_items[0]:
                    disp_req_name = st.session_state.staged_items[0]['Lookup Name']
                pdf.cell(0, 10, f"Request Type: {disp_req_name}", ln=True)
                pdf.ln(8)
                
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
                
                subtotal = summary_df['Total Amount'].sum()
                vat = subtotal * 0.14
                total_with_vat = subtotal + vat
                
                if selected_request_type == "Land Extension":
                    pdf.cell(0, 8, f"Total Value: {subtotal:,.2f} EGP", ln=True)
                else:
                    pdf.cell(0, 8, f"Total Value: {subtotal:,.2f} EGP", ln=True)
                    pdf.cell(0, 8, f"Total Value (Including 14% VAT): {total_with_vat:,.2f} EGP", ln=True)
                pdf.ln(4)
                
                if 'Financing Options' in st.session_state.staged_items[0] and selected_request_type == "Roof Room":
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(0, 8, "Legal Framework & Strategic Project Adjustments:", ln=True)
                    pdf.set_font("Helvetica", "", 8)
                    
                    terms_opt_col = df_terms.columns[1] if len(df_terms.columns) > 1 else df_terms.columns[0]
                    terms_text_col = df_terms.columns[2] if len(df_terms.columns) > 2 else df_terms.columns[-1]
                    
                    rule_term = st.session_state.staged_items[0].get('Financing Options')
                    lookup_request_name = st.session_state.staged_items[0].get('Lookup Name', 'Roof Room')
                    
                    matched_legal_text_blocks = df_terms[
                        (df_terms[terms_opt_col] == rule_term) & 
                        (df_terms[df_terms.columns[0]].str.upper() == lookup_request_name.upper())
                    ][terms_text_col].values
                    
                    if len(matched_legal_text_blocks) > 0:
                        pdf.multi_cell(0, 4, str(matched_legal_text_blocks[0]))
                    else:
                        matched_fallback = df_terms[df_terms[terms_opt_col] == rule_term][terms_text_col].values
                        if len(matched_fallback) > 0:
                            pdf.multi_cell(0, 4, str(matched_fallback[0]))
                    pdf.ln(2)
                
                try:
                    pdf_out = pdf.output(dest="S")
                    if isinstance(pdf_out, str):
                        compiled_pdf_payload = pdf_out.encode("latin-1", errors="ignore")
                    else:
                        compiled_pdf_payload = bytes(pdf_out)
                except AttributeError:
                    compiled_pdf_payload = bytes(pdf.output(dest="S"))
                
                st.download_button(
                    label="📄 Download Quick PDF Preview",
                    data=compiled_pdf_payload,
                    file_name=f"O_West_Proposal_{final_client_name.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )

            # Document Hub Display
            if st.session_state.doc_url and st.session_state.pdf_url:
                st.markdown("### 📥 Generated Proposal Documents")
                st.success("Files successfully compiled inside Google Workspace!")
                
                col_l1, col_l2, col_l3 = st.columns(3)
                with col_l1:
                    st.link_button("📄 Open Google Doc Editor", st.session_state.doc_url, use_container_width=True)
                with col_l2:
                    st.link_button("💾 View / Download PDF", st.session_state.pdf_url, use_container_width=True)
                with col_l3:
                    js_share_component = """
                    <button id="shareBtn" style="width:100%; height:45px; background-color:#25D366; color:white; border:none; border-radius:5px; font-weight:bold; font-size:16px; cursor:pointer;">
                        🟢 Share PDF over WhatsApp / Mobile
                    </button>
                    <script>
                    document.getElementById('shareBtn').addEventListener('click', () => {
                        if (navigator.share) {
                            navigator.share({
                                title: 'O West Proposal',
                                text: 'Dear Client, Please find the attached O West Quotation Proposal for Unit UNIT_PLACEHOLDER.',
                                url: 'URL_PLACEHOLDER'
                            }).then(() => {
                                console.log('Successfully shared proposal');
                            }).catch((err) => {
                                console.log('Error sharing', err);
                            });
                        } else {
                            window.open('URL_PLACEHOLDER', '_blank');
                        }
                    });
                    </script>
                    """.replace("URL_PLACEHOLDER", st.session_state.pdf_url).replace("UNIT_PLACEHOLDER", selected_unit)
                    
                    st.components.v1.html(js_share_component, height=55)
else:
    st.info("Awaiting structural backend database connection strings...")
