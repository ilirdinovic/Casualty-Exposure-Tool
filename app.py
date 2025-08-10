import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO

st.set_page_config(page_title="Casualty Exposure — Live Table", layout="wide")

DEFAULT_PATH = "Casualty_Exposure_Dummy_Universe.xlsx"

@st.cache_data
def load_data_from_xlsx(file_like):
    df = pd.read_excel(file_like, sheet_name="Policies")
    return df

@st.cache_data
def load_data_from_csv(file_like):
    df = pd.read_csv(file_like)
    return df

def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    # Ensure expected types and handy derived columns
    if "Effective_Date" in df.columns:
        df["Effective_Date"] = pd.to_datetime(df["Effective_Date"], errors="coerce")
    if "Expiration_Date" in df.columns:
        df["Expiration_Date"] = pd.to_datetime(df["Expiration_Date"], errors="coerce")

    for c in ["Annual_Premium","Limit_Per_Occurrence","Limit_Aggregate","Attachment_Point","Share"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Derived helpers
    if "MGA" in df.columns:
        df["MGA_Flag"] = np.where(df["MGA"].fillna("N/A")=="N/A","No MGA","MGA")

    def band_limit(x):
        if pd.isna(x): return None
        if x <= 1_000_000: return "$1M"
        if x <= 2_000_000: return "$2M"
        if x <= 3_000_000: return "$3M"
        if x <= 5_000_000: return "$5M"
        return "$10M+"

    def band_attach(x):
        if pd.isna(x): return None
        if x == 0: return "$0 (Primary)"
        if x <= 1_000_000: return "$1M"
        if x <= 2_000_000: return "$2M"
        if x <= 5_000_000: return "$5M"
        return "$10M+"

    if "Limit_Per_Occurrence" in df.columns:
        df["Limit_Band"] = df["Limit_Per_Occurrence"].apply(band_limit)
    if "Attachment_Point" in df.columns:
        df["Attachment_Band"] = df["Attachment_Point"].apply(band_attach)

    return df

st.title("Casualty Exposure — Interactive Live Table")

with st.sidebar:
    st.header("Upload Exposure Data")
    st.caption("Upload your policy listing as Excel (.xlsx, sheet 'Policies') or CSV. "
               "If skipped, the app tries to load 'Casualty_Exposure_Dummy_Universe.xlsx' from the repo root.")
    uploaded = st.file_uploader("Upload file", type=["xlsx","csv"])

df = None
if uploaded is not None:
    name = uploaded.name.lower()
    try:
        if name.endswith(".xlsx"):
            df = load_data_from_xlsx(uploaded)
        elif name.endswith(".csv"):
            df = load_data_from_csv(uploaded)
        else:
            st.error("Unsupported file type. Please upload .xlsx or .csv.")
    except Exception as e:
        st.error(f"Could not read the uploaded file: {e}")
else:
    # fallback to repo file if present
    try:
        with open(DEFAULT_PATH, "rb") as f:
            df = load_data_from_xlsx(f)
        st.info("Loaded default sample: Casualty_Exposure_Dummy_Universe.xlsx")
    except Exception:
        st.warning("No file uploaded and default sample not found. Upload a file to proceed.")
        st.stop()

df = coerce_types(df)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    def options(col):
        return sorted([x for x in df[col].dropna().unique().tolist()]) if col in df.columns else []
    uy = st.multiselect("Underwriting Year (UY)", options("UY"), default=options("UY"))
    lob = st.multiselect("LOB", options("LOB"))
    sublob = st.multiselect("Sub LOB", options("Sub_LOB"))
    ptype = st.multiselect("Policy Type", options("Policy_Type"))
    business_id = st.multiselect("Business ID (Treaty)", options("Business_ID"))
    cedent = st.multiselect("Ceding Company", options("Ceding_Company"))
    mga = st.multiselect("MGA", options("MGA"))
    venue = st.multiselect("Venue (State)", options("Venue"))
    st.divider()
    limit_band = st.multiselect("Limit Band", options("Limit_Band"))
    attach_band = st.multiselect("Attachment Band", options("Attachment_Band"))
    st.caption("Leave a filter empty to include all values.")

def isin_or_all(series, values):
    return series.isin(values) if values else pd.Series(True, index=series.index)

mask = pd.Series(True, index=df.index)
if "UY" in df.columns: mask &= isin_or_all(df["UY"], uy)
if "LOB" in df.columns: mask &= isin_or_all(df["LOB"], lob)
if "Sub_LOB" in df.columns: mask &= isin_or_all(df["Sub_LOB"], sublob)
if "Policy_Type" in df.columns: mask &= isin_or_all(df["Policy_Type"], ptype)
if "Business_ID" in df.columns: mask &= isin_or_all(df["Business_ID"], business_id)
if "Ceding_Company" in df.columns: mask &= isin_or_all(df["Ceding_Company"], cedent)
if "MGA" in df.columns: mask &= isin_or_all(df["MGA"], mga)
if "Venue" in df.columns: mask &= isin_or_all(df["Venue"], venue)
if "Limit_Band" in df.columns: mask &= isin_or_all(df["Limit_Band"], limit_band)
if "Attachment_Band" in df.columns: mask &= isin_or_all(df["Attachment_Band"], attach_band)

f = df.loc[mask].copy()

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Policies", f.shape[0])
if "Annual_Premium" in f.columns:
    k2.metric("Premium (GWP)", f"${f['Annual_Premium'].sum():,.0f}")
else:
    k2.metric("Premium (GWP)", "—")
if set(["Limit_Per_Occurrence","Share"]).issubset(f.columns):
    k3.metric("Exposed Limit", f"${(f['Limit_Per_Occurrence']*f['Share']).sum():,.0f}")
else:
    k3.metric("Exposed Limit", "—")
if "Policy_Type" in f.columns and len(f) > 0:
    k4.metric("% Primary", f"{100*f['Policy_Type'].eq('Primary').mean():.1f}%")
else:
    k4.metric("% Primary", "—")
if "Business_ID" in f.columns:
    k5.metric("Treaties", f['Business_ID'].nunique())
else:
    k5.metric("Treaties", "—")

st.divider()

st.subheader("Filtered Policies (live table)")
st.dataframe(f, use_container_width=True, hide_index=True)

# Optional: download filtered
def df_to_excel_bytes(df):
    out = BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format='yyyy-mm-dd', date_format='yyyy-mm-dd') as writer:
        df.to_excel(writer, sheet_name="Policies_Filtered", index=False)
    out.seek(0)
    return out

c1, c2 = st.columns(2)
with c1:
    st.download_button("Download filtered (Excel)", data=df_to_excel_bytes(f), file_name="Filtered_Policies.xlsx")
with c2:
    st.download_button("Download filtered (CSV)", data=f.to_csv(index=False).encode("utf-8"), file_name="Filtered_Policies.csv")

st.caption("Upload at left to replace the sample. Filters update the live table instantly.")
