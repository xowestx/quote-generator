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

from terms_engine import (
    generate_terms,
    parse_terms_defaults,
    validate_terms_values,
)

# Import PDF Merger
try:
    from pypdf import PdfReader, PdfWriter
    has_pypdf = True
except ImportError:
    has_pypdf = False


def merge_pdf_base64(primary_pdf_base64, supplemental_pdf_base64s):
    """Append selected furniture design PDFs to the quotation PDF."""
    supplemental_pdf_base64s = [
        pdf_data for pdf_data in (supplemental_pdf_base64s or []) if pdf_data
    ]
    if not has_pypdf or not supplemental_pdf_base64s:
        return primary_pdf_base64

    writer = PdfWriter()
    for encoded_pdf in [primary_pdf_base64] + supplemental_pdf_base64s:
        reader = PdfReader(io.BytesIO(base64.b64decode(encoded_pdf)))
        for page in reader.pages:
            writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return base64.b64encode(output.getvalue()).decode("ascii")

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

# P1/P2/P3 are design options. L/D/R are package tiers. The correct design
# code differs by room, so it must travel with each quotation item.
FURNITURE_PACKAGE_DESIGNS = {
    "L": {
        "RECEPTION": "RECEPTION - P1",
        "LIVING ROOM": "LIVING ROOM - P1",
        "DINING ROOM": "DINING ROOM - P2",
        "MASTER BEDROOM": "MASTER BEDROOM - P1",
        "KIDS BEDROOM": "KIDS BEDROOM - P1",
        "TERRACE": "TERRACE - P1",
        "OUTDOORS": "OUTDOORS - P2",
    },
    "D": {
        "RECEPTION": "RECEPTION - P2",
        "LIVING ROOM": "LIVING ROOM - P2",
        "DINING ROOM": "DINING ROOM - P1",
        "MASTER BEDROOM": "MASTER BEDROOM - P3",
        "KIDS BEDROOM": "KIDS BEDROOM - P2",
        "TERRACE": "TERRACE - P2",
        "OUTDOORS": "OUTDOORS - P1",
    },
    "R": {
        "RECEPTION": "RECEPTION - P3",
        "LIVING ROOM": "LIVING ROOM - P3",
        "DINING ROOM": "DINING ROOM - P3",
        "MASTER BEDROOM": "MASTER BEDROOM - P2",
        "KIDS BEDROOM": "KIDS BEDROOM - P3",
        "TERRACE": "TERRACE - P3",
        "OUTDOORS": "OUTDOORS - P3",
    },
}

LAND_EXTENSION_RATES = (55000.0, 65000.0)

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
        # Terms & Conditions now live in the APP spreadsheet as the single source.
        terms = get_csv("TERMS%20%26%20CONDITIONS")
        
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
        
        # Start with Roof Room products only. Other product categories must never
        # appear as fallbacks when a unit has no configured Roof Room product.
        filtered_catalog = df_products[
            df_products[cat_col].astype(str).str.strip().str.upper() == "ROOF ROOM"
        ].copy()

        def catalog_value_matches(product_value, target_value):
            """Blank product values act as wildcards; populated values must match."""
            product_text = str(product_value).strip().upper()
            target_text = str(target_value).strip().upper()

            if not product_text or product_text in ['NAN', 'NONE']:
                return True
            if not target_text or target_text in ['NAN', 'NONE']:
                return True

            # Supports cells containing multiple eligible values while preventing
            # the previous broad-catalog fallback after a failed match.
            return target_text in product_text or product_text in target_text

        strict_filters = [
            (prod_project_col, unit_project),
        ]

        prod_unit_type_col = next((c for c in df_products.columns if 'UNIT TYPE' in c.upper()), df_products.columns[2])
        design_type_col = next((c for c in df_products.columns if 'DESIGN TYPE' in c.upper()), df_products.columns[3])
        prod_opt_link_col = next((c for c in df_products.columns if 'OPTION LINK' in c.upper() or 'DESIGN OPTION' in c.upper()), df_products.columns[4])

        strict_filters.extend([
            (prod_unit_type_col, target_unit_type),
            (design_type_col, target_design_type),
            (prod_opt_link_col, target_design_opt),
        ])

        for filter_col, target_value in strict_filters:
            if filter_col and str(target_value).strip().upper() not in ['', 'NAN', 'NONE']:
                filtered_catalog = filtered_catalog[
                    filtered_catalog[filter_col].apply(
                        lambda value: catalog_value_matches(value, target_value)
                    )
                ]

        if filtered_catalog.empty:
            st.session_state.staged_items = []
            st.error(
                "No Roof Room product is configured for this unit typology. "
                f"Project: {unit_project or 'N/A'} | "
                f"Unit Type: {target_unit_type or 'N/A'} | "
                f"Design Type: {target_design_type or 'N/A'} | "
                f"Design Option: {target_design_opt or 'N/A'}"
            )
            st.info(
                "Add the exact eligible typology to the PRODUCTS tab before "
                "generating a Roof Room quotation."
            )
            st.stop()

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
        st.markdown("### 🛋️ Furniture Quotation Builder")
        st.info(
            "Package Tier and Design Option are separate: L/D/R controls the package "
            "level, while each room keeps its exact P1/P2/P3 design code. Custom "
            "Option O rooms use their listed rate directly with no multiplier."
        )

        if 'staged_items' not in st.session_state or not isinstance(
            st.session_state.staged_items, list
        ):
            st.session_state.staged_items = []

        st.markdown("##### Optional Add-ons")
        optional_col1, optional_col2, optional_col3 = st.columns(3)
        with optional_col1:
            include_furniture_kitchen = st.checkbox(
                "Include Kitchen",
                value=True,
                key="include_furniture_kitchen",
            )
        with optional_col2:
            include_furniture_closets = st.checkbox(
                "Include Closets",
                value=True,
                key="include_furniture_closets",
            )
        with optional_col3:
            include_furniture_ac = st.checkbox(
                "Include Air Conditioning",
                value=True,
                key="include_furniture_ac",
            )
        st.caption(
            "Optional selections are applied when you populate a preset or run bulk export."
        )

        def build_furniture_package(unit_type, package_label):
            """Build one package while preserving every existing numeric price."""
            package_code = (
                "L" if "Luxury" in package_label
                else "D" if "Deluxe" in package_label
                else "R"
            )
            multiplier = (
                1.0 if package_code == "L"
                else 0.7 if package_code == "D"
                else 0.35
            )
            num_beds = int(unit_type[0])
            request_name = f"{unit_type}, {package_label}"
            room_specs = [
                {
                    "desc": "Reception Room",
                    "qty": 1.0,
                    "rate_key": "RECEPTION - P1",
                    "design_group": "RECEPTION",
                },
                {
                    "desc": "Dining Room",
                    "qty": 1.0,
                    "rate_key": "DINING ROOM - P2",
                    "design_group": "DINING ROOM",
                },
                {
                    "desc": "Terrace Area",
                    "qty": 1.0,
                    "rate_key": "TERRACE - P1",
                    "design_group": "TERRACE",
                },
            ]
            if "+N" in unit_type:
                room_specs.append({
                    "desc": "Nanny's Room",
                    "qty": 1.0,
                    "rate_key": "NANNY'S ROOM",
                    "design_group": "NANNY'S ROOM",
                })
            if "+F" in unit_type:
                room_specs.append({
                    "desc": "Living Room Area",
                    "qty": 1.0,
                    "rate_key": "LIVING ROOM - P1",
                    "design_group": "LIVING ROOM",
                })
            room_specs.append({
                "desc": "Master Bedroom Area",
                "qty": 1.0,
                "rate_key": "MASTER BEDROOM - P1",
                "design_group": "MASTER BEDROOM",
            })
            if num_beds > 1:
                room_specs.append({
                    "desc": "Kids Bedroom Area",
                    "qty": float(num_beds - 1),
                    "rate_key": "KIDS BEDROOM - P1",
                    "design_group": "KIDS BEDROOM",
                })

            package_items = []
            for room in room_specs:
                rate = FURNITURE_RATES[room["rate_key"]] * multiplier
                design_key = FURNITURE_PACKAGE_DESIGNS[package_code].get(
                    room["design_group"], room["rate_key"]
                )
                description = (
                    f"Supply and install Furniture for {room['desc']} as per attached "
                    "design, including Curtains, rugs, cushions, bed linens, table "
                    "lamps, pendant lights, and mattresses."
                )
                package_items.append({
                    "No.": len(package_items) + 1,
                    "Description": description,
                    "Unit": "LS",
                    "QTY": room["qty"],
                    "Rate": rate,
                    "Total Amount": room["qty"] * rate,
                    "Lookup Name": request_name,
                    "Base Key": design_key,
                    "Multiplier": multiplier,
                    "Pricing Mode": f"Package {package_code}",
                })

            if include_furniture_kitchen:
                kitchen_finish = (
                    "Luxury" if package_code == "L"
                    else "Deluxe" if package_code == "D"
                    else "Rent"
                )
                kitchen_rate = (
                    354350.00 if package_code == "L"
                    else 270050.00 if package_code == "D"
                    else 185750.00
                )
                package_items.append({
                    "No.": len(package_items) + 1,
                    "Description": (
                        f"Supply and install kitchen with {kitchen_finish} finish as "
                        "per approved sample and attached design."
                    ),
                    "Unit": "LS",
                    "QTY": 1.0,
                    "Rate": kitchen_rate,
                    "Total Amount": kitchen_rate,
                    "Lookup Name": request_name,
                    "Base Key": f"KITCHEN - {package_code}",
                    "Multiplier": 1.0,
                    "Pricing Mode": "Optional Kitchen",
                })

            if include_furniture_closets:
                if package_code == "L":
                    closet_description = (
                        "Supply and install a wardrobe constructed from 'Good Wood' "
                        "blockboard with an HPL finish and pressed blockboard boxes, "
                        "fully fitted with hinged wooden doors and all necessary "
                        "installation hardware. SIZE: 2800 X 2200 MM H"
                    )
                    closet_rate = 72800.00
                elif package_code == "D":
                    closet_description = (
                        "Supply and install a wardrobe constructed from melamine-faced "
                        "blockboard with pressed blockboard boxes, fully fitted with "
                        "hinged wooden doors and all necessary installation hardware. "
                        "SIZE: 2800 X 2200 MM H"
                    )
                    closet_rate = 72800.00 * 0.7
                else:
                    closet_description = (
                        "Supply and install a wardrobe constructed from melamine-faced "
                        "chipboard with pressed blockboard boxes, fully fitted with "
                        "hinged wooden doors and all necessary installation hardware. "
                        "SIZE: 2800 X 2200 MM H"
                    )
                    closet_rate = 72800.00 * 0.5

                package_items.append({
                    "No.": len(package_items) + 1,
                    "Description": closet_description + " for Master Bedroom",
                    "Unit": "NO.",
                    "QTY": 2.0,
                    "Rate": closet_rate,
                    "Total Amount": 2.0 * closet_rate,
                    "Lookup Name": request_name,
                    "Base Key": f"CLOSETS - {package_code}",
                    "Multiplier": 1.0,
                    "Pricing Mode": "Optional Closets",
                })
                if num_beds > 1:
                    kids_quantity = float(num_beds - 1)
                    package_items.append({
                        "No.": len(package_items) + 1,
                        "Description": closet_description + " for Kids Bedrooms",
                        "Unit": "NO.",
                        "QTY": kids_quantity,
                        "Rate": closet_rate,
                        "Total Amount": kids_quantity * closet_rate,
                        "Lookup Name": request_name,
                        "Base Key": f"CLOSETS - {package_code}",
                        "Multiplier": 1.0,
                        "Pricing Mode": "Optional Closets",
                    })
                if "+N" in unit_type:
                    nanny_closet_rate = 22500.00
                    package_items.append({
                        "No.": len(package_items) + 1,
                        "Description": (
                            "Supply and install a wardrobe constructed from "
                            "melamine-faced chipboard with pressed blockboard boxes, "
                            "fully fitted with hinged wooden doors and all necessary "
                            "installation hardware. SIZE: 2000 X 2200 MM H for "
                            "Nanny's Room"
                        ),
                        "Unit": "NO.",
                        "QTY": 1.0,
                        "Rate": nanny_closet_rate,
                        "Total Amount": nanny_closet_rate,
                        "Lookup Name": request_name,
                        "Base Key": "CLOSETS - NANNY",
                        "Multiplier": 1.0,
                        "Pricing Mode": "Optional Closets",
                    })

            if include_furniture_ac:
                package_items.append({
                    "No.": len(package_items) + 1,
                    "Description": (
                        "Supply and install 3 hp Carrier AC split unit for Reception, "
                        "including freon piping required."
                    ),
                    "Unit": "NO.",
                    "QTY": 1.0,
                    "Rate": 60694.40,
                    "Total Amount": 60694.40,
                    "Lookup Name": request_name,
                    "Base Key": "AC - 3HP",
                    "Multiplier": 1.0,
                    "Pricing Mode": "Optional AC",
                })
                package_items.append({
                    "No.": len(package_items) + 1,
                    "Description": (
                        "Supply and install 1.5 hp Carrier AC split unit for Bedrooms, "
                        "including freon piping required."
                    ),
                    "Unit": "NO.",
                    "QTY": float(num_beds),
                    "Rate": 38772.20,
                    "Total Amount": float(num_beds) * 38772.20,
                    "Lookup Name": request_name,
                    "Base Key": "AC - 1.5HP",
                    "Multiplier": 1.0,
                    "Pricing Mode": "Optional AC",
                })
            return package_items

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            st.markdown("##### Option A: Complete Package")
            fur_package = st.selectbox(
                "Select Furniture Package Tier",
                ["Luxury [L]", "Deluxe [D]", "Rent [R]"],
            )
            fur_unit_type = st.selectbox(
                "Select Unit Typology Preset",
                [
                    "1 Bedroom",
                    "2 Bedrooms",
                    "3 Bedrooms",
                    "3 Bedrooms+N",
                    "3 Bedrooms+N+F",
                    "4 Bedrooms+N",
                ],
            )
            if st.button("➕ Populate Package", use_container_width=True):
                st.session_state.staged_items = build_furniture_package(
                    fur_unit_type, fur_package
                )
                st.toast("Furniture package loaded successfully!")
                st.rerun()

        with col_f2:
            st.markdown("##### Option B: Custom Room / Design (Option O)")
            st.caption(
                "Choose the exact P1/P2/P3 room design. Its stored Option O rate is "
                "used directly without an L/D/R multiplier."
            )
            add_room_key = st.selectbox(
                "Select Room Design Option",
                list(FURNITURE_RATES.keys()),
            )
            add_room_qty = st.number_input(
                "Enter Quantity",
                min_value=1.0,
                max_value=10.0,
                value=1.0,
                step=1.0,
            )
            if st.button("➕ Append Custom Room", use_container_width=True):
                exact_rate = FURNITURE_RATES[add_room_key]
                clean_room_name = add_room_key.rsplit(" - P", 1)[0].title()
                if "Nanny" in clean_room_name:
                    clean_room_name = "Nanny's Room"
                lookup_name = "Furniture - Custom [O]"
                if st.session_state.staged_items:
                    lookup_name = st.session_state.staged_items[0].get(
                        "Lookup Name", lookup_name
                    )
                description = (
                    f"Supply and install Furniture for {clean_room_name} as per "
                    "attached design, including Curtains, rugs, cushions, bed linens, "
                    "table lamps, pendant lights, and mattresses."
                )
                st.session_state.staged_items.append({
                    "No.": len(st.session_state.staged_items) + 1,
                    "Description": description,
                    "Unit": "LS",
                    "QTY": float(add_room_qty),
                    "Rate": exact_rate,
                    "Total Amount": float(add_room_qty) * exact_rate,
                    "Lookup Name": lookup_name,
                    "Base Key": add_room_key,
                    "Multiplier": 1.0,
                    "Pricing Mode": "Custom Option O",
                })
                st.rerun()

        if st.session_state.staged_items:
            st.markdown("### 📊 Active Furniture Quotation")
            st.info(
                "Edit quantities or delete unwanted rows. Rates and exact design "
                "codes are locked."
            )
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
                    "Pricing Mode": None,
                    "No.": st.column_config.NumberColumn("No.", disabled=True),
                    "Description": st.column_config.TextColumn(
                        "Description", disabled=True
                    ),
                    "Unit": st.column_config.TextColumn("Unit", disabled=True),
                    "QTY": st.column_config.NumberColumn("QTY", min_value=0.0),
                    "Rate": st.column_config.NumberColumn(
                        "Rate", format="%.2f", disabled=True
                    ),
                    "Total Amount": st.column_config.NumberColumn(
                        "Total", format="%.2f", disabled=True
                    ),
                },
            )

            updated_items = []
            for _, row in edited_df.reset_index(drop=True).iterrows():
                item = row.to_dict()
                item["No."] = len(updated_items) + 1
                item["Total Amount"] = float(item.get("QTY", 1.0)) * float(
                    item.get("Rate", 0.0)
                )
                updated_items.append(item)
            if updated_items != st.session_state.staged_items:
                st.session_state.staged_items = updated_items
                st.rerun()

            subtotal = sum(
                float(item["Total Amount"])
                for item in st.session_state.staged_items
            )
            vat = subtotal * 0.14
            total_with_vat = subtotal + vat
            col_t1, col_t2 = st.columns(2)
            col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

            if st.button(
                "❌ Clear Furniture Configuration",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.staged_items = []
                st.rerun()

            with st.expander("Bulk Export: Generate All 18 Package Options"):
                st.warning(
                    "This creates six typologies × three package tiers. The optional "
                    "Kitchen, Closets and AC selections above apply to every option."
                )
                if st.button(
                    "Generate & Export All 18 Options",
                    type="primary",
                    use_container_width=True,
                ):
                    typologies = [
                        "1 Bedroom",
                        "2 Bedrooms",
                        "3 Bedrooms",
                        "3 Bedrooms+N",
                        "3 Bedrooms+N+F",
                        "4 Bedrooms+N",
                    ]
                    packages = ["Luxury [L]", "Deluxe [D]", "Rent [R]"]
                    total_iterations = len(typologies) * len(packages)
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    final_client_name = (
                        client_name.strip() if client_name.strip() else "Unassigned"
                    )
                    headers = {"Content-Type": "application/json"}
                    success_count = 0
                    current_iteration = 0

                    terms_request_col = df_terms.columns[0]
                    terms_text_col = (
                        df_terms.columns[1]
                        if len(df_terms.columns) > 1
                        else df_terms.columns[0]
                    )
                    furniture_terms_rows = df_terms[
                        df_terms[terms_request_col]
                        .astype(str)
                        .str.strip()
                        .str.upper()
                        == "FURNITURE"
                    ]
                    furniture_master_terms = (
                        str(furniture_terms_rows.iloc[0][terms_text_col])
                        if not furniture_terms_rows.empty
                        else ""
                    )

                    for typology in typologies:
                        for package in packages:
                            current_iteration += 1
                            request_name = f"{typology}, {package}"
                            status_text.text(
                                f"Compiling {current_iteration}/{total_iterations}: "
                                f"{request_name}..."
                            )
                            items = build_furniture_package(typology, package)
                            package_code = (
                                "P1" if "[L]" in package
                                else "P2" if "[D]" in package
                                else "P3"
                            )
                            payload = {
                                "action": "generateDocOnly",
                                "requestCategory": "Furniture",
                                "unitId": selected_unit,
                                "clientName": final_client_name,
                                "zone": str(zone_name),
                                "requestType": request_name,
                                "packageCode": package_code,
                                "packageName": request_name,
                                "generatedTermsAndConditions": furniture_master_terms,
                                "items": [
                                    {
                                        "description": item["Description"],
                                        "unit": item["Unit"],
                                        "qty": item["QTY"],
                                        "rate": item["Rate"],
                                        "baseKey": item["Base Key"],
                                    }
                                    for item in items
                                ],
                            }

                            try:
                                response = requests.post(
                                    WEBHOOK_URL,
                                    data=json.dumps(payload),
                                    headers=headers,
                                )
                                response_data = response.json()
                                if response_data.get("status") == "success":
                                    merged_pdf = merge_pdf_base64(
                                        response_data["docBase64"],
                                        response_data.get("roomBase64s", []),
                                    )
                                    upload_payload = {
                                        "action": "uploadPdf",
                                        "requestCategory": "Furniture",
                                        "docName": response_data["docName"],
                                        "base64Pdf": merged_pdf,
                                        "serialNumber": response_data["serialNumber"],
                                        "unitId": selected_unit,
                                        "clientName": final_client_name,
                                        "requestType": request_name,
                                        "grandTotal": response_data["grandTotal"],
                                        "zone": str(zone_name),
                                    }
                                    upload_response = requests.post(
                                        WEBHOOK_URL,
                                        data=json.dumps(upload_payload),
                                        headers=headers,
                                    )
                                    if upload_response.json().get("status") == "success":
                                        success_count += 1
                            except Exception as error:
                                st.toast(
                                    f"Error on {request_name}: {error}",
                                    icon="🚨",
                                )
                            progress_bar.progress(
                                current_iteration / total_iterations
                            )
                            time.sleep(1)

                    if success_count == total_iterations:
                        status_text.success(
                            f"All {success_count} packages were generated successfully."
                        )
                    else:
                        status_text.warning(
                            f"{success_count} of {total_iterations} packages succeeded."
                        )

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
        
        PERGOLA_RULES = {
            "Musky": {
                "rate": 3530.0,
                "desc": "Supply & Install Musky Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture."
            },
            "Pitch Pine": {
                "rate": 6470.0,
                "desc": "Supply & Install Pitch pine Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture."
            },
            "Khashamonium": {
                "rate": 11200.0,
                "desc": "Supply & Install Khashamonium Pergola (as per the attached drawing, standard pergola with Height 270cm), including fabrics and without lighting fixture."
            },
            "Retractable": {
                "rate": 67500.0,
                "desc": "Supply and install a landscape retractable pergola as per attached drawings including Motor and Fabric."
            }
        }

        if selected_request_type == "Land Extension":
            LAND_EXTENSION_RATE = st.selectbox(
                "Select Land Extension Rate (EGP/m²)",
                options=LAND_EXTENSION_RATES,
                format_func=lambda rate: f"EGP {rate:,.0f} / m²",
                key="land_extension_rate",
            )
        else:
            LAND_EXTENSION_RATE = LAND_EXTENSION_RATES[0]

        # Reset the custom editor cleanly whenever the request type changes.
        # The versioned widget key prevents Streamlit from restoring stale editor state
        # from a previously selected product/request type.
        if 'custom_boq_data' not in st.session_state or st.session_state.get('last_type') != selected_request_type:
            if selected_request_type == "Land Extension":
                initial_data = [{
                    'Description': 'Required Fees for Adding land extension area of for a/m unit as per attached Drawings.',
                    'Unit': 'M2',
                    'QTY': 0.0,
                    'Rate': LAND_EXTENSION_RATE
                }]
            elif selected_request_type == "Pergola":
                initial_data = [{
                    'Type': 'Musky',
                    'Description': PERGOLA_RULES['Musky']['desc'],
                    'Area / QTY (NO.)': 10.0,
                    'prev_Type': 'Musky'
                }]

                # Dedicated lightweight Pergola state. Each row receives a stable ID so
                # adding, deleting, changing type, and changing quantity do not rebuild
                # the full editor or lose the user's current values.
                st.session_state.pergola_rows = [{
                    '_id': 1,
                    'Type': 'Musky',
                    'Description': PERGOLA_RULES['Musky']['desc'],
                    'Area / QTY (NO.)': 10.0
                }]
                st.session_state.pergola_next_id = 2
            else:
                initial_data = [{
                    'Description': '',
                    'Unit': 'LS',
                    'QTY': 1.0,
                    'Rate': 0.0
                }]

            st.session_state.custom_boq_data = pd.DataFrame(initial_data)
            st.session_state.last_type = selected_request_type
            st.session_state.custom_editor_version = st.session_state.get('custom_editor_version', 0) + 1

        if selected_request_type == "Pergola":
            # ==============================================================
            # FAST PERGOLA EDITOR
            # ==============================================================
            # st.fragment isolates all Pergola interactions from the rest of
            # the application. Type, quantity, add, delete, and description
            # edits rerun only this small function instead of the entire app.

            if 'pergola_rows' not in st.session_state:
                st.session_state.pergola_rows = [{
                    '_id': 1,
                    'Type': 'Musky',
                    'Description': PERGOLA_RULES['Musky']['desc'],
                    'Area / QTY (NO.)': 10.0
                }]
                st.session_state.pergola_next_id = 2

            def add_default_pergola_row():
                """Append one ready-to-use Musky row without asking for a type."""
                row_id = int(st.session_state.get('pergola_next_id', 1))
                st.session_state.pergola_next_id = row_id + 1
                st.session_state.pergola_rows.append({
                    '_id': row_id,
                    'Type': 'Musky',
                    'Description': PERGOLA_RULES['Musky']['desc'],
                    'Area / QTY (NO.)': 10.0
                })

            def delete_pergola_row(row_id):
                """Delete a row before the fragment is redrawn."""
                st.session_state.pergola_rows = [
                    row for row in st.session_state.pergola_rows
                    if int(row.get('_id', -1)) != int(row_id)
                ]

                # Remove obsolete widget state for the deleted row.
                for prefix in ('pergola_type_', 'pergola_desc_', 'pergola_qty_'):
                    st.session_state.pop(f'{prefix}{row_id}', None)

            def update_pergola_type(row_id, type_key, desc_key, qty_key):
                """Synchronize description and quantity immediately after a type change."""
                selected_type = st.session_state.get(type_key, 'Musky')
                if selected_type not in PERGOLA_RULES:
                    selected_type = 'Musky'

                for row in st.session_state.get('pergola_rows', []):
                    if int(row.get('_id', -1)) != int(row_id):
                        continue

                    old_type = str(row.get('Type', 'Musky')).strip()
                    old_qty = pd.to_numeric(
                        row.get('Area / QTY (NO.)', 10.0), errors='coerce'
                    )
                    if pd.isna(old_qty) or float(old_qty) <= 0:
                        old_qty = 1.0 if old_type == 'Retractable' else 10.0

                    if selected_type == 'Retractable':
                        new_qty = 1.0
                    elif old_type == 'Retractable':
                        new_qty = 10.0
                    else:
                        new_qty = float(old_qty)

                    official_description = PERGOLA_RULES[selected_type]['desc']
                    row['Type'] = selected_type
                    row['Description'] = official_description
                    row['Area / QTY (NO.)'] = new_qty

                    # The callback runs before the fragment reruns, so these widget
                    # values are refreshed immediately without rerunning the full app.
                    st.session_state[desc_key] = official_description
                    st.session_state[qty_key] = new_qty
                    break

            # Use a no-op decorator only as a compatibility fallback. For the
            # optimized behavior, Streamlit 1.37 or later is recommended.
            fragment_decorator = getattr(st, 'fragment', lambda func: func)

            @fragment_decorator
            def render_pergola_editor():
                top_left, top_right = st.columns([1.25, 3.75])
                with top_left:
                    st.button(
                        "➕ Add New Row",
                        key="add_default_pergola_row",
                        on_click=add_default_pergola_row,
                        use_container_width=True,
                        help="Adds a new Musky Pergola row with 10 sqm by default."
                    )
                with top_right:
                    st.caption(
                        "New rows are added immediately as Musky. Type and quantity changes "
                        "recalculate inside this section only."
                    )

                rows = list(st.session_state.get('pergola_rows', []))

                if not rows:
                    st.info("No Pergola items. Press **Add New Row** to add a default Musky item.")
                    st.session_state.custom_boq_data = pd.DataFrame(
                        columns=['Type', 'Description', 'Area / QTY (NO.)', 'prev_Type']
                    )
                    st.session_state.staged_items = []
                    return

                # Table-style headings.
                header_cols = st.columns([0.35, 1.15, 3.25, 1.05, 0.65, 1.0, 1.15, 0.42])
                headers = ["No.", "Type", "Description", "Area / Qty", "Unit", "Rate", "Total", ""]
                for col, title in zip(header_cols, headers):
                    col.markdown(f"**{title}**")

                updated_rows = []
                final_rows = []

                for position, source_row in enumerate(rows, start=1):
                    row = dict(source_row)
                    row_id = int(row.get('_id', position))

                    current_type = str(row.get('Type', 'Musky')).strip()
                    if current_type not in PERGOLA_RULES:
                        current_type = 'Musky'

                    current_description = str(
                        row.get('Description', PERGOLA_RULES[current_type]['desc'])
                    ).strip()
                    if not current_description:
                        current_description = PERGOLA_RULES[current_type]['desc']

                    current_qty = pd.to_numeric(
                        row.get('Area / QTY (NO.)', 10.0), errors='coerce'
                    )
                    if pd.isna(current_qty) or float(current_qty) <= 0:
                        current_qty = 1.0 if current_type == 'Retractable' else 10.0
                    current_qty = float(current_qty)

                    type_key = f"pergola_type_{row_id}"
                    desc_key = f"pergola_desc_{row_id}"
                    qty_key = f"pergola_qty_{row_id}"

                    row_cols = st.columns([0.35, 1.15, 3.25, 1.05, 0.65, 1.0, 1.15, 0.42])
                    row_cols[0].markdown(f"**{position}**")

                    # Initialize widget state once. Afterwards, the type-change
                    # callback controls the official description and default quantity.
                    if type_key not in st.session_state:
                        st.session_state[type_key] = current_type
                    if desc_key not in st.session_state:
                        st.session_state[desc_key] = current_description
                    if qty_key not in st.session_state:
                        st.session_state[qty_key] = current_qty

                    selected_type = row_cols[1].selectbox(
                        f"Pergola Type {position}",
                        options=list(PERGOLA_RULES.keys()),
                        key=type_key,
                        on_change=update_pergola_type,
                        args=(row_id, type_key, desc_key, qty_key),
                        label_visibility="collapsed"
                    )

                    # The callback has already synchronized the source row before
                    # this fragment reruns. Always calculate from the selected type.
                    current_type = selected_type

                    entered_description = row_cols[2].text_area(
                        f"Description {position}",
                        key=desc_key,
                        height=76,
                        label_visibility="collapsed"
                    )

                    entered_qty = row_cols[3].number_input(
                        f"Area or Quantity {position}",
                        min_value=0.0,
                        step=1.0,
                        key=qty_key,
                        label_visibility="collapsed"
                    )

                    if current_type == 'Retractable':
                        pricing_qty = max(1, int(entered_qty))
                        unit = "Item"
                        boq_qty = float(pricing_qty)
                        rate = float(PERGOLA_RULES[current_type]['rate'])
                        total = boq_qty * rate
                    else:
                        pricing_qty = float(entered_qty)
                        base_rate = float(PERGOLA_RULES[current_type]['rate'])

                        # Standard Pergolas have a minimum charge of 10 sqm.
                        if pricing_qty < 10.0:
                            unit = "LS"
                            boq_qty = 1.0
                            rate = 10.0 * base_rate
                            total = rate
                        else:
                            unit = "SQM"
                            boq_qty = pricing_qty
                            rate = base_rate
                            total = pricing_qty * base_rate

                    row_cols[4].markdown(unit)
                    row_cols[5].markdown(f"{rate:,.2f}")
                    row_cols[6].markdown(f"**{total:,.2f}**")
                    row_cols[7].button(
                        "🗑️",
                        key=f"delete_pergola_{row_id}",
                        on_click=delete_pergola_row,
                        args=(row_id,),
                        help="Delete this row"
                    )

                    updated_rows.append({
                        '_id': row_id,
                        'Type': current_type,
                        'Description': entered_description.strip() or PERGOLA_RULES[current_type]['desc'],
                        'Area / QTY (NO.)': float(entered_qty)
                    })

                    final_rows.append({
                        'No.': position,
                        'Type': current_type,
                        'Description': entered_description.strip() or PERGOLA_RULES[current_type]['desc'],
                        'Area / QTY (NO.)': float(entered_qty),
                        'Unit': unit,
                        'QTY': boq_qty,
                        'Rate': rate,
                        'Total Amount': total,
                        'prev_Type': current_type
                    })

                # Store one clean source of truth for exports and PDF generation.
                st.session_state.pergola_rows = updated_rows
                final_df = pd.DataFrame(final_rows)
                st.session_state.custom_boq_data = pd.DataFrame([
                    {
                        'Type': row['Type'],
                        'Description': row['Description'],
                        'Area / QTY (NO.)': row['Area / QTY (NO.)'],
                        'prev_Type': row['Type']
                    }
                    for row in updated_rows
                ])
                st.session_state.staged_items = final_df.to_dict('records')

                subtotal = float(final_df['Total Amount'].sum()) if not final_df.empty else 0.0
                vat = subtotal * 0.14
                total_with_vat = subtotal + vat

                st.markdown("---")
                total_col, vat_col = st.columns(2)
                total_col.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
                vat_col.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

            render_pergola_editor()
            summary_df = pd.DataFrame(st.session_state.get('staged_items', []))

        else:
            is_land_extension = selected_request_type == "Land Extension"

            # Land Extension uses one centrally controlled rate. Re-apply it on every
            # rerun so an existing browser session or stale data-editor state cannot
            # override the official value.
            if is_land_extension:
                st.session_state.custom_boq_data = st.session_state.custom_boq_data.copy()
                st.session_state.custom_boq_data['Unit'] = 'M2'
                st.session_state.custom_boq_data['Rate'] = LAND_EXTENSION_RATE

            col_no, col_editor, col_total = st.columns([0.4, 3.5, 1.1])
            base_editor_key = f"custom_boq_editor_{st.session_state.get('custom_editor_version', 0)}"
            editor_key = (
                f"{base_editor_key}_land_extension_{int(LAND_EXTENSION_RATE)}"
                if is_land_extension
                else base_editor_key
            )

            with col_editor:
                edited_df = st.data_editor(
                    st.session_state.custom_boq_data,
                    key=editor_key,
                    num_rows="fixed" if is_land_extension else "dynamic",
                    disabled=["Unit", "Rate"] if is_land_extension else False,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Description": st.column_config.TextColumn("Description"),
                        "Unit": st.column_config.SelectboxColumn(
                            "Unit",
                            options=["SQM", "M2", "LM", "NO.", "LS", "Other"],
                            default="LS"
                        ),
                        "QTY": st.column_config.NumberColumn("QTY", min_value=0.0, default=1.0),
                        "Rate": st.column_config.NumberColumn("Rate", min_value=0.0, default=0.0)
                    }
                )

            # Enforce the official value again after the widget returns its data.
            # This is the final guard before totals and webhook payloads are created.
            if is_land_extension:
                edited_df = edited_df.copy()
                edited_df['Unit'] = 'M2'
                edited_df['Rate'] = LAND_EXTENSION_RATE

            final_df = edited_df.copy()
            final_df['QTY'] = pd.to_numeric(final_df['QTY'], errors='coerce').fillna(0.0)
            final_df['Rate'] = pd.to_numeric(final_df['Rate'], errors='coerce').fillna(0.0)
            final_df['Total Amount'] = final_df['QTY'] * final_df['Rate']
            final_df.insert(0, 'No.', range(1, len(final_df) + 1))
            st.session_state.custom_boq_data = edited_df

            with col_no:
                st.dataframe(final_df[['No.']], hide_index=True, use_container_width=True)

            with col_total:
                st.dataframe(
                    final_df[['Total Amount']],
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Total Amount": st.column_config.NumberColumn("Total Amount", format="%.2f EGP")
                    }
                )

            st.session_state.staged_items = final_df.to_dict('records')
            summary_df = final_df

            subtotal = final_df['Total Amount'].sum()
            vat = subtotal * 0.14
            total_with_vat = subtotal + vat

            col_t1, col_t2 = st.columns(2)
            if selected_request_type == "Land Extension":
                col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            else:
                col_t1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
                col_t2.metric("Total with 14% VAT (EGP)", f"{total_with_vat:,.2f} EGP")

    # --- SECTION 3B: QUOTATION-SPECIFIC TERMS & DURATION ---
    if st.session_state.staged_items:
        terms_lookup_name = selected_request_type
        if (
            selected_request_type in ["Roof Room", "Closing Double Height"]
            and "Lookup Name" in st.session_state.staged_items[0]
        ):
            terms_lookup_name = st.session_state.staged_items[0]["Lookup Name"]

        terms_request_col = df_terms.columns[0]
        terms_text_col = df_terms.columns[1] if len(df_terms.columns) > 1 else df_terms.columns[0]
        terms_match = df_terms[
            df_terms[terms_request_col].astype(str).str.strip().str.upper()
            == str(terms_lookup_name).strip().upper()
        ]
        default_terms_text = (
            str(terms_match.iloc[0][terms_text_col])
            if not terms_match.empty
            else ""
        )

        terms_context_key = f"{selected_unit}|{terms_lookup_name}"
        if st.session_state.get("terms_context_key") != terms_context_key:
            defaults, extraction_warnings = parse_terms_defaults(default_terms_text)
            st.session_state.terms_context_key = terms_context_key
            normalized_unit_id = str(selected_unit or "").upper()
            st.session_state.qt_delivery_stage = (
                defaults.delivery_stage
                if any(code in normalized_unit_id for code in ("RV", "RA", "QA"))
                else "Pre-Construction"
            )
            st.session_state.qt_master_duration_months = defaults.duration_months
            st.session_state.qt_duration_months = (
                6
                if st.session_state.qt_delivery_stage == "Pre-Construction"
                else defaults.duration_months
            )
            st.session_state.qt_last_delivery_stage = st.session_state.qt_delivery_stage
            st.session_state.qt_payment_method = defaults.payment_method
            st.session_state.qt_custom_payment_method = defaults.custom_payment_method
            st.session_state.qt_down_payment = defaults.down_payment_percent
            st.session_state.qt_due_event = defaults.due_event
            st.session_state.qt_custom_due_event = defaults.custom_due_event
            st.session_state.qt_payment_term_months = defaults.payment_term_months
            st.session_state.qt_frequency = defaults.installment_frequency
            st.session_state.qt_validity_days = defaults.offer_validity_days
            st.session_state.qt_extraction_warnings = extraction_warnings

        st.markdown("### Quotation Terms & Duration")
        st.caption(
            "The product's master Terms & Conditions remain unchanged. "
            "These controls create quotation-specific clauses only."
        )

        if not default_terms_text:
            st.error(
                f"No master Terms & Conditions were found for '{terms_lookup_name}'. "
                "Document generation is blocked until this request is added to the master sheet."
            )

        extraction_warnings = st.session_state.get("qt_extraction_warnings", [])
        if extraction_warnings:
            with st.expander("Review defaults that could not be extracted", expanded=False):
                for warning in extraction_warnings:
                    st.warning(warning)

        # Row 1: Delivery stage only.
        st.selectbox(
            "Delivery Stage",
            ["Pre-Construction", "Post-Delivery"],
            key="qt_delivery_stage",
        )

        # Apply the stage-specific default only when the stage changes. The user
        # can still edit the duration after the default is applied.
        current_delivery_stage = st.session_state.qt_delivery_stage
        if st.session_state.get("qt_last_delivery_stage") != current_delivery_stage:
            st.session_state.qt_duration_months = (
                6
                if current_delivery_stage == "Pre-Construction"
                else st.session_state.get("qt_master_duration_months", 0)
            )
            st.session_state.qt_last_delivery_stage = current_delivery_stage

        # Row 2: Only the editable payment-plan factors.
        payment_col1, payment_col2, payment_col3 = st.columns(3)
        with payment_col1:
            st.number_input(
                "Down Payment (%)",
                min_value=0.0,
                max_value=100.0,
                step=0.5,
                key="qt_down_payment",
            )
        with payment_col2:
            st.number_input(
                "Payment Term (Months)",
                min_value=1,
                step=1,
                key="qt_payment_term_months",
            )
        with payment_col3:
            st.selectbox(
                "Installment Frequency",
                ["Monthly", "Quarterly"],
                key="qt_frequency",
            )

        # Row 3: Duration / handover extension only.
        st.number_input(
            "Duration / Handover Extension (Months)",
            min_value=0,
            step=1,
            key="qt_duration_months",
        )

        validation_errors = validate_terms_values(
            st.session_state.qt_duration_months,
            st.session_state.qt_down_payment,
            st.session_state.qt_payment_term_months,
            st.session_state.qt_frequency,
            st.session_state.qt_validity_days,
            st.session_state.get("qt_custom_payment_method", ""),
            st.session_state.qt_payment_method,
            st.session_state.get("qt_custom_due_event", ""),
            st.session_state.qt_due_event,
        )
        if not default_terms_text:
            validation_errors.append("Master Terms & Conditions are required.")

        remaining_balance = 100.0 - float(st.session_state.qt_down_payment)
        installment_count = (
            int(st.session_state.qt_payment_term_months) // 3
            if st.session_state.qt_frequency == "Quarterly"
            and int(st.session_state.qt_payment_term_months) % 3 == 0
            else int(st.session_state.qt_payment_term_months)
        )
        metric_col1, metric_col2 = st.columns(2)
        metric_col1.metric("Remaining Balance", f"{remaining_balance:g}%")
        metric_col2.metric("Number of Installments", installment_count)

        generated_terms_text = ""
        quotation_terms_data = {}
        if not validation_errors:
            generated_terms_text, quotation_terms_data = generate_terms(
                default_terms_text,
                delivery_stage=st.session_state.qt_delivery_stage,
                duration_months=int(st.session_state.qt_duration_months),
                payment_method=st.session_state.qt_payment_method,
                custom_payment_method=st.session_state.get("qt_custom_payment_method", ""),
                down_payment_percent=float(st.session_state.qt_down_payment),
                due_event=st.session_state.qt_due_event,
                custom_due_event=st.session_state.get("qt_custom_due_event", ""),
                payment_term_months=int(st.session_state.qt_payment_term_months),
                installment_frequency=st.session_state.qt_frequency,
                offer_validity_days=int(st.session_state.qt_validity_days),
            )

        for validation_error in validation_errors:
            st.error(validation_error)

        st.session_state.generated_terms_and_conditions = generated_terms_text
        st.session_state.quotation_terms_data = quotation_terms_data
        st.session_state.terms_valid = not validation_errors

        st.markdown("#### Generated Terms & Conditions Preview")
        st.text_area(
            "Final quotation terms",
            value=generated_terms_text,
            height=320,
            disabled=True,
            label_visibility="collapsed",
        )

    st.divider()

    # --- SECTION 4: EXPORT BUTTONS (SHARED) ---
    if st.session_state.staged_items:
        summary_df = pd.DataFrame(st.session_state.staged_items)
        if not summary_df.empty:
            final_client_name = client_name.strip() if client_name.strip() else "Unassigned"
            st.markdown("##### Finalize Document Details")
            col_export1, col_export2 = st.columns(2)
            
            with col_export1:
                if st.button(
                    "🌐 Generate Official Google Doc via Webhook",
                    use_container_width=True,
                    type="primary",
                    disabled=not st.session_state.get("terms_valid", False),
                ):
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
                            "generatedTermsAndConditions": st.session_state.get(
                                "generated_terms_and_conditions", ""
                            ),
                            "quotationTermsOverrides": st.session_state.get(
                                "quotation_terms_data", {}
                            ),
                            "items": []
                        }

                        if selected_request_type == "Land Extension":
                            payload["landExtensionRate"] = float(LAND_EXTENSION_RATE)
                        
                        for item in st.session_state.staged_items:
                            payload["items"].append({
                                "description": item.get("Description", ""),
                                "unit": item.get("Unit", "LS"),
                                "qty": item.get("QTY", 1.0),
                                "rate": item.get("Rate", 0.0),
                                "baseKey": item.get("Base Key", ""),
                            })
                            
                        # Add packageCode and packageName to the payload for single Furniture exports so it triggers the Furniture template
                        if selected_request_type == "Furniture":
                            fur_package_name = st.session_state.staged_items[0].get('Lookup Name', '')
                            if "[L]" in fur_package_name: pkg_code = "P1"
                            elif "[D]" in fur_package_name: pkg_code = "P2"
                            elif "[R]" in fur_package_name: pkg_code = "P3"
                            else: pkg_code = "P1"
                            payload["action"] = "generateDocOnly"
                            payload["requestCategory"] = "Furniture"
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
                                        # Furniture 2-step: merge the quotation with
                                        # the exact selected room-design PDFs.
                                        merged_pdf = merge_pdf_base64(
                                            response_data["docBase64"],
                                            response_data.get("roomBase64s", []),
                                        )
                                        upload_payload = {
                                            "action": "uploadPdf",
                                            "requestCategory": "Furniture",
                                            "docName": response_data["docName"],
                                            "base64Pdf": merged_pdf,
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
                
                final_terms_text = st.session_state.get(
                    "generated_terms_and_conditions", ""
                )
                if final_terms_text:
                    pdf.set_font("Helvetica", "B", 11)
                    pdf.cell(0, 8, "Terms & Conditions:", ln=True)
                    pdf.set_font("Helvetica", "", 8)

                    def pdf_safe_text(value):
                        return str(value).encode("latin-1", errors="replace").decode("latin-1")

                    for term_line in final_terms_text.splitlines():
                        if term_line.strip():
                            # Reset the cursor after prior cells/multi-cells so fpdf has
                            # the full printable width available for every terms line.
                            pdf.set_x(pdf.l_margin)
                            pdf.multi_cell(0, 4, pdf_safe_text(term_line.strip()))
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
                    use_container_width=True,
                    disabled=not st.session_state.get("terms_valid", False),
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
