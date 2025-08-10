import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="Casualty Exposure Table", layout="wide")

@st.cache_data
def load_data(path: str):
    df = pd.read_excel(path, sheet_name="Policies")
    # types
    df["Effective_Date"] = pd.to_datetime(df["Effective_Date"])
    df["Expiration_Date"] = pd.to_datetime(df["Expiration_Date"])
    num_cols = ["Annual_Premium","Limit_Per_Occurrence","Limit_Aggregate","Attachment_Point","Share"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # derived helpers for filtering
    df["MGA_Flag"] = np.where(df["MGA"].fillna("N/A") == "N/A", "No MGA", "MGA")
    # bands (optional, useful filters)
    def band_limit(x):
        if x <= 1_000_000: return "$1M"
        if x <= 2_000_000: return "$2M"
        if x <= 3_000_000: return "$3M"
        if x <= 5_000_000: return "$5M"
        return "$10M+"
    def band_attach(x):
        if x == 0: return "$0 (Primary)"
        if x <= 1_000_000: return "$1M"
        if x <= 2_000_000: return "$2M"
        if x <= 5_000_000: return "$5M"
        return "$10M+"
    df["Limit_Band"] = df["Limit_Per_Occurrence"].apply(band_limit)
    df["Attachment_Band"] = df["Attachment_Point"].apply(band_attach)
    return df

DATA_PATH = "Casualty_Exposure_Dummy_Universe.xlsx"

st.title("Casualty Exposure — Interactive Table")

# Load once (cached)
df = load_data(DATA_PATH)

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    uy = st.multiselect("Underwriting Year (UY)", sorted(df["UY"].unique().tolist()),
                        default=sorted(df["UY"].unique().tolist()))
    lob = st.multiselect("LOB", sorted(df["LOB"].unique().tolist()))
    sublob = st.multiselect("Sub LOB", sorted(df["Sub_LOB"].unique().tolist()))
    ptype = st.multiselect("Policy Type", sorted(df["Policy_Type"].unique().tolist()))
    business_id = st.multiselect("Business ID (Treaty)", sorted(df["Business_ID"].unique().tolist()))
    cedent = st.multiselect("Ceding Company", sorted(df["Ceding_Company"].unique().tolist()))
    mga = st.multiselect("MGA", sorted(df["MGA"].unique().tolist()))
    venue = st.multiselect("Venue (State)", sorted(df["Venue"].unique().tolist()))
    st.divider()
    limit_band = st.multiselect("Limit Band", sorted(df["Limit_Band"].unique().tolist()))
    attach_band = st.multiselect("Attachment Band", sorted(df["Attachment_Band"].unique().tolist()))
    st.caption("Tip: leave filters blank to include all values.")

# Efficient filter helper
def isin_or_all(series, values):
    return series.isin(values) if values else pd.Series([True]*len(series), index=series.index)

mask = (
    isin_or_all(df["UY"], uy) &
    isin_or_all(df["LOB"], lob) &
    isin_or_all(df["Sub_LOB"], sublob) &
    isin_or_all(df["Policy_Type"], ptype) &
    isin_or_all(df["Business_ID"], business_id) &
    isin_or_all(df["Ceding_Company"], cedent) &
    isin_or_all(df["MGA"], mga) &
    isin_or_all(df["Venue"], venue) &
    isin_or_all(df["Limit_Band"], limit_band) &
    isin_or_all(df["Attachment_Band"], attach_band)
)

f = df[mask].copy()

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Policies", len(f))
k2.metric("Premium (GWP)", f"${f['Annual_Premium'].sum():,.0f}")
k3.metric("Exposed Limit", f"${(f['Limit_Per_Occurrence']*f['Share']).sum():,.0f}")
k4.metric("% Primary", f"{100*f['Policy_Type'].eq('Primary').mean():.1f}%" if len(f) else "0.0%")
k5.metric("Treaties", f["Business_ID"].nunique())

st.divider()

# Live table
st.subheader("Filtered Policies (live)")
st.dataframe(
    f,
    use_container_width=True,
    hide_index=True
)