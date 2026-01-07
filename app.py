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
    .main {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    }
    .stMetric {
        background-color: rgba(255, 255, 255, 0.4);
        padding: 20px;
        border-radius: 15px;
        backdrop-filter: blur(10px);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        border: 1px solid rgba(255, 255, 255, 0.3);
    }
    .stAlert {
        border-radius: 15px;
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
