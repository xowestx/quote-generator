# ... existing code ...
    st.subheader("1. Project & Asset Context")
    col_u1, col_u2 = st.columns(2)
    
    with col_u1:
        # Enforce valid units to ALWAYS pull from the FACT table to guarantee exact string matching
        valid_units = [u for u in df_fact[fact_unit_id_col].unique() if str(u).strip() and str(u).strip().upper() not in ['NAN', 'NONE']]
        valid_units = sorted(list(set(valid_units)), key=lambda x: str(x))
        selected_unit = st.selectbox("Select Unit ID", valid_units)
        
        unit_meta_df = df_fact[df_fact[fact_unit_id_col] == selected_unit]
        unit_meta = unit_meta_df.iloc[0] if not unit_meta_df.empty else {}
        
    with col_u2:
        db_client_name = ""
        
        if df_clients is not None and not df_clients.empty:
            # 1. Identify exact columns in the CLIENT NAME tab
            name_col = next((c for c in df_clients.columns if 'NAME' in str(c).upper() or 'CLIENT' in str(c).upper()), None)
            c_unit_col = next((c for c in df_clients.columns if 'UNIT ID' in str(c).upper() or 'UNIT' in str(c).upper()), None)
            
            if name_col and c_unit_col:
                # 2. Simple, direct Pandas lookup (Match Unit ID -> Extract Client Name)
                target_u = str(selected_unit).strip().upper()
                
                # Standardize the column temporarily for a safe comparison
                df_clients['__clean_unit'] = df_clients[c_unit_col].astype(str).str.strip().str.upper()
                matched_rows = df_clients[df_clients['__clean_unit'] == target_u]
                
                if not matched_rows.empty:
                    raw_name = str(matched_rows.iloc[0][name_col]).strip()
                    
                    # 3. Filter out Pandas NaN artifacts
                    if raw_name.upper() not in ["", "NAN", "NONE", "NULL", "0.0", "0"]:
                        db_client_name = raw_name

        client_name = st.text_input("Client Name Reference (Optional)", value=db_client_name)

    # --- UPDATED DATA PARSING FOR NEW 'FACT' TAB COLUMNS ---
    unit_type = unit_meta.get('Unit Type', '')
    unit_design_type = unit_meta.get('Design Type', '')
# ... existing code ...
