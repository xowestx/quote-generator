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

# Verified Room-by-Room Furniture Rate Mapping (As per Rates Tab Option "O")
FURNITURE_RATES = {
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
    "OUTDOORS - P2": 64153.21
}

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
        
        # Robust fetch for CLIENT NAME: prevents grabbing FACT tab by default if tab name has encoding issues
        clients = pd.DataFrame()
        for sheet_guess in ["CLIENT%20NAME", "CLIENT_NAME", "Client%20Name"]:
            try:
                temp_df = get_csv(sheet_guess)
                if not temp_df.empty:
                    header_str = " ".join([str(c).upper() for c in temp_df.columns])
                    # Verify it's actually the Client Name tab and not a default fallback tab
                    if ('CLIENT' in header_str or 'NAME' in header_str) and 'UNIT' in header_str:
                        clients = temp_df
                        break
            except Exception:
                continue
        
        for df in [facts, products, rates, clients, terms]:
            if df is not None and not df.empty:
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
    
    # 1. Identify columns in both FACT and CLIENT NAME tables robustly
    fact_unit_id_col = next((c for c in df_fact.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), df_fact.columns[0])
    
    c_unit_col = None
    c_name_col = None
    
    if df_clients is not None and not df_clients.empty:
        # Dynamically map the Unit and Name columns based on headers
        for col in df_clients.columns:
            c_upper = str(col).upper()
            if 'UNIT' in c_upper:
                c_unit_col = col
            if 'NAME' in c_upper or 'CLIENT' in c_upper:
                c_name_col = col

    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        # Build the Valid Units Dropdown by combining BOTH tables
        valid_units_client = []
        if c_unit_col is not None and c_unit_col in df_clients.columns:
            valid_units_client = [str(u).strip() for u in df_clients[c_unit_col].unique() if str(u).strip() and str(u).strip().upper() not in ['NAN', 'NONE', '0.0', '0']]
            
        valid_units_fact = []
        if fact_unit_id_col is not None and fact_unit_id_col in df_fact.columns:
            valid_units_fact = [str(u).strip() for u in df_fact[fact_unit_id_col].unique() if str(u).strip() and str(u).strip().upper() not in ['NAN', 'NONE']]
            
        # Combine units so no unit is left behind, sort alphabetically
        combined_units = list(set(valid_units_client + valid_units_fact))
        valid_units = sorted(combined_units, key=lambda x: str(x))
        selected_unit = st.selectbox("Select Unit ID", valid_units)
        
    with col_u2:
        db_client_name = ""
        
        if df_clients is not None and not df_clients.empty:
            def super_clean(text):
                t = str(text).strip()
                if t.endswith('.0'): t = t[:-2]
                return re.sub(r'[\s\-_/]+', '', t).upper()
                
            safe_selected_unit = super_clean(selected_unit)
            
            # Fast vectorized match (Using columns mapped above)
            if c_unit_col is not None and c_name_col is not None:
                df_clients['_safe_unit'] = df_clients[c_unit_col].apply(super_clean)
                match_row = df_clients[df_clients['_safe_unit'] == safe_selected_unit]
                if not match_row.empty:
                    raw_name = str(match_row.iloc[0][c_name_col]).strip()
                    if raw_name.upper() not in ["", "NAN", "NONE", "NULL", "0.0", "0", "0.00"]:
                        db_client_name = raw_name
            
            # Failsafe fallback: Deep sweep of all cells in dataframe if exact mapping fails
            if not db_client_name:
                for row_idx in range(len(df_clients)):
                    row = df_clients.iloc[row_idx]
                    cleaned_cells = [super_clean(cell) for cell in row.values]
                    
                    if safe_selected_unit in cleaned_cells:
                        for cell in row.values:
                            cell_str = str(cell).strip()
                            # Select the first column that has text and is NOT the unit ID itself
                            if cell_str.upper() not in ["", "NAN", "NONE", "NULL", "0.0", "0", "0.00"]:
                                if super_clean(cell_str) != safe_selected_unit:
                                    db_client_name = cell_str
                                    break
                        if db_client_name:
                            break

        # Push to the UI
        client_name = st.text_input("Client Name Reference (Optional)", value=db_client_name, autocomplete="off")

    # 4. Extract metadata from FACT Table SECOND
    unit_meta = {}
    if df_fact is not None and not df_fact.empty:
        # Try direct match
        df_fact['__match_fact'] = df_fact[fact_unit_id_col].astype(str).str.strip().str.upper()
        target_unit_str = str(selected_unit).strip().upper()
        unit_meta_df = df_fact[df_fact['__match_fact'] == target_unit_str]
        
        if not unit_meta_df.empty:
            unit_meta = unit_meta_df.iloc[0]
        else:
            # Aggressive fuzzy match fallback if formatting differs slightly (e.g. spaces/slashes)
            def fuzzy_clean(text):
                t = str(text).strip()
                if t.endswith('.0'): t = t[:-2]
                return re.sub(r'[\s\-_/]+', '', t).upper()
                
            safe_target = fuzzy_clean(selected_unit)
            df_fact['__fuzzy_fact'] = df_fact[fact_unit_id_col].apply(fuzzy_clean)
            fuzzy_meta_df = df_fact[df_fact['__fuzzy_fact'] == safe_target]
            if not fuzzy_meta_df.empty:
                unit_meta = fuzzy_meta_df.iloc[0]

    unit_project = str(unit_meta.get('Project', '')).strip().upper()
    unit_type = unit_meta.get('Unit Type', '')
    unit_design_type = unit_meta.get('Design Type', '')
    unit_design_opt = unit_meta.get('Design Option', unit_meta.get('Design Options', ''))
    zone_name = unit_meta.get('Zone', 'Unknown Zone')
    
    # Extract extra physical attributes from FACT tab
    unit_bua = unit_meta.get('Built up area', unit_meta.get('Built Up Area', 0))
    land_area = unit_meta.get('Land Area', 0)
    bedrooms = unit_meta.get('No. Of Bedrooms', unit_meta.get('Bedrooms', 0))
    bathrooms = unit_meta.get('No. of Bathrooms', unit_meta.get('Bathrooms', 0))
    floors = unit_meta.get('No. of Floors', unit_meta.get('Floors', 0))
    footprint = unit_meta.get('Foot Print', unit_meta.get('Footprint', 0))

    # Clean formatting functions to handle zero values and floats properly
    def fmt_val(val, is_qty=False):
        try:
            v = float(val)
            if v == 0: return "N/A"
            return str(int(v)) if is_qty or v.is_integer() else f"{v:.2f}"
        except:
            s = str(val).strip()
            return s if s and s.upper() not in ["0", "NAN", "NONE"] else "N/A"

    def fmt_sqm(val):
        res = fmt_val(val)
        return f"{res} sqm" if res != "N/A" else "N/A"
    
    # Render First Row
    m1, m2, m3 = st.columns(3)
    m1.metric("Unit Profile", str(unit_type) if unit_type else "N/A")
    m2.metric("Native Design Options", str(unit_design_opt) if unit_design_opt else "N/A")
    m3.metric("Native Design Type", str(unit_design_type) if unit_design_type else "N/A")
    
    st.write("") # Spacer for clean UI
    
    # Render Second Row (New Data)
    def grey_metric(label, value):
        st.markdown(
            f"""
            <div style="color: #737373;">
                <p style="font-size: 14px; margin-bottom: 0px; padding-bottom: 0px;">{label}</p>
                <p style="font-size: 1.8rem; padding-top: 0px; margin-top: 0px; line-height: 1.2;">{value}</p>
            </div>
            """, unsafe_allow_html=True
        )

    m4, m5, m6, m7, m8, m9 = st.columns(6)
    with m4: grey_metric("Land Area", fmt_sqm(land_area))
    with m5: st.metric("Built Up Area", fmt_sqm(unit_bua))
    with m6: grey_metric("Bedrooms", fmt_val(bedrooms, is_qty=True))
    with m7: grey_metric("Bathrooms", fmt_val(bathrooms, is_qty=True))
    with m8: grey_metric("Floors", fmt_val(floors, is_qty=True))
    with m9: grey_metric("Foot Print", fmt_sqm(footprint))
    
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
        prod_project_col = next((c for c in df_products.columns if 'PROJECT' in c.upper()), None)
        
        target_unit_type = str(unit_type).strip().upper()
        target_design_type = str(unit_design_type).strip().upper()
        target_design_opt = str(unit_design_opt).strip().upper()
        
        filtered_catalog = df_products.copy()
        
        # New filtration layer: Filter by Project Match (Containment Check)
        if prod_project_col and unit_project and unit_project not in ['NAN', 'NONE', '']:
            def match_project(prod_proj):
                p = str(prod_proj).strip().upper()
                if not p or p in ['NAN', 'NONE']: return False
                # Check if product project is substring of unit project or vice versa
                return p in unit_project or unit_project in p
                
            mask = filtered_catalog[prod_project_col].apply(match_project)
            if mask.any(): 
                filtered_catalog = filtered_catalog[mask]
                
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
        st.markdown("### 🛋️ Room-by-Room Furniture Builder")
        st.info("💡 **Unified System Workspace:** Select your Package Level (rates scale dynamically: Luxury = 100%, Deluxe = 70%, Rent = 35%). Load clean typology presets or append specific rooms exactly as they appear in your Rates Database.")
        
        # Ensure st.session_state.staged_items is formatted correctly as a list
        if 'staged_items' not in st.session_state or not isinstance(st.session_state.staged_items, list):
            st.session_state.staged_items = []
            
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.markdown("##### Option A: Quick Populate Typology Preset")
            fur_package = st.selectbox("Select Furniture Package Tier", ["Luxury [L]", "Deluxe [D]", "Rent [R]"])
            fur_unit_type = st.selectbox("Select Unit Typology Preset", ["1 Bedroom", "2 Bedrooms", "3 Bedrooms", "3 Bedrooms+N", "3 Bedrooms+N+F", "4 Bedrooms+N"])
            
            # Map selected package tier to multiplier factor
            pkg_code_letter = "L" if "Luxury" in fur_package else "D" if "Deluxe" in fur_package else "R"
            multiplier = 1.0 if pkg_code_letter == "L" else 0.7 if pkg_code_letter == "D" else 0.35
            
            if st.button("➕ Populate Preset Rooms", use_container_width=True):
                rooms_to_add = []
                
                # Setup specific room names directly matching structural rate mapping definitions
                rooms_to_add.append({"desc": "Reception Room", "qty": 1.0, "key": "RECEPTION - P1"})
                rooms_to_add.append({"desc": "Dining Room", "qty": 1.0, "key": "DINING ROOM - P2"})
                rooms_to_add.append({"desc": "Terrace Area", "qty": 1.0, "key": "TERRACE - P1"})
                
                if "+N" in fur_unit_type: 
                    rooms_to_add.append({"desc": "Nanny's Room", "qty": 1.0, "key": "NANNY'S ROOM"})
                if "+F" in fur_unit_type: 
                    rooms_to_add.append({"desc": "Living Room Area", "qty": 1.0, "key": "LIVING ROOM - P1"})
                    
                num_beds = int(fur_unit_type[0])
                rooms_to_add.append({"desc": "Master Bedroom Area", "qty": 1.0, "key": "MASTER BEDROOM - P1"})
                if num_beds > 1: 
                    rooms_to_add.append({"desc": "Kids Bedroom Area", "qty": float(num_beds - 1), "key": "KIDS BEDROOM - P1"})
                    
                fur_request_name = f"{fur_unit_type}, {fur_package}"

                new_staged = []
                for idx, r in enumerate(rooms_to_add):
                    base_rate = FURNITURE_RATES[r["key"]]
                    scaled_rate = base_rate * multiplier
                    total = r["qty"] * scaled_rate
                    # ADDED NEW FURNITURE INCLUSIONS HERE
                    full_desc = f"Supply and install Furniture for {r['desc']} as per attached design, including Curtains, rugs, cushions, bed linens, table lamps, pendant lights, and mattresses."
                    new_staged.append({
                        'No.': idx + 1, 
                        'Description': full_desc, 
                        'Unit': 'LS', 
                        'QTY': r["qty"], 
                        'Rate': scaled_rate,
                        'Total Amount': total, 
                        'Lookup Name': fur_request_name,
                        'Base Key': r["key"],
                        'Multiplier': multiplier
                    })
                    
                # ADD EXTRA AMENITIES: Kitchen, Closets, and ACs
                # Kitchen
                kitchen_desc = f"Supply and install kitchen with {'Luxury' if pkg_code_letter == 'L' else 'Deluxe' if pkg_code_letter == 'D' else 'Rent'} finish as per approved sample and attached design."
                kitchen_rate = 354350.00 if pkg_code_letter == 'L' else 270050.00 if pkg_code_letter == 'D' else 185750.00
                new_staged.append({
                    'No.': len(new_staged) + 1, 'Description': kitchen_desc, 'Unit': 'LS', 'QTY': 1.0,
                    'Rate': kitchen_rate, 'Total Amount': kitchen_rate, 'Lookup Name': fur_request_name, 'Base Key': f"KITCHEN - {pkg_code_letter}", 'Multiplier': 1.0
                })
                
                # Closets (Master vs Kids)
                if pkg_code_letter == 'L':
                    closet_desc_base = "Supply and install a wardrobe constructed from 'Good Wood' blockboard with an HPL finish and pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                    closet_rate = 72800.00
                elif pkg_code_letter == 'D':
                    closet_desc_base = "Supply and install a wardrobe constructed from melamine-faced blockboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                    closet_rate = 72800.00 * 0.7
                else:
                    closet_desc_base = "Supply and install a wardrobe constructed from melamine-faced chipboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                    closet_rate = 72800.00 * 0.5
                
                # Master Bedroom Wardrobe
                new_staged.append({
                    'No.': len(new_staged) + 1, 'Description': closet_desc_base + " for Master Bedroom", 'Unit': 'NO.', 'QTY': 2.0,
                    'Rate': closet_rate, 'Total Amount': 2.0 * closet_rate, 'Lookup Name': fur_request_name, 'Base Key': f"CLOSETS - {pkg_code_letter}", 'Multiplier': 1.0
                })
                
                # Kids Bedroom Wardrobe
                if num_beds > 1:
                    kids_qty = float(num_beds - 1)
                    new_staged.append({
                        'No.': len(new_staged) + 1, 'Description': closet_desc_base + " for Kids Bedrooms", 'Unit': 'NO.', 'QTY': kids_qty,
                        'Rate': closet_rate, 'Total Amount': kids_qty * closet_rate, 'Lookup Name': fur_request_name, 'Base Key': f"CLOSETS - {pkg_code_letter}", 'Multiplier': 1.0
                    })
                
                # Nanny's Wardrobe
                if "+N" in fur_unit_type:
                    nanny_closet_desc = "Supply and install a wardrobe constructed from melamine-faced chipboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2000 X 2200 MM H for Nanny's Room"
                    nanny_closet_rate = 22500.00
                    new_staged.append({
                        'No.': len(new_staged) + 1, 'Description': nanny_closet_desc, 'Unit': 'NO.', 'QTY': 1.0,
                        'Rate': nanny_closet_rate, 'Total Amount': nanny_closet_rate, 'Lookup Name': fur_request_name, 'Base Key': "CLOSETS - NANNY", 'Multiplier': 1.0
                    })
                
                # ACs UPDATED
                new_staged.append({
                    'No.': len(new_staged) + 1, 'Description': "Supply and install 3 hp Carrier AC split unit for Reception, including freon piping required.", 'Unit': 'NO.', 'QTY': 1.0,
                    'Rate': 60694.40, 'Total Amount': 60694.40, 'Lookup Name': fur_request_name, 'Base Key': "AC - 3HP", 'Multiplier': 1.0
                })
                new_staged.append({
                    'No.': len(new_staged) + 1, 'Description': "Supply and install 1.5 hp Carrier AC split unit for Bedrooms, including freon piping required.", 'Unit': 'NO.', 'QTY': float(num_beds),
                    'Rate': 38772.20, 'Total Amount': float(num_beds) * 38772.20, 'Lookup Name': fur_request_name, 'Base Key': "AC - 1.5HP", 'Multiplier': 1.0
                })

                st.session_state.staged_items = new_staged
                st.toast("Typology preset rooms loaded successfully!")

        with col_f2:
            st.markdown("##### Option B: Append Specific Database Room (O Option)")
            add_room_pkg = st.selectbox("Select Package Tier for this Room", ["Luxury [L]", "Deluxe [D]", "Rent [R]"], key="add_room_pkg")
            add_room_key = st.selectbox("Select Database Room Option", list(FURNITURE_RATES.keys()))
            add_room_qty = st.number_input("Enter Quantity", min_value=1.0, max_value=10.0, value=1.0, step=1.0)
            
            if st.button("➕ Append Room Option", use_container_width=True):
                pkg_code_letter_b = "L" if "Luxury" in add_room_pkg else "D" if "Deluxe" in add_room_pkg else "R"
                multiplier_b = 1.0 if pkg_code_letter_b == "L" else 0.7 if pkg_code_letter_b == "D" else 0.35
                
                base_rate = FURNITURE_RATES[add_room_key]
                scaled_rate = base_rate * multiplier_b
                total = add_room_qty * scaled_rate
                
                clean_room_name = add_room_key.split(" - ")[0].title()
                if "Nanny" in clean_room_name:
                    clean_room_name = "Nanny's Room"
                
                # ADDED NEW FURNITURE INCLUSIONS HERE
                full_desc = f"Supply and install Furniture for {clean_room_name} as per attached design, including Curtains, rugs, cushions, bed linens, table lamps, pendant lights, and mattresses."
                default_lookup = f"Custom Suite, {add_room_pkg}"
                if st.session_state.staged_items:
                    default_lookup = st.session_state.staged_items[0].get('Lookup Name', default_lookup)
                
                next_no = len(st.session_state.staged_items) + 1
                st.session_state.staged_items.append({
                    'No.': next_no,
                    'Description': full_desc,
                    'Unit': 'LS',
                    'QTY': float(add_room_qty),
                    'Rate': scaled_rate,
                    'Total Amount': total,
                    'Lookup Name': default_lookup,
                    'Base Key': add_room_key,
                    'Multiplier': multiplier_b
                })
                st.rerun()

        if st.session_state.staged_items:
            st.markdown("### 📊 Active Unified Furniture Quotation List")
            st.info("💡 **Interactive Table:** Select any row and press **Delete** (or click the trash icon) to remove specific rooms. You can also edit the QTY directly!")
            
            df_staged = pd.DataFrame(st.session_state.staged_items)
            
            edited_df = st.data_editor(
                df_staged,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="furniture_editor",
                column_config={
                    "Lookup Name": None,
                    "Base Key": None,
                    "Multiplier": None,
                    "No.": st.column_config.NumberColumn("No.", disabled=True),
                    "Description": st.column_config.TextColumn("Description", disabled=True),
                    "Unit": st.column_config.TextColumn("Unit", disabled=True),
                    "QTY": st.column_config.NumberColumn("QTY", min_value=0.0),
                    "Rate": st.column_config.NumberColumn("Rate", format="%.2f", disabled=True),
                    "Total Amount": st.column_config.NumberColumn("Total", format="%.2f", disabled=True)
                }
            )
            
            # Sync edits and row deletions back to staged_items
            updated_items = []
            edited_df = edited_df.reset_index(drop=True)
            for idx, row in edited_df.iterrows():
                item = row.to_dict()
                item['No.'] = len(updated_items) + 1
                
                # Recalculate totals dynamically if user edits QTY inside the table
                rate = float(item.get('Rate', 0.0))
                qty = float(item.get('QTY', 1.0))
                item['Total Amount'] = qty * rate
                
                updated_items.append(item)
                
            # Update session state if user changed QTY or deleted a row
            if updated_items != st.session_state.staged_items:
                st.session_state.staged_items = updated_items
                st.rerun()
            
            subtotal = sum(item['Total Amount'] for item in st.session_state.staged_items)
            vat = subtotal * 0.14
            total_with_vat = subtotal + vat

            col_t1, col_t2 = st.columns(2)
            col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")
            
            if st.button("❌ Clear Furniture Configuration", type="secondary", use_container_width=True):
                st.session_state.staged_items = []
                st.rerun()

            # ==========================================
            # 🚀 BULK EXPORT ENGINE (ALL 18 PACKAGES)
            # ==========================================
            st.markdown("---")
            st.markdown("### 🚀 Bulk Export Engine")
            st.warning("⚠️ **Warning:** Generating all 18 PDFs involves heavy processing and API calls. This process will take a few minutes. Please do not close the window while the progress bar is running.")
            
            if st.button("🔥 Generate & Export All 18 Options (One-Click)", type="primary", use_container_width=True):
                
                # Define iteration matrices
                typologies = ["1 Bedroom", "2 Bedrooms", "3 Bedrooms", "3 Bedrooms+N", "3 Bedrooms+N+F", "4 Bedrooms+N"]
                packages = ["Luxury [L]", "Deluxe [D]", "Rent [R]"]
                outdoors = ["No"] # STRICTLY SET TO 'No' TO REDUCE TO 18 OPTIONS
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
                            
                            # 1. Resolve Package Codes, Multipliers & Variables
                            pkg_code_letter = "L" if "Luxury" in p else "D" if "Deluxe" in p else "R"
                            payload_pkg_code = "P1" if pkg_code_letter == "L" else "P2" if pkg_code_letter == "D" else "P3"
                            bulk_multiplier = 1.0 if pkg_code_letter == "L" else 0.7 if pkg_code_letter == "D" else 0.35
                            
                            outdoor_text = ", + Outdoor" if o == "Yes" else ""
                            fur_request_name = f"{t}, {p}{outdoor_text}"
                            status_text.text(f"⚙️ Compiling {current_iter}/{total_iters}: {fur_request_name}...")
                            
                            # 2. Build Automated BOQ for this specific combination
                            rooms_to_add = [
                                {"desc": "Reception Room", "qty": 1.0, "key": "RECEPTION - P1"},
                                {"desc": "Dining Room", "qty": 1.0, "key": "DINING ROOM - P2"},
                                {"desc": "Terrace Area", "qty": 1.0, "key": "TERRACE - P1"}
                            ]
                            if "+N" in t: 
                                rooms_to_add.append({"desc": "Nanny's Room", "qty": 1.0, "key": "NANNY'S ROOM"})
                            if "+F" in t: 
                                rooms_to_add.append({"desc": "Living Room Area", "qty": 1.0, "key": "LIVING ROOM - P1"})
                            
                            num_beds = int(t[0])
                            rooms_to_add.append({"desc": "Master Bedroom Area", "qty": 1.0, "key": "MASTER BEDROOM - P1"})
                            if num_beds > 1: 
                                rooms_to_add.append({"desc": "Kids Bedroom Area", "qty": float(num_beds - 1), "key": "KIDS BEDROOM - P1"})
                            
                            staged_items_payload = []
                            for r in rooms_to_add:
                                base_rate = FURNITURE_RATES[r["key"]]
                                scaled_rate = base_rate * bulk_multiplier
                                # ADDED NEW FURNITURE INCLUSIONS HERE
                                staged_items_payload.append({
                                    "description": f"Supply and install Furniture for {r['desc']} as per attached design, including Curtains, rugs, cushions, bed linens, table lamps, pendant lights, and mattresses.",
                                    "unit": "LS", 
                                    "qty": r["qty"], 
                                    "rate": scaled_rate
                                })
                                
                            # BULK ADD EXTRA AMENITIES: Kitchen, Closets, and ACs
                            kitchen_desc = f"Supply and install kitchen with {'Luxury' if pkg_code_letter == 'L' else 'Deluxe' if pkg_code_letter == 'D' else 'Rent'} finish as per approved sample and attached design."
                            kitchen_rate = 354350.00 if pkg_code_letter == 'L' else 270050.00 if pkg_code_letter == 'D' else 185750.00
                            staged_items_payload.append({
                                "description": kitchen_desc, "unit": "LS", "qty": 1.0, "rate": kitchen_rate
                            })

                            if pkg_code_letter == 'L':
                                closet_desc_base = "Supply and install a wardrobe constructed from 'Good Wood' blockboard with an HPL finish and pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                                closet_rate = 72800.00
                            elif pkg_code_letter == 'D':
                                closet_desc_base = "Supply and install a wardrobe constructed from melamine-faced blockboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                                closet_rate = 72800.00 * 0.7
                            else:
                                closet_desc_base = "Supply and install a wardrobe constructed from melamine-faced chipboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2800 X 2200 MM H"
                                closet_rate = 72800.00 * 0.5
                            
                            # Master Bedroom Wardrobe
                            staged_items_payload.append({
                                "description": closet_desc_base + " for Master Bedroom", "unit": "NO.", "qty": 2.0, "rate": closet_rate
                            })
                            
                            # Kids Bedroom Wardrobe
                            if num_beds > 1:
                                staged_items_payload.append({
                                    "description": closet_desc_base + " for Kids Bedrooms", "unit": "NO.", "qty": float(num_beds - 1), "rate": closet_rate
                                })
                            
                            # Nanny's Wardrobe
                            if "+N" in t:
                                nanny_closet_desc = "Supply and install a wardrobe constructed from melamine-faced chipboard with pressed blockboard boxes, fully fitted with hinged wooden doors and all necessary installation hardware. SIZE: 2000 X 2200 MM H for Nanny's Room"
                                staged_items_payload.append({
                                    "description": nanny_closet_desc, "unit": "NO.", "qty": 1.0, "rate": 22500.00
                                })

                            # ACs UPDATED
                            staged_items_payload.append({
                                "description": "Supply and install 3 hp Carrier AC split unit for Reception, including freon piping required.", "unit": "NO.", "qty": 1.0, "rate": 60694.40
                            })
                            staged_items_payload.append({
                                "description": "Supply and install 1.5 hp Carrier AC split unit for Bedrooms, including freon piping required.", "unit": "NO.", "qty": float(num_beds), "rate": 38772.20
                            })
                                
                            # 3. Trigger Webhook (Doc Generation) - Sending typology name as requestType to trigger Apps Script regex!
                            payload = {
                                "action": "generateDocOnly",
                                "unitId": selected_unit,
                                "clientName": final_client_name,
                                "zone": str(zone_name),
                                "requestType": fur_request_name,  # THIS FIXES THE TEMPLATE ISSUE
                                "packageCode": payload_pkg_code,
                                "packageName": fur_request_name,
                                "items": staged_items_payload
                            }
                            
                            try:
                                res = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                                res_data = res.json()
                                
                                if res_data.get("status") == "success":
                                    # Skip PDF Merging and upload directly back
                                    up_payload = {
                                        "action": "uploadPdf",
                                        "docName": res_data["docName"],
                                        "base64Pdf": res_data["docBase64"],
                                        "serialNumber": res_data["serialNumber"],
                                        "unitId": selected_unit,
                                        "clientName": final_client_name,
                                        "requestType": fur_request_name,  # Matches above
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

    elif selected_request_type == "Closing Double Height":
        st.markdown("### 🏗️ Closing Double Height Configuration")
        
        # Identify columns dynamically
        rate_cat_col = df_rates.columns[0]
        rate_val_col = df_rates.columns[1]
        rate_opt_col = df_rates.columns[2] if len(df_rates.columns) > 2 else df_rates.columns[-1]
        
        # Filter for Closing Double Height options
        category_rates = df_rates[df_rates[rate_cat_col].astype(str).str.upper() == "CLOSING DOUBLE HEIGHT"]
        
        # Provide a fallback just in case the rates tab doesn't match perfectly
        if category_rates.empty:
            st.warning("Rates for 'Closing Double Height' not found. Using system defaults.")
            category_rates = pd.DataFrame({
                rate_cat_col: ["Closing Double Height", "Closing Double Height"],
                rate_val_col: [61052.63, 67631.58],
                rate_opt_col: ["6 months installment", "24 months installment"]
            })
            
        col_cdh1, col_cdh2 = st.columns(2)
        with col_cdh1:
            cdh_qty = st.number_input("Enter Area (SQM)", min_value=1.0, max_value=500.0, value=10.0, step=1.0)
        with col_cdh2:
            chosen_term_option = st.selectbox("Financing & Installment Plan", category_rates[rate_opt_col].unique())
            
        # Get specific record
        rate_record = category_rates[category_rates[rate_opt_col] == chosen_term_option].iloc[0]
        
        try:
            rate_val = str(rate_record[rate_val_col]).replace(',', '').replace('$', '').strip()
            base_rate = float(rate_val)
        except: 
            base_rate = 0.0
            
        calculated_line_item_total = (base_rate * cdh_qty) + 50000.0
        
        # Format the quantity to remove decimals if it's a whole number for the description
        formatted_qty = int(cdh_qty) if cdh_qty.is_integer() else cdh_qty
        cdh_description = f"Required fees for Supply and install reinforced concrete slab for closing double height for {formatted_qty} sqm as per drawings."
        
        # Manage suffix to display on generated docs properly
        financing_name_suffix = " - 6 months" if "6" in str(chosen_term_option) else " - 24 months" if "24" in str(chosen_term_option) else f" - {chosen_term_option}"
        resolved_request_name = "Closing Double Height" + financing_name_suffix
        
        # Storing as 1 LS, and the rate contains the full combined value
        st.session_state.staged_items = [{
            'No.': 1, 
            'Description': cdh_description, 
            'Unit': 'LS', 
            'QTY': 1.0, 
            'Rate': calculated_line_item_total, 
            'Total Amount': calculated_line_item_total,
            'Financing Options': chosen_term_option, 
            'Lookup Name': resolved_request_name
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

    else:
        st.markdown(f"### 📝 Custom BOQ Entry Table: {selected_request_type}")
        st.info("💡 **Tip:** Type smoothly in the center! The read-only previews calculate No., Unit, Rate, and Total instantly.")
        
        if 'custom_boq_data' not in st.session_state or st.session_state.get('last_type') != selected_request_type:
            if selected_request_type == "Land Extension":
                initial_data = [{'Description': 'Required Fees for Adding land extension area of for a/m unit as per attached Drawings.', 'Unit': 'M2', 'QTY': 0.0, 'Rate': 65000.0}]
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
                        if selected_request_type in ["Roof Room", "Closing Double Height", "Furniture"] and 'Lookup Name' in st.session_state.staged_items[0]:
                            resolved_req_name = st.session_state.staged_items[0]['Lookup Name']

                        payload = {
                            "action": "standard",
                            "unitId": selected_unit,
                            "clientName": final_client_name,
                            "zone": str(zone_name),
                            "requestType": resolved_req_name, # Passes the typology name instead of "Furniture"
                            "items": []
                        }
                        
                        for item in st.session_state.staged_items:
                            payload["items"].append({
                                "description": item.get("Description", ""),
                                "unit": item.get("Unit", "LS"),
                                "qty": item.get("QTY", 1.0),
                                "rate": item.get("Rate", 0.0)
                            })
                            
                        # Add packageCode and packageName to the payload for single Furniture exports so it triggers the Furniture template
                        if selected_request_type == "Furniture":
                            fur_package_name = st.session_state.staged_items[0].get('Lookup Name', '')
                            if "[L]" in fur_package_name: pkg_code = "P1"
                            elif "[D]" in fur_package_name: pkg_code = "P2"
                            elif "[R]" in fur_package_name: pkg_code = "P3"
                            else: pkg_code = "P1"
                            payload["action"] = "generateDocOnly"
                            payload["packageCode"] = pkg_code
                            payload["packageName"] = fur_package_name
                                
                        try:
                            headers = {"Content-Type": "application/json"}
                            response = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                            
                            if response.status_code == 200:
                                response_data = response.json()
                                
                                # Process standard quote
                                if response_data.get("status") == "success":
                                    if selected_request_type != "Furniture":
                                        st.success("✅ Quotation Generated Successfully!")
                                        st.session_state.doc_url = response_data.get('docUrl')
                                        st.session_state.pdf_url = response_data.get('pdfUrl')
                                        st.rerun()
                                    else:
                                        # Furniture 2-step (No PDF merging)
                                        upload_payload = {
                                            "action": "uploadPdf",
                                            "docName": response_data["docName"],
                                            "base64Pdf": response_data["docBase64"],
                                            "serialNumber": response_data["serialNumber"],
                                            "unitId": selected_unit,
                                            "clientName": final_client_name,
                                            "requestType": resolved_req_name, # Updated to match Typology
                                            "grandTotal": response_data["grandTotal"],
                                            "zone": str(zone_name)
                                        }
                                        
                                        up_res = requests.post(WEBHOOK_URL, data=json.dumps(upload_payload), headers=headers)
                                        up_data = up_res.json()
                                        
                                        if up_data.get("status") == "success":
                                            st.success("✅ Furniture Quotation Compiled Successfully!")
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
                if selected_request_type in ["Roof Room", "Closing Double Height", "Furniture"] and 'Lookup Name' in st.session_state.staged_items[0]:
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
                
                if 'Financing Options' in st.session_state.staged_items[0] and selected_request_type in ["Roof Room", "Closing Double Height"]:
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(0, 8, "Legal Framework & Strategic Project Adjustments:", ln=True)
                    pdf.set_font("Helvetica", "", 8)
                    
                    terms_opt_col = df_terms.columns[1] if len(df_terms.columns) > 1 else df_terms.columns[0]
                    terms_text_col = df_terms.columns[2] if len(df_terms.columns) > 2 else df_terms.columns[-1]
                    
                    rule_term = st.session_state.staged_items[0].get('Financing Options')
                    lookup_request_name = st.session_state.staged_items[0].get('Lookup Name', selected_request_type)
                    
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
