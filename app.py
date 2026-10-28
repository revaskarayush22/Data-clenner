import io

import pandas as pd
import streamlit as st

from cleaner import (
    DEFAULT_EMAIL_TEMPLATE,
    SAMPLE_DATA,
    clean_dataframe,
)

st.set_page_config(page_title="Lead Data Cleaner", page_icon="🧹", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; max-width: 1250px;}
    .hero {
        background: linear-gradient(120deg, #4f46e5 0%, #7c3aed 55%, #db2777 100%);
        padding: 2rem 2.2rem; border-radius: 18px; color: white; margin-bottom: 1.5rem;
    }
    .hero h1 {margin: 0; font-size: 2.1rem; color: white;}
    .hero p {margin: .4rem 0 0; opacity: .92; font-size: 1.05rem;}
    div[data-testid="stMetric"] {
        background: rgba(124,58,237,.07); border: 1px solid rgba(124,58,237,.2);
        padding: 14px 16px; border-radius: 14px;
    }
    .stDownloadButton button, .stButton button[kind="primary"] {
        border-radius: 10px; font-weight: 600;
    }
    </style>
    <div class="hero">
        <h1>🧹 Lead Data Cleaner</h1>
        <p>Drop in messy lead data. Get clean names, emails, budgets, fit scores and
        draft replies back in seconds.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------- Sidebar settings ----------------
with st.sidebar:
    st.header("⚙️ Scoring rules")
    high_budget = st.number_input("High budget from ($) → score 90", 0, value=10_000, step=500)
    mid_budget = st.number_input("Mid budget from ($) → score 75", 0, value=5_000, step=500)
    threshold = st.slider("HIGH_PRIORITY at score ≥", 0, 100, 70)
    st.caption("Any budget above 0 scores 60. Zero or missing budget scores 30.")

    st.header("✉️ Email draft")
    signature = st.text_input("Signature", "Sales Team")
    template = st.text_area(
        "Template",
        DEFAULT_EMAIL_TEMPLATE,
        height=220,
        help="Use {first_name} and {signature} as placeholders.",
    )

# ---------------- Input ----------------
st.subheader("1 · Add your messy data")
tab_upload, tab_paste, tab_sample = st.tabs(["📁 Upload file", "📋 Paste data", "🧪 Try sample"])

raw_df = None

with tab_upload:
    up = st.file_uploader("CSV or Excel file", type=["csv", "xlsx", "xls"])
    if up is not None:
        try:
            if up.name.lower().endswith(".csv"):
                raw_df = pd.read_csv(up, dtype=str, keep_default_na=False)
            else:
                raw_df = pd.read_excel(up, dtype=str).fillna("")
        except Exception as e:
            st.error(f"Could not read the file: {e}")

with tab_paste:
    pasted = st.text_area(
        "Paste CSV or tab-separated rows (with a header row)",
        height=180,
        placeholder="Raw_Name,Contact_Email,Company_Name,Claimed_Budget,Project_Details\n"
        "jOHN doe,john@acme.com,acme corp,$5,000 USD,CRM automation",
    )
    if pasted.strip():
        try:
            raw_df = pd.read_csv(io.StringIO(pasted), sep=None, engine="python", dtype=str, keep_default_na=False)
        except Exception as e:
            st.error(f"Could not parse the pasted data: {e}")

with tab_sample:
    st.dataframe(SAMPLE_DATA, width="stretch", hide_index=True)
    if st.button("Use this sample"):
        st.session_state["use_sample"] = True
    if st.session_state.get("use_sample") and raw_df is None:
        raw_df = SAMPLE_DATA.copy()

# ---------------- Output ----------------
if raw_df is None or raw_df.empty:
    st.info("Upload a file, paste rows, or try the sample to get started.")
    st.stop()

st.subheader("2 · Raw input")
st.caption(f"{len(raw_df):,} rows · columns: {', '.join(raw_df.columns)}")
with st.expander("Preview raw data", expanded=False):
    st.dataframe(raw_df, width="stretch", hide_index=True)

clean_df = clean_dataframe(
    raw_df,
    high_budget=high_budget,
    mid_budget=mid_budget,
    priority_threshold=threshold,
    email_template=template,
    signature=signature,
)

st.subheader("3 · Clean results")

flagged = (clean_df["AI_Red_Flags"] != "None").sum()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Leads cleaned", f"{len(clean_df):,}")
c2.metric("High priority", int((clean_df["Priority"] == "HIGH_PRIORITY").sum()))
c3.metric("With red flags", int(flagged))
c4.metric("Total budget", f"${clean_df['Budget'].sum():,.0f}")

t_clean, t_flags, t_drafts, t_charts = st.tabs(["✅ Clean data", "🚩 Red flags", "✉️ Email drafts", "📊 Insights"])

with t_clean:
    only_high = st.checkbox("Show only HIGH_PRIORITY")
    view = clean_df[clean_df["Priority"] == "HIGH_PRIORITY"] if only_high else clean_df
    st.dataframe(
        view.drop(columns=["AI_Email_Draft"]),
        width="stretch",
        hide_index=True,
        column_config={
            "Budget": st.column_config.NumberColumn(format="$%d"),
            "AI_Fit_Score": st.column_config.ProgressColumn("Fit score", min_value=0, max_value=100, format="%d"),
        },
    )

with t_flags:
    bad = clean_df[clean_df["AI_Red_Flags"] != "None"][
        ["Full_Name", "Email", "Company_Name", "Budget", "AI_Red_Flags"]
    ]
    if bad.empty:
        st.success("No red flags. Every lead has an email, company and budget.")
    else:
        st.warning(f"{len(bad)} lead(s) need attention.")
        st.dataframe(bad, width="stretch", hide_index=True)

with t_drafts:
    for _, r in clean_df.iterrows():
        with st.expander(f"{r['Full_Name']} · {r['Company_Name']}"):
            st.code(r["AI_Email_Draft"], language=None)

with t_charts:
    left, right = st.columns(2)
    with left:
        st.markdown("**Leads by priority**")
        st.bar_chart(clean_df["Priority"].value_counts())
    with right:
        st.markdown("**Fit score distribution**")
        st.bar_chart(clean_df["AI_Fit_Score"].value_counts().sort_index())

# ---------------- Download ----------------
st.subheader("4 · Download")
d1, d2, _ = st.columns([1, 1, 2])
d1.download_button(
    "⬇️ Download CSV",
    clean_df.to_csv(index=False).encode("utf-8"),
    "clean_leads.csv",
    "text/csv",
    type="primary",
)
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as xw:
    clean_df.to_excel(xw, index=False, sheet_name="Clean Leads")
d2.download_button(
    "⬇️ Download Excel",
    buf.getvalue(),
    "clean_leads.xlsx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)
