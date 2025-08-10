# Create a simple Streamlit web app that reads the previously generated Excel file
# and provides interactive filtering, KPIs, and a few charts.
import os, textwrap, json, pandas as pd

app_dir = "/mnt/data/casualty_exposure_app"
os.makedirs(app_dir, exist_ok=True)

app_py = r"""
import streamlit as st
import pandas as pd
import numpy as np
import io
from datetime import datetime
import plotly.express as px

st.set_page_config(page_title="Casualty Exposure Explorer", layout="wide")

@st.cache_data
def load_policies(default_path):
    try:
        df = pd.read_excel(default_path, sheet_name="Policies")
    except Exception:
        df = pd.DataFrame()
    # enforce dtypes
    if not df.empty:
        date_cols = ["Effective_Date", "Expiration_Date"]
        for c in date_cols:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c])
        num_cols = ["Annual_Premium","Limit_Per_Occurrence","Limit_Aggregate","Attachment_Point","Share"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        # helpful derived columns
        if "MGA" in df.columns:
            df["MGA_Flag"] = np.where(df["MGA"].fillna("N/A")=="N/A","No MGA","MGA")
        if "Effective_Date" in df.columns:
            df["Inception_Month"] = df["Effective_Date"].dt.to_period("M").dt.to_timestamp()
        # bands
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
        df["Exposed_Limit"] = df["Limit_Per_Occurrence"] * df["Share"]
    return df

@st.cache_data
def load_judicial(path):
    try:
        jr = pd.read_excel(path, sheet_name="JudicialRisk")
    except Exception:
        jr = pd.DataFrame(columns=["State","RiskTier","RiskScore"])
    return jr

DEFAULT_DATA = "Casualty_Exposure_Dummy_Universe.xlsx"
DEFAULT_JR = "Judicial_Risk_Lookup.xlsx"

st.title("Casualty Exposure Explorer")

with st.sidebar:
    st.header("Data")
    upl = st.file_uploader("Upload exposure Excel (Policies sheet)", type=["xlsx"])
    jr_upl = st.file_uploader("Upload judicial risk Excel (JudicialRisk sheet)", type=["xlsx"], key="jr")
    st.caption("If you skip uploads, the app will load the provided sample files if present.")

df = None
if upl is not None:
    df = pd.read_excel(upl, sheet_name="Policies")
else:
    df = load_policies(DEFAULT_DATA)

jr = None
if jr_upl is not None:
    jr = pd.read_excel(jr_upl, sheet_name="JudicialRisk")
else:
    jr = load_judicial(DEFAULT_JR)

if df is None or df.empty:
    st.warning("No data loaded. Upload an Excel file with a 'Policies' sheet.")
    st.stop()

# Sidebar filters
with st.sidebar:
    st.header("Filters")
    cols = st.columns(2)
    with cols[0]:
        uy = st.multiselect("Underwriting Year (UY)", sorted(df["UY"].dropna().unique().tolist()), default=sorted(df["UY"].dropna().unique().tolist()))
        lob = st.multiselect("LOB", sorted(df["LOB"].dropna().unique().tolist()))
        sublob = st.multiselect("Sub LOB", sorted(df["Sub_LOB"].dropna().unique().tolist()))
        policy_type = st.multiselect("Policy Type", sorted(df["Policy_Type"].dropna().unique().tolist()))
    with cols[1]:
        business_id = st.multiselect("Business ID (Treaty)", sorted(df["Business_ID"].dropna().unique().tolist()))
        cedent = st.multiselect("Ceding Company", sorted(df["Ceding_Company"].dropna().unique().tolist()))
        mga = st.multiselect("MGA", sorted(df["MGA"].dropna().unique().tolist()))
        venue = st.multiselect("Venue (State)", sorted(df["Venue"].dropna().unique().tolist()))
    st.divider()
    st.header("Bands")
    limit_band = st.multiselect("Limit Band", sorted(df["Limit_Band"].dropna().unique().tolist()))
    attach_band = st.multiselect("Attachment Band", sorted(df["Attachment_Band"].dropna().unique().tolist()))

f = df.copy()
def apply_filter(series, values):
    return series.isin(values) if values else True

mask = (
    apply_filter(f["UY"], uy) &
    (apply_filter(f["LOB"], lob)) &
    (apply_filter(f["Sub_LOB"], sublob)) &
    (apply_filter(f["Policy_Type"], policy_type)) &
    (apply_filter(f["Business_ID"], business_id)) &
    (apply_filter(f["Ceding_Company"], cedent)) &
    (apply_filter(f["MGA"], mga)) &
    (apply_filter(f["Venue"], venue)) &
    (apply_filter(f["Limit_Band"], limit_band)) &
    (apply_filter(f["Attachment_Band"], attach_band))
)

f = f.loc[mask].copy()

# KPIs
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Policies", f.shape[0])
k2.metric("Total Premium (GWP)", f"${f['Annual_Premium'].sum():,.0f}")
k3.metric("Exposed Limit", f"${(f['Limit_Per_Occurrence'] * f['Share']).sum():,.0f}")
primary_pct = 100.0 * (f["Policy_Type"].eq("Primary").mean() if not f.empty else 0.0)
k4.metric("% Primary", f"{primary_pct:,.1f}%")
k5.metric("Treaties", f["Business_ID"].nunique())

st.divider()

# Row: Premium by LOB & UY
c1, c2 = st.columns([2,1])
with c1:
    if not f.empty:
        fig1 = px.bar(f, x="UY", y="Annual_Premium", color="LOB", barmode="stack",
                      title="Premium by LOB & UY", labels={"Annual_Premium":"Premium"})
        st.plotly_chart(fig1, use_container_width=True)
with c2:
    if not f.empty:
        top_ced = (f.groupby("Ceding_Company")["Annual_Premium"].sum()
                   .sort_values(ascending=False).head(10).reset_index())
        fig2 = px.bar(top_ced, x="Annual_Premium", y="Ceding_Company", orientation="h",
                      title="Top 10 Ceding Companies by Premium", labels={"Annual_Premium":"Premium"})
        st.plotly_chart(fig2, use_container_width=True)

# Row: Map + Scatter
c3, c4 = st.columns([1.5,1.5])
with c3:
    if not f.empty:
        mdf = f.groupby("Venue", as_index=False).agg(Exposed_Limit=("Exposed_Limit","sum"),
                                                     Policies=("Policy_Number","count"),
                                                     Premium=("Annual_Premium","sum"))
        fig3 = px.choropleth(mdf, locations="Venue", locationmode="USA-states",
                             color="Exposed_Limit", scope="usa",
                             hover_data={"Policies":True,"Premium":":,.0f","Exposed_Limit":":,.0f"},
                             title="Exposed Limit by State (Venue)")
        st.plotly_chart(fig3, use_container_width=True)

with c4:
    if not f.empty:
        fig4 = px.scatter(f, x="Attachment_Point", y="Annual_Premium",
                          size="Limit_Per_Occurrence", color="Policy_Type",
                          hover_data=["Policy_Number","Business_ID","LOB","Sub_LOB"],
                          title="Premium vs Attachment (bubble sized by Limit)",
                          labels={"Annual_Premium":"Premium","Attachment_Point":"Attachment"})
        st.plotly_chart(fig4, use_container_width=True)

# Row: Matrix
st.subheader("Exposure Cross-Tab (LOB × Limit Band)")
if not f.empty:
    pivot = (f.pivot_table(index="LOB", columns="Limit_Band",
                           values="Policy_Number", aggfunc="count", fill_value=0)
             .reindex(sorted(f["LOB"].unique()), axis=0))
    st.dataframe(pivot)

# Table + download
st.subheader("Filtered Policies")
st.dataframe(f.head(500))  # show first 500 for performance

def to_excel_bytes(df):
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="xlsxwriter", datetime_format='yyyy-mm-dd', date_format='yyyy-mm-dd') as writer:
        df.to_excel(writer, sheet_name="Policies_Filtered", index=False)
    out.seek(0)
    return out

dl1, dl2 = st.columns(2)
with dl1:
    st.download_button("Download filtered (Excel)", data=to_excel_bytes(f), file_name="Filtered_Policies.xlsx")
with dl2:
    st.download_button("Download filtered (CSV)", data=f.to_csv(index=False).encode("utf-8"), file_name="Filtered_Policies.csv")

st.caption("Tip: Upload new exposure files at left. Join a judicial risk sheet to enhance the state map tooltips.")
"""

reqs = """streamlit==1.36.0
pandas==2.2.2
plotly==5.23.0
openpyxl==3.1.2
xlsxwriter==3.2.0
"""

with open(os.path.join(app_dir, "app.py"), "w", encoding="utf-8") as f:
    f.write(app_py)
with open(os.path.join(app_dir, "requirements.txt"), "w", encoding="utf-8") as f:
    f.write(reqs)

app_dir
