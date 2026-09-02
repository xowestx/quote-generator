import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import re
import requests
import json

from terms_engine import (
    generate_terms,
    parse_terms_defaults,
    validate_terms_values,
)

# Verified Room-by-Room Furniture Rate Mapping
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

LAND_EXTENSION_RATES = (55000.0, 65000.0)

# A.C equipment source rates are dry cost. Quotations always use the selling
# rate (dry cost / 0.85). The accessories below are already selling rates.
AC_DRY_COST_FACTOR = 0.85
AC_FREON_PIPE_RATE = 1176.4
AC_CONCEALED_DUCT_RATE = 10588.2
AC_GRILLE_RATE = 2353.0
AC_FREON_METERS_MIN = 10.0
AC_FREON_METERS_MAX = 15.0
AC_GRILLE_METERS_MIN = 4.0
AC_GRILLE_METERS_MAX = 6.0

AC_RATE_CATALOG = (
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 1.5, "Dry Cost": 28640.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 2.25, "Dry Cost": 44025.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 3.0, "Dry Cost": 50000.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 1.5, "Dry Cost": 31205.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 2.25, "Dry Cost": 47610.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 3.0, "Dry Cost": 54055.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 1.5, "Dry Cost": 26985.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 2.25, "Dry Cost": 40530.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 2.25, "Dry Cost": 56010.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 3.0, "Dry Cost": 64525.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 5.0, "Dry Cost": 95185.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 6.0, "Dry Cost": 124605.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 7.5, "Dry Cost": 137510.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 2.25, "Dry Cost": 46700.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 3.0, "Dry Cost": 56105.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 5.0, "Dry Cost": 95035.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 6.0, "Dry Cost": 108350.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Concealed", "Cooling": "Hot & Cold", "Horse Power": 7.5, "Dry Cost": 119610.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 1.5, "Dry Cost": 24895.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 2.25, "Dry Cost": 37190.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 3.0, "Dry Cost": 44625.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 3.0, "Dry Cost": 48050.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 4.0, "Dry Cost": 84250.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 4.0, "Dry Cost": 74960.0},
    {"Model": "Carrier", "Type": "Inverter", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 5.0, "Dry Cost": 96810.0},
    {"Model": "Carrier", "Type": "Normal", "Installation Type": "Split", "Cooling": "Hot & Cold", "Horse Power": 5.0, "Dry Cost": 86125.0},
    {"Model": "Midea", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 1.5, "Dry Cost": 21900.0},
    {"Model": "Midea", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 2.25, "Dry Cost": 32900.0},
    {"Model": "Midea", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 3.0, "Dry Cost": 38800.0},
    {"Model": "Midea", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 4.0, "Dry Cost": 64800.0},
    {"Model": "Midea", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 5.0, "Dry Cost": 74500.0},
    {"Model": "Fresh", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 1.5, "Dry Cost": 18500.0},
    {"Model": "Fresh", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 2.25, "Dry Cost": 30000.0},
    {"Model": "Fresh", "Type": "Normal", "Installation Type": "Split", "Cooling": "Cold Only", "Horse Power": 3.0, "Dry Cost": 36000.0},
)


def ac_configuration_key(configuration):
    """Return the unique selectable equipment combination."""
    return "|".join(
        str(configuration[field])
        for field in (
            "Model",
            "Type",
            "Installation Type",
            "Cooling",
            "Horse Power",
        )
    )


def ac_catalog_options(field, filters=None):
    """Return valid dependent-selector values while preserving catalog order."""
    filters = filters or {}
    values = []
    for catalog_item in AC_RATE_CATALOG:
        if all(catalog_item.get(name) == value for name, value in filters.items()):
            value = catalog_item[field]
            if value not in values:
                values.append(value)
    return values


def build_ac_line_items(configuration):
    """Build transparent selling-price quotation lines for one A.C selection."""
    equipment_selling_rate = round(
        float(configuration["Dry Cost"]) / AC_DRY_COST_FACTOR,
        2,
    )
    unit_qty = int(configuration["Unit QTY"])
    freon_meters = float(configuration["Freon Meters per Unit"])
    horsepower = float(configuration["Horse Power"])
    horsepower_label = f"{horsepower:g}"
    config_key = ac_configuration_key(configuration)
    metadata = {
        "Model": configuration["Model"],
        "Type": configuration["Type"],
        "Installation Type": configuration["Installation Type"],
        "Cooling": configuration["Cooling"],
        "Horse Power": horsepower,
        "Configuration Key": config_key,
        "Lookup Name": "A.C",
    }

    lines = [
        {
            **metadata,
            "Component": "A.C Unit",
            "Description": (
                f"Supply and install {configuration['Model']} "
                f"{configuration['Type']} {configuration['Installation Type']} "
                f"air-conditioning unit, {configuration['Cooling']}, "
                f"{horsepower_label} HP."
            ),
            "Unit": "NO.",
            "QTY": float(unit_qty),
            "Rate": equipment_selling_rate,
            "Total Amount": float(unit_qty) * equipment_selling_rate,
        },
        {
            **metadata,
            "Component": "Freon Piping",
            "Description": (
                f"Supply and install refrigerant (Freon) piping for "
                f"{configuration['Model']} {horsepower_label} HP "
                "air-conditioning unit."
            ),
            "Unit": "M",
            "QTY": float(unit_qty) * freon_meters,
            "Rate": AC_FREON_PIPE_RATE,
            "Total Amount": float(unit_qty) * freon_meters * AC_FREON_PIPE_RATE,
        },
    ]

    if configuration["Installation Type"] == "Concealed":
        grille_meters = float(configuration["Grille Meters per Unit"])
        lines.extend(
            [
                {
                    **metadata,
                    "Component": "Ductwork & Insulation",
                    "Description": (
                        "Supply and install ductwork and insulation for "
                        f"{configuration['Model']} {horsepower_label} HP "
                        "concealed air-conditioning unit."
                    ),
                    "Unit": "NO.",
                    "QTY": float(unit_qty),
                    "Rate": AC_CONCEALED_DUCT_RATE,
                    "Total Amount": float(unit_qty) * AC_CONCEALED_DUCT_RATE,
                },
                {
                    **metadata,
                    "Component": "A.C Grille",
                    "Description": (
                        "Supply and install air-conditioning grille for "
                        f"{configuration['Model']} {horsepower_label} HP "
                        "concealed unit."
                    ),
                    "Unit": "M",
                    "QTY": float(unit_qty) * grille_meters,
                    "Rate": AC_GRILLE_RATE,
                    "Total Amount": float(unit_qty) * grille_meters * AC_GRILLE_RATE,
                },
            ]
        )

    return lines

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
        if selected_request_type == "A.C":
            st.session_state.ac_context = None
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
        st.caption(
            "Choose the furniture level, then add either a complete typology package "
            "or individual rooms. Each room can appear only once."
        )

        if st.session_state.get("furniture_ui_version") != "hierarchy_v2":
            st.session_state.furniture_ui_version = "hierarchy_v2"
            st.session_state.furniture_selection_revision = 0
            st.session_state.staged_items = []

        if "staged_items" not in st.session_state or not isinstance(
            st.session_state.staged_items, list
        ):
            st.session_state.staged_items = []

        st.markdown("##### 1. Furniture Level")
        furniture_level = st.radio(
            "Furniture Level",
            ["Luxury [L]", "Deluxe [D]", "Rent [R]"],
            horizontal=True,
            label_visibility="collapsed",
            key="furniture_level",
        )
        level_code = (
            "L" if "[L]" in furniture_level
            else "D" if "[D]" in furniture_level
            else "R"
        )
        level_name = (
            "Luxury" if level_code == "L"
            else "Deluxe" if level_code == "D"
            else "Rent"
        )
        level_multiplier = (
            1.0 if level_code == "L"
            else 0.7 if level_code == "D"
            else 0.35
        )

        st.markdown("##### 2. Selection Method")
        selection_method = st.radio(
            "Selection Method",
            ["Full Package", "Select Rooms Individually"],
            horizontal=True,
            label_visibility="collapsed",
            key="furniture_selection_method",
        )
        selection_revision = st.session_state.get(
            "furniture_selection_revision", 0
        )

        package_designs = {
            "L": {
                "Reception": "RECEPTION - P1",
                "Dining Room": "DINING ROOM - P2",
                "Living Room": "LIVING ROOM - P1",
                "Master Bedroom": "MASTER BEDROOM - P1",
                "Kids Bedroom": "KIDS BEDROOM - P1",
                "Nanny's Room": "NANNY'S ROOM",
                "Terrace": "TERRACE - P1",
            },
            "D": {
                "Reception": "RECEPTION - P2",
                "Dining Room": "DINING ROOM - P1",
                "Living Room": "LIVING ROOM - P2",
                "Master Bedroom": "MASTER BEDROOM - P3",
                "Kids Bedroom": "KIDS BEDROOM - P2",
                "Nanny's Room": "NANNY'S ROOM",
                "Terrace": "TERRACE - P2",
            },
            "R": {
                "Reception": "RECEPTION - P3",
                "Dining Room": "DINING ROOM - P2",
                "Living Room": "LIVING ROOM - P3",
                "Master Bedroom": "MASTER BEDROOM - P2",
                "Kids Bedroom": "KIDS BEDROOM - P2",
                "Nanny's Room": "NANNY'S ROOM",
                "Terrace": "TERRACE - P3",
            },
        }
        room_option_keys = {
            "Reception": [
                "RECEPTION - P1",
                "RECEPTION - P2",
                "RECEPTION - P3",
            ],
            "Dining Room": [
                "DINING ROOM - P1",
                "DINING ROOM - P2",
            ],
            "Living Room": [
                "LIVING ROOM - P1",
                "LIVING ROOM - P2",
                "LIVING ROOM - P3",
            ],
            "Master Bedroom": [
                "MASTER BEDROOM - P1",
                "MASTER BEDROOM - P2",
                "MASTER BEDROOM - P3",
            ],
            "Kids Bedroom": [
                "KIDS BEDROOM - P1",
                "KIDS BEDROOM - P2",
            ],
            "Nanny's Room": ["NANNY'S ROOM"],
            "Terrace": [
                "TERRACE - P1",
                "TERRACE - P2",
                "TERRACE - P3",
            ],
            "Outdoors": [
                "OUTDOORS - P1",
                "OUTDOORS - P2",
            ],
        }

        selected_room_items = []
        full_package_typology = None
        package_bedrooms = 1

        if selection_method == "Full Package":
            full_package_typology = st.selectbox(
                "Select Unit Typology",
                [
                    "1 Bedroom",
                    "2 Bedrooms",
                    "3 Bedrooms",
                    "3 Bedrooms+N",
                    "3 Bedrooms+N+F",
                    "4 Bedrooms+N",
                ],
                key="furniture_package_typology",
            )
            package_bedrooms = int(full_package_typology[0])
            package_room_quantities = [
                ("Reception", 1.0),
                ("Dining Room", 1.0),
                ("Terrace", 1.0),
                ("Master Bedroom", 1.0),
            ]
            if package_bedrooms > 1:
                package_room_quantities.append(
                    ("Kids Bedroom", float(package_bedrooms - 1))
                )
            if "+N" in full_package_typology:
                package_room_quantities.append(("Nanny's Room", 1.0))
            if "+F" in full_package_typology:
                package_room_quantities.insert(2, ("Living Room", 1.0))

            package_preview_rows = []
            for room_name, quantity in package_room_quantities:
                rate_key = package_designs[level_code][room_name]
                option_label = rate_key.replace(" - ", " ")
                rate = float(FURNITURE_RATES[rate_key]) * level_multiplier
                package_preview_rows.append({
                    "Room": room_name,
                    "Option": option_label,
                    "QTY": quantity,
                    "Rate (EGP)": rate,
                    "Total (EGP)": quantity * rate,
                })
                selected_room_items.append({
                    "Level": level_name,
                    "Room": room_name,
                    "Option": option_label,
                    "Description": (
                        f"Supply and install Furniture for {room_name}, "
                        f"{option_label}, including Curtains, rugs, cushions, "
                        "bed linens, table lamps, pendant lights, and mattresses."
                    ),
                    "Unit": "LS",
                    "QTY": quantity,
                    "Rate": rate,
                    "Lookup Name": (
                        f"{full_package_typology}, {furniture_level}"
                    ),
                    "Pricing Key": f"ROOM|{room_name.upper()}",
                    "Pricing Mode": "Full Package",
                })

            st.markdown("###### Full Package Preview")
            st.dataframe(
                pd.DataFrame(package_preview_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Room": st.column_config.TextColumn(
                        "Room",
                        disabled=True,
                    ),
                    "Option": st.column_config.TextColumn(
                        "Option",
                        disabled=True,
                    ),
                    "QTY": st.column_config.NumberColumn(
                        "QTY",
                        disabled=True,
                    ),
                    "Rate (EGP)": st.column_config.NumberColumn(
                        "Rate (EGP)",
                        format="%.2f",
                        disabled=True,
                    ),
                    "Total (EGP)": st.column_config.NumberColumn(
                        "Total (EGP)",
                        format="%.2f",
                        disabled=True,
                    ),
                },
            )
            st.caption(
                "The full package automatically selects one option for each "
                "applicable room."
            )

        else:
            st.markdown("###### Room-by-Room Selection")
            heading_add, heading_room, heading_option, heading_qty, heading_rate = (
                st.columns([0.65, 1.8, 1.8, 0.8, 1.25])
            )
            heading_add.markdown("**Add**")
            heading_room.markdown("**Room**")
            heading_option.markdown("**Single Option**")
            heading_qty.markdown("**QTY**")
            heading_rate.markdown("**Rate (EGP)**")

            for room_name, option_keys in room_option_keys.items():
                row_add, row_room, row_option, row_qty, row_rate = st.columns(
                    [0.65, 1.8, 1.8, 0.8, 1.25]
                )
                safe_room_key = (
                    room_name.lower()
                    .replace(" ", "_")
                    .replace("'", "")
                )
                with row_add:
                    include_room = st.checkbox(
                        f"Add {room_name}",
                        value=False,
                        key=(
                            f"furniture_add_{safe_room_key}_"
                            f"{selection_revision}"
                        ),
                        label_visibility="collapsed",
                    )
                with row_room:
                    st.markdown(room_name)
                with row_option:
                    if len(option_keys) == 1:
                        selected_rate_key = option_keys[0]
                        st.markdown(selected_rate_key.replace(" - ", " "))
                    else:
                        selected_rate_key = st.selectbox(
                            f"{room_name} Option",
                            option_keys,
                            format_func=lambda value: value.rsplit(" - ", 1)[-1],
                            key=(
                                f"furniture_option_{safe_room_key}_"
                                f"{selection_revision}"
                            ),
                            label_visibility="collapsed",
                        )
                with row_qty:
                    quantity = st.number_input(
                        f"{room_name} QTY",
                        min_value=1.0,
                        value=1.0,
                        step=1.0,
                        key=(
                            f"furniture_qty_{safe_room_key}_"
                            f"{selection_revision}"
                        ),
                        label_visibility="collapsed",
                    )
                rate = (
                    float(FURNITURE_RATES[selected_rate_key])
                    * level_multiplier
                )
                with row_rate:
                    st.markdown(f"{rate:,.2f}")

                if include_room:
                    option_label = selected_rate_key.replace(" - ", " ")
                    selected_room_items.append({
                        "Level": level_name,
                        "Room": room_name,
                        "Option": option_label,
                        "Description": (
                            f"Supply and install Furniture for {room_name}, "
                            f"{option_label}, including Curtains, rugs, cushions, "
                            "bed linens, table lamps, pendant lights, and mattresses."
                        ),
                        "Unit": "LS",
                        "QTY": float(quantity),
                        "Rate": rate,
                        "Lookup Name": f"Furniture - {level_name}",
                        "Pricing Key": f"ROOM|{room_name.upper()}",
                        "Pricing Mode": "Room Selection",
                    })

            st.caption(
                "Each room has one option selector, so two options for the same "
                "room cannot be selected."
            )

        addon_items = []
        with st.expander(
            "Optional Kitchen, Closets & Air Conditioning",
            expanded=False,
        ):
            kitchen_rate = (
                354350.00 if level_code == "L"
                else 270050.00 if level_code == "D"
                else 185750.00
            )
            closet_rate = (
                72800.00 if level_code == "L"
                else 72800.00 * 0.7 if level_code == "D"
                else 72800.00 * 0.5
            )
            default_kids_quantity = (
                float(max(package_bedrooms - 1, 1))
                if selection_method == "Full Package"
                else 1.0
            )
            default_bedroom_ac_quantity = (
                float(package_bedrooms)
                if selection_method == "Full Package"
                else 1.0
            )
            addon_specs = [
                {
                    "name": "Kitchen",
                    "qty": 1.0,
                    "rate": kitchen_rate,
                    "unit": "LS",
                    "description": (
                        f"Supply and install kitchen with {level_name} finish "
                        "as per approved sample and selected design."
                    ),
                },
                {
                    "name": "Master Bedroom Closets",
                    "qty": 2.0,
                    "rate": closet_rate,
                    "unit": "NO.",
                    "description": (
                        f"Supply and install {level_name} closets for "
                        "Master Bedroom."
                    ),
                },
                {
                    "name": "Kids Bedroom Closets",
                    "qty": default_kids_quantity,
                    "rate": closet_rate,
                    "unit": "NO.",
                    "description": (
                        f"Supply and install {level_name} closets for "
                        "Kids Bedrooms."
                    ),
                },
                {
                    "name": "Nanny's Room Closet",
                    "qty": 1.0,
                    "rate": 22500.00,
                    "unit": "NO.",
                    "description": (
                        "Supply and install melamine-faced chipboard wardrobe "
                        "for Nanny's Room."
                    ),
                },
                {
                    "name": "Reception AC 3 HP",
                    "qty": 1.0,
                    "rate": 60694.40,
                    "unit": "NO.",
                    "description": (
                        "Supply and install 3 hp Carrier AC split unit for "
                        "Reception, including freon piping required."
                    ),
                },
                {
                    "name": "Bedroom AC 1.5 HP",
                    "qty": default_bedroom_ac_quantity,
                    "rate": 38772.20,
                    "unit": "NO.",
                    "description": (
                        "Supply and install 1.5 hp Carrier AC split unit for "
                        "Bedrooms, including freon piping required."
                    ),
                },
            ]

            addon_heading_add, addon_heading_name, addon_heading_qty, addon_heading_rate = (
                st.columns([0.65, 3.6, 0.8, 1.25])
            )
            addon_heading_add.markdown("**Add**")
            addon_heading_name.markdown("**Optional Item**")
            addon_heading_qty.markdown("**QTY**")
            addon_heading_rate.markdown("**Rate (EGP)**")

            for addon in addon_specs:
                addon_add, addon_name, addon_qty, addon_rate = st.columns(
                    [0.65, 3.6, 0.8, 1.25]
                )
                safe_addon_key = (
                    addon["name"].lower()
                    .replace(" ", "_")
                    .replace("'", "")
                    .replace(".", "")
                )
                with addon_add:
                    include_addon = st.checkbox(
                        f"Add {addon['name']}",
                        value=False,
                        key=(
                            f"furniture_addon_add_{safe_addon_key}_"
                            f"{selection_revision}"
                        ),
                        label_visibility="collapsed",
                    )
                with addon_name:
                    st.markdown(addon["name"])
                with addon_qty:
                    addon_quantity = st.number_input(
                        f"{addon['name']} QTY",
                        min_value=1.0,
                        value=float(addon["qty"]),
                        step=1.0,
                        key=(
                            f"furniture_addon_qty_{safe_addon_key}_"
                            f"{selection_revision}"
                        ),
                        label_visibility="collapsed",
                    )
                with addon_rate:
                    st.markdown(f"{addon['rate']:,.2f}")

                if include_addon:
                    addon_items.append({
                        "Level": level_name,
                        "Room": "Optional Add-on",
                        "Option": addon["name"],
                        "Description": addon["description"],
                        "Unit": addon["unit"],
                        "QTY": float(addon_quantity),
                        "Rate": float(addon["rate"]),
                        "Lookup Name": (
                            f"{full_package_typology}, {furniture_level}"
                            if full_package_typology
                            else f"Furniture - {level_name}"
                        ),
                        "Pricing Key": (
                            f"ADDON|{addon['name'].upper()}"
                        ),
                        "Pricing Mode": "Optional Add-on",
                    })

        if st.button(
            "➕ Add Configuration to Quotation",
            type="primary",
            use_container_width=True,
        ):
            candidate_items = selected_room_items + addon_items
            if not candidate_items:
                st.warning(
                    "Select a full package or check at least one room or "
                    "optional item."
                )
            else:
                existing_keys = {
                    str(item.get("Pricing Key", ""))
                    for item in st.session_state.staged_items
                }
                duplicate_items = [
                    item["Room"]
                    if item["Room"] != "Optional Add-on"
                    else item["Option"]
                    for item in candidate_items
                    if item["Pricing Key"] in existing_keys
                ]
                candidate_keys = [
                    item["Pricing Key"] for item in candidate_items
                ]
                duplicate_candidate_keys = {
                    key for key in candidate_keys
                    if candidate_keys.count(key) > 1
                }

                if duplicate_items or duplicate_candidate_keys:
                    duplicate_labels = sorted(set(duplicate_items))
                    if duplicate_candidate_keys:
                        duplicate_labels.extend(
                            sorted(duplicate_candidate_keys)
                        )
                    st.error(
                        "Duplicate selection blocked. Remove or edit the "
                        "existing row before adding: "
                        + ", ".join(duplicate_labels)
                    )
                else:
                    for item in candidate_items:
                        item["No."] = (
                            len(st.session_state.staged_items) + 1
                        )
                        item["Total Amount"] = (
                            float(item["QTY"]) * float(item["Rate"])
                        )
                        st.session_state.staged_items.append(item)
                    st.session_state.furniture_selection_revision += 1
                    st.toast(
                        f"{len(candidate_items)} item(s) added successfully."
                    )
                    st.rerun()

        if st.session_state.staged_items:
            st.markdown("### 📊 Quotation Items")
            st.info(
                "Quantities can be edited and rows can be deleted. "
                "Level, room, option and rate are locked."
            )
            result_columns = [
                "No.",
                "Level",
                "Room",
                "Option",
                "Description",
                "Unit",
                "QTY",
                "Rate",
                "Total Amount",
                "Lookup Name",
                "Pricing Key",
                "Pricing Mode",
            ]
            df_staged = pd.DataFrame(
                st.session_state.staged_items
            ).reindex(columns=result_columns)
            edited_df = st.data_editor(
                df_staged,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",
                key="furniture_results_hierarchy_v2",
                column_config={
                    "Lookup Name": None,
                    "Pricing Key": None,
                    "Pricing Mode": None,
                    "No.": st.column_config.NumberColumn(
                        "No.",
                        disabled=True,
                    ),
                    "Level": st.column_config.TextColumn(
                        "Level",
                        disabled=True,
                    ),
                    "Room": st.column_config.TextColumn(
                        "Room",
                        disabled=True,
                    ),
                    "Option": st.column_config.TextColumn(
                        "Option",
                        disabled=True,
                    ),
                    "Description": st.column_config.TextColumn(
                        "Description",
                        disabled=True,
                    ),
                    "Unit": st.column_config.TextColumn(
                        "Unit",
                        disabled=True,
                    ),
                    "QTY": st.column_config.NumberColumn(
                        "QTY",
                        min_value=1.0,
                        step=1.0,
                    ),
                    "Rate": st.column_config.NumberColumn(
                        "Rate",
                        format="%.2f",
                        disabled=True,
                    ),
                    "Total Amount": st.column_config.NumberColumn(
                        "Total Amount",
                        format="%.2f",
                        disabled=True,
                    ),
                },
                disabled=[
                    "No.",
                    "Level",
                    "Room",
                    "Option",
                    "Description",
                    "Unit",
                    "Rate",
                    "Total Amount",
                    "Lookup Name",
                    "Pricing Key",
                    "Pricing Mode",
                ],
            )

            updated_items = []
            seen_pricing_keys = set()
            for _, row in edited_df.reset_index(drop=True).iterrows():
                item = row.to_dict()
                pricing_key = item.get("Pricing Key")
                if pd.isna(pricing_key) or not str(pricing_key).strip():
                    continue
                pricing_key = str(pricing_key)
                if pricing_key in seen_pricing_keys:
                    continue
                seen_pricing_keys.add(pricing_key)
                item["Pricing Key"] = pricing_key
                item["No."] = len(updated_items) + 1
                item["QTY"] = float(item.get("QTY", 1.0))
                item["Rate"] = float(item.get("Rate", 0.0))
                item["Total Amount"] = item["QTY"] * item["Rate"]
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
            total_col1, total_col2 = st.columns(2)
            total_col1.metric("Total (EGP)", f"{subtotal:,.2f} EGP")
            total_col2.metric(
                "Total with 14% VAT (EGP)",
                f"{total_with_vat:,.2f} EGP",
            )

            if st.button(
                "❌ Clear Furniture Quotation",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.staged_items = []
                st.session_state.furniture_selection_revision += 1
                st.rerun()

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

    elif selected_request_type == "A.C":
        st.markdown("### ❄️ A.C Quotation Builder")
        st.caption(
            "Select the equipment in order, then set the quantity and required "
            "installation lengths. All displayed rates are selling rates."
        )

        ac_context = f"{selected_unit}|ac_configurator_v1"
        if st.session_state.get("ac_context") != ac_context:
            st.session_state.ac_context = ac_context
            st.session_state.ac_configurations = []
            st.session_state.ac_selection_revision = 0
            st.session_state.staged_items = []

        if "ac_configurations" not in st.session_state or not isinstance(
            st.session_state.ac_configurations,
            list,
        ):
            st.session_state.ac_configurations = []
        if "ac_selection_revision" not in st.session_state:
            st.session_state.ac_selection_revision = 0

        st.markdown("##### 1. Select A.C Equipment")
        selector_col1, selector_col2, selector_col3, selector_col4, selector_col5 = (
            st.columns(5)
        )

        with selector_col1:
            ac_model = st.selectbox(
                "Model",
                ac_catalog_options("Model"),
                key=f"ac_model_{st.session_state.ac_selection_revision}",
            )

        with selector_col2:
            ac_type_options = ac_catalog_options(
                "Type",
                {"Model": ac_model},
            )
            ac_type = st.selectbox(
                "Type",
                ac_type_options,
                key=(
                    f"ac_type_{ac_model}_"
                    f"{st.session_state.ac_selection_revision}"
                ),
            )

        with selector_col3:
            installation_filters = {
                "Model": ac_model,
                "Type": ac_type,
            }
            ac_installation_options = ac_catalog_options(
                "Installation Type",
                installation_filters,
            )
            ac_installation = st.selectbox(
                "Installation Type",
                ac_installation_options,
                key=(
                    f"ac_installation_{ac_model}_{ac_type}_"
                    f"{st.session_state.ac_selection_revision}"
                ),
            )

        with selector_col4:
            cooling_filters = {
                **installation_filters,
                "Installation Type": ac_installation,
            }
            ac_cooling_options = ac_catalog_options(
                "Cooling",
                cooling_filters,
            )
            ac_cooling = st.selectbox(
                "Cooling",
                ac_cooling_options,
                key=(
                    f"ac_cooling_{ac_model}_{ac_type}_{ac_installation}_"
                    f"{st.session_state.ac_selection_revision}"
                ),
            )

        with selector_col5:
            horsepower_filters = {
                **cooling_filters,
                "Cooling": ac_cooling,
            }
            ac_horsepower_options = ac_catalog_options(
                "Horse Power",
                horsepower_filters,
            )
            ac_horsepower = st.selectbox(
                "Horse Power",
                ac_horsepower_options,
                format_func=lambda value: f"{float(value):g} HP",
                key=(
                    f"ac_horsepower_{ac_model}_{ac_type}_"
                    f"{ac_installation}_{ac_cooling}_"
                    f"{st.session_state.ac_selection_revision}"
                ),
            )

        selected_catalog_item = next(
            item
            for item in AC_RATE_CATALOG
            if all(
                item[field] == value
                for field, value in {
                    "Model": ac_model,
                    "Type": ac_type,
                    "Installation Type": ac_installation,
                    "Cooling": ac_cooling,
                    "Horse Power": ac_horsepower,
                }.items()
            )
        )

        st.markdown("##### 2. Set Quantity & Installation")
        quantity_columns = st.columns(3)
        selection_suffix = (
            f"{ac_model}_{ac_type}_{ac_installation}_{ac_cooling}_"
            f"{ac_horsepower}_{st.session_state.ac_selection_revision}"
        )
        with quantity_columns[0]:
            ac_unit_qty = st.number_input(
                "A.C Unit QTY",
                min_value=1,
                max_value=100,
                value=1,
                step=1,
                key=f"ac_unit_qty_{selection_suffix}",
            )
        with quantity_columns[1]:
            freon_meters_per_unit = st.number_input(
                "Freon Piping per Unit (m)",
                min_value=AC_FREON_METERS_MIN,
                max_value=AC_FREON_METERS_MAX,
                value=AC_FREON_METERS_MIN,
                step=0.5,
                help="Allowed range: 10–15 meters for every A.C unit.",
                key=f"ac_freon_meters_{selection_suffix}",
            )

        grille_meters_per_unit = None
        with quantity_columns[2]:
            if ac_installation == "Concealed":
                grille_meters_per_unit = st.number_input(
                    "A.C Grille per Unit (m)",
                    min_value=AC_GRILLE_METERS_MIN,
                    max_value=AC_GRILLE_METERS_MAX,
                    value=AC_GRILLE_METERS_MIN,
                    step=0.5,
                    help="Allowed range: 4–6 meters for every concealed unit.",
                    key=f"ac_grille_meters_{selection_suffix}",
                )
            else:
                st.text_input(
                    "Concealed Extras",
                    value="Not required for Split",
                    disabled=True,
                    key=f"ac_concealed_not_required_{selection_suffix}",
                )

        preview_configuration = {
            **selected_catalog_item,
            "Unit QTY": int(ac_unit_qty),
            "Freon Meters per Unit": float(freon_meters_per_unit),
            "Grille Meters per Unit": (
                float(grille_meters_per_unit)
                if grille_meters_per_unit is not None
                else 0.0
            ),
        }
        preview_lines = build_ac_line_items(preview_configuration)
        equipment_preview_total = preview_lines[0]["Total Amount"]
        piping_preview_total = preview_lines[1]["Total Amount"]
        concealed_preview_total = sum(
            line["Total Amount"]
            for line in preview_lines
            if line["Component"] in ("Ductwork & Insulation", "A.C Grille")
        )
        configuration_preview_total = sum(
            line["Total Amount"]
            for line in preview_lines
        )

        preview_columns = st.columns(4)
        preview_columns[0].metric(
            "A.C Units",
            f"{equipment_preview_total:,.2f} EGP",
        )
        preview_columns[1].metric(
            "Freon Piping",
            f"{piping_preview_total:,.2f} EGP",
        )
        preview_columns[2].metric(
            "Concealed Extras",
            (
                f"{concealed_preview_total:,.2f} EGP"
                if ac_installation == "Concealed"
                else "Not required"
            ),
        )
        preview_columns[3].metric(
            "Configuration Total",
            f"{configuration_preview_total:,.2f} EGP",
        )

        selected_configuration_key = ac_configuration_key(
            preview_configuration
        )
        existing_configuration_keys = {
            ac_configuration_key(configuration)
            for configuration in st.session_state.ac_configurations
        }
        duplicate_configuration = (
            selected_configuration_key in existing_configuration_keys
        )

        if duplicate_configuration:
            st.warning(
                "This exact A.C configuration is already in the quotation. "
                "Remove it first if you need to replace its quantity or lengths."
            )

        if st.button(
            "➕ Add A.C Configuration",
            type="primary",
            use_container_width=True,
            disabled=duplicate_configuration,
        ):
            st.session_state.ac_configurations.append(
                preview_configuration.copy()
            )
            st.session_state.ac_selection_revision += 1
            st.rerun()

        st.markdown("##### 3. Selected A.C Configurations")
        if not st.session_state.ac_configurations:
            st.info("No A.C configuration has been added yet.")
            st.session_state.staged_items = []
        else:
            for configuration_index, configuration in enumerate(
                st.session_state.ac_configurations
            ):
                summary_columns = st.columns([4, 2, 2, 1])
                summary_columns[0].markdown(
                    f"**{configuration['Model']} · {configuration['Type']} · "
                    f"{configuration['Installation Type']} · "
                    f"{configuration['Cooling']} · "
                    f"{float(configuration['Horse Power']):g} HP**"
                )
                summary_columns[1].write(
                    f"Units: {int(configuration['Unit QTY'])}"
                )
                length_summary = (
                    f"Freon: {float(configuration['Freon Meters per Unit']):g} m/unit"
                )
                if configuration["Installation Type"] == "Concealed":
                    length_summary += (
                        f" · Grille: "
                        f"{float(configuration['Grille Meters per Unit']):g} m/unit"
                    )
                summary_columns[2].write(length_summary)
                if summary_columns[3].button(
                    "Remove",
                    key=(
                        f"remove_ac_configuration_"
                        f"{st.session_state.ac_selection_revision}_"
                        f"{configuration_index}"
                    ),
                ):
                    st.session_state.ac_configurations.pop(configuration_index)
                    st.session_state.ac_selection_revision += 1
                    st.rerun()

            ac_staged_items = []
            for configuration in st.session_state.ac_configurations:
                ac_staged_items.extend(build_ac_line_items(configuration))

            for item_number, item in enumerate(ac_staged_items, start=1):
                item["No."] = item_number
            st.session_state.staged_items = ac_staged_items

            result_columns = [
                "No.",
                "Component",
                "Model",
                "Type",
                "Installation Type",
                "Cooling",
                "Horse Power",
                "Description",
                "Unit",
                "QTY",
                "Rate",
                "Total Amount",
            ]
            st.dataframe(
                pd.DataFrame(st.session_state.staged_items)[result_columns],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Horse Power": st.column_config.NumberColumn(
                        "Horse Power",
                        format="%.2f HP",
                    ),
                    "QTY": st.column_config.NumberColumn(
                        "QTY",
                        format="%.2f",
                    ),
                    "Rate": st.column_config.NumberColumn(
                        "Selling Rate (EGP)",
                        format="%.2f",
                    ),
                    "Total Amount": st.column_config.NumberColumn(
                        "Total Amount (EGP)",
                        format="%.2f",
                    ),
                },
            )

            ac_subtotal = sum(
                float(item["Total Amount"])
                for item in st.session_state.staged_items
            )
            ac_vat = ac_subtotal * 0.14
            ac_total_with_vat = ac_subtotal + ac_vat
            total_columns = st.columns(2)
            total_columns[0].metric(
                "Total (EGP)",
                f"{ac_subtotal:,.2f} EGP",
            )
            total_columns[1].metric(
                "Total with 14% VAT (EGP)",
                f"{ac_total_with_vat:,.2f} EGP",
            )

            if st.button(
                "❌ Clear A.C Quotation",
                type="secondary",
                use_container_width=True,
            ):
                st.session_state.ac_configurations = []
                st.session_state.staged_items = []
                st.session_state.ac_selection_revision += 1
                st.rerun()

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
                            })
                            
                        if selected_request_type == "Furniture":
                            payload["requestCategory"] = "Furniture"
                                
                        try:
                            headers = {"Content-Type": "application/json"}
                            response = requests.post(WEBHOOK_URL, data=json.dumps(payload), headers=headers)
                            
                            if response.status_code == 200:
                                response_data = response.json()
                                
                                # Process standard quote
                                if response_data.get("status") == "success":
                                    st.success("✅ Quotation Generated Successfully!")
                                    st.session_state.doc_url = response_data.get("docUrl")
                                    st.session_state.pdf_url = response_data.get("pdfUrl")
                                    st.rerun()
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
