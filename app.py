import streamlit as st
import pandas as pd
import os
import tempfile
from extractor import extract_text_from_pdf, filter_relevant_pages, analyze_page_with_llm, merge_financials
from utils import calculate_ratios_structured, format_currency

st.set_page_config(page_title="IDX Financial Analyzer", layout="wide")

# Custom CSS for Premium Look
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Outfit:wght@400;600;700&display=swap');

    /* Target the root and all app containers */
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMainViewContainer"] {
        background: linear-gradient(135deg, #020617 0%, #0f172a 100%) !important;
        background-attachment: fixed !important;
        color: #f8fafc !important;
        font-family: 'Outfit', sans-serif !important;
    }

    /* Transparency for header */
    [data-testid="stHeader"] {
        background-color: rgba(0,0,0,0) !important;
    }

    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    ::-webkit-scrollbar-track {
        background: #0f172a;
    }
    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 10px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #475569;
    }

    /* Specific glassmorphism for Metrics */
    div[data-testid="stMetric"], .stMetric, div[data-testid="metric-container"] {
        background-color: rgba(30, 41, 59, 0.45) !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        padding: 24px !important;
        border-radius: 24px !important;
        backdrop-filter: blur(20px) !important;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -2px rgba(0, 0, 0, 0.2) !important;
        transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1) !important;
        margin-bottom: 1.5rem !important;
    }
    
    div[data-testid="stMetric"]:hover {
        transform: translateY(-8px) scale(1.02) !important;
        background-color: rgba(30, 41, 59, 0.7) !important;
        border: 1px solid rgba(59, 130, 246, 0.5) !important;
        box-shadow: 0 25px 30px -10px rgba(0, 0, 0, 0.6) !important;
    }

    /* Metric internal text colors */
    [data-testid="stMetricLabel"] p {
        color: #94adcf !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.025em !important;
    }
    
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-weight: 700 !important;
    }
    
    /* Ensure the metric value container doesn't have its own background/border */
    [data-testid="stMetricValue"] > div {
        background: transparent !important;
    }

    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
        color: white !important;
        border: none !important;
        padding: 0.6rem 1.5rem !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
        font-family: 'Inter', sans-serif !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2) !important;
        width: 100% !important;
    }

    .stButton>button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4) !important;
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    }

    /* File Uploader */
    [data-testid="stFileUploader"] {
        background-color: rgba(30, 41, 59, 0.3) !important;
        border: 2px dashed rgba(255, 255, 255, 0.1) !important;
        border-radius: 15px !important;
        padding: 30px !important;
    }
    
    [data-testid="stFileUploadDropzone"] {
        border: none !important;
        background: transparent !important;
    }

    /* Success/Warning/Error Alerts */
    .stAlert {
        background-color: rgba(30, 41, 59, 0.5) !important;
        color: #f8fafc !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
        border-radius: 16px !important;
        backdrop-filter: blur(12px) !important;
    }
    
    h1, h2, h3 {
        color: #ffffff !important;
        font-family: 'Outfit', sans-serif !important;
        font-weight: 700 !important;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: rgba(30, 41, 59, 0.3) !important;
        border-radius: 10px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    
    .streamlit-expanderContent {
        background-color: rgba(30, 41, 59, 0.2) !important;
        border-radius: 0 0 10px 10px !important;
    }

    /* JSON and Code blocks */
    pre, code {
        background-color: rgba(15, 23, 42, 0.6) !important;
        border-radius: 8px !important;
        color: #e2e8f0 !important;
    }

    /* Progress Bar */
    .stProgress > div > div > div > div {
        background-image: linear-gradient(to right, #3b82f6, #60a5fa) !important;
    }

    /* Input focus */
    .stTextInput input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5) !important;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 IDX Financial Analyzer (LLM-First)")
st.markdown("""
Aplikasi ini menggunakan **LLM (GPT-4o)** untuk ekstraksi data laporan keuangan yang lebih cerdas dan fleksibel.
""")

uploaded_file = st.file_uploader("Upload Laporan Keuangan (PDF)", type="pdf")

if uploaded_file is not None:
    try:
        # Save uploaded file to a temporary location
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.read())
            tmp_path = tmp_file.name

        with st.spinner("🚀 AI sedang menganalisis dokumen..."):
            # 1. Extract Text
            pages_text = extract_text_from_pdf(tmp_path)
            
            # 2. Filter Relevant Pages
            relevant_map = filter_relevant_pages(pages_text)
            
            # Collect indices to process
            indices = set(relevant_map['balance_sheet'] + relevant_map['income_statement'])
            if not indices:
                indices = set(range(min(5, len(pages_text))))
            
            # 3. Analyze with LLM
            extracted_results = []
            progress_bar = st.progress(0)
            total = len(indices)
            
            for i, idx in enumerate(indices):
                progress_bar.progress((i + 1) / total)
                st.write(f"📝 Memproses Halaman {idx + 1}...")
                result = analyze_page_with_llm(pages_text[idx])
                if result:
                    extracted_results.append(result)
            
            # 4. Merge
            final_data = merge_financials(extracted_results)
            
        os.remove(tmp_path) # Cleanup

        if final_data:
            st.success(f"Analisis Selesai: **{final_data.company_name}** ({final_data.report_period})")
            
            if final_data.is_psak_111:
                st.warning("⚠️ Data diprioritaskan dari halaman **Laporan Tambahan (Setelah PSAK 111)**.")

            # Display Extraction Metadata
            with st.expander("🔍 Detail Ekstraksi AI"):
                st.json(final_data.model_dump())

            # 5. Calculate Ratios
            ratios = calculate_ratios_structured(final_data)

            # 6. Display Dashboard
            st.markdown("---")
            st.header("📈 Financial Performance Dashboard")
            
            # Highlights
            c1, c2, c3 = st.columns(3)
            c1.metric("Revenue", f"{final_data.currency} {format_currency(final_data.income_statement.revenues.value if final_data.income_statement.revenues else 0)}")
            c2.metric("Net Income", f"{final_data.currency} {format_currency(final_data.income_statement.net_income.value if final_data.income_statement.net_income else 0)}")
            c3.metric("Total Assets", f"{final_data.currency} {format_currency(final_data.balance_sheet.total_assets.value if final_data.balance_sheet.total_assets else 0)}")

            # Profitability
            st.subheader("Profitability")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Gross Profit Margin", f"{ratios.get('GPM', 0):.2f}%")
            m2.metric("Net Profit Margin", f"{ratios.get('NPM', 0):.2f}%")
            m3.metric("ROE", f"{ratios.get('ROE', 0):.2f}%")
            m4.metric("ROA", f"{ratios.get('ROA', 0):.2f}%")
            
            # Solvency & Liquidity
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader("Solvency")
                s1, s2 = st.columns(2)
                s1.metric("DER", f"{ratios.get('DER', 0):.2f}x")
                s2.metric("Interest Coverage", f"{ratios.get('Interest Coverage', 0):.2f}x")
            
            with col_b:
                st.subheader("Liquidity")
                l1, l2, l3 = st.columns(3)
                l1.metric("Current Ratio", f"{ratios.get('Current Ratio', 0):.2f}x")
                l2.metric("Cash Ratio", f"{ratios.get('Cash Ratio', 0):.2f}x")
                l3.metric("Quick Ratio", f"{ratios.get('Quick Ratio', 0):.2f}x")

        else:
            st.error("Gagal mengekstrak data terstruktur. Coba upload file lain.")

    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        with st.expander("Debug Traceback"):
            st.text(traceback.format_exc())
