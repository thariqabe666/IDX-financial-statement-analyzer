import os
import pypdf
from typing import List, Dict, Any
from schemas import ExtractedFinancials, BalanceSheet, IncomeStatement
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
import json
from dotenv import load_dotenv

load_dotenv()

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
client = OpenAI(
    api_key=os.environ.get("XAI_API_KEY"),
    base_url="https://api.x.ai/v1", # The xAI API base URL
)

def extract_text_from_pdf(pdf_path: str, max_pages: int = 20) -> List[str]:
    """
    Extracts text from each page of the PDF, up to max_pages.
    Returns a list of strings, where each string is the text content of a page.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        
    pages_text = []
    try:
        reader = pypdf.PdfReader(pdf_path)
        # Limit to the first max_pages
        pages_to_read = reader.pages[:max_pages]
        for page in pages_to_read:
            text = page.extract_text()
            pages_text.append(text if text else "")
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return []
        
    return pages_text

def filter_relevant_pages(pages_text: List[str]) -> Dict[str, List[int]]:
    """
    Identifies relevant pages for Balance Sheet (Posisi Keuangan) and Income Statement (Laba Rugi)
    by detecting the start and end of each section.
    """
    relevant_pages = {
        'balance_sheet': [],
        'income_statement': []
    }
    
    # 1. Keywords for Start
    kw_bs_start = ["laporan posisi keuangan", "statement of financial position"]
    kw_is_start = ["laporan laba rugi", "statement of profit or loss", "laba rugi dan penghasilan komprehensif"]
    
    # 2. Keywords for End (Termination)
    kw_bs_end = ["jumlah liabilitas dan ekuitas", "total liabilities and equity"]
    kw_is_end = ["laba (rugi) per saham", "earnings (loss) per share", "laba per saham"]

    # 3. Exclude keywords (like Table of Contents)
    kw_exclude = ["daftar isi", "table of contents"]
    kw_stop_all = ["catatan atas laporan keuangan", "notes to the financial statements"]

    current_section = None # 'bs' or 'is'

    for i, text in enumerate(pages_text):
        text_lower = text.lower()
        
        # Skip Table of Contents
        if any(ex in text_lower[:500] for ex in kw_exclude):
            continue
            
        # Global stop for primary statements
        if any(stop in text_lower[:500] for stop in kw_stop_all):
            current_section = None
            # We don't continue because we might hit another section start on the same page? 
            # Usually notes start on its own page.
            # But let's check for starts below.

        # Check for Start of Balance Sheet
        if any(kw in text_lower[:1000] for kw in kw_bs_start):
            current_section = 'bs'
            relevant_pages['balance_sheet'].append(i)
            # Check if it also ends on the same page
            if any(kw in text_lower for kw in kw_bs_end):
                current_section = None
            continue

        # Check for Start of Income Statement
        if any(kw in text_lower[:1000] for kw in kw_is_start):
            current_section = 'is'
            relevant_pages['income_statement'].append(i)
            # Check if it also ends on the same page
            if any(kw in text_lower for kw in kw_is_end):
                current_section = None
            continue

        # If we are already in a section, continue adding pages until end is found
        if current_section == 'bs':
            relevant_pages['balance_sheet'].append(i)
            if any(kw in text_lower for kw in kw_bs_end):
                current_section = None
        elif current_section == 'is':
            relevant_pages['income_statement'].append(i)
            if any(kw in text_lower for kw in kw_is_end):
                current_section = None
            
    return relevant_pages

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def analyze_page_with_llm(text_content: str) -> ExtractedFinancials:
    """
    Sends text content to LLM to extract financial data according to ExtractedFinancials schema.
    """
    
    system_prompt = """
    Anda adalah Akuntan Expert auditor PSAK. Tugas Anda adalah mengekstrak data keuangan dari teks kotor hasil OCR PDF.
    
    Rules:
    1. Identifikasi angka dengan hati-hati. PDF sering menggunakan format Indonesia (1.000.000) atau Inggris (1,000,000). Konversi semua ke Float standar Python.
    2. Jika angka dalam kurung `(500)`, itu artinya Negatif `-500`.
    3. Perhatikan Skala! Jika header tabel bilang 'Dalam Jutaan Rupiah', kalikan angka dengan 1.000.000. Skala bisa dalam bentuk Rupiah ataupun Dolar.
    4. Coba temukan Nama Perusahaan, Periode, dan Mata Uang dari konteks teks.
    5. Mapping field sesuai schema:
       - 'revenues': Pendapatan Usaha / Penjualan
       - 'gross_profit': Laba Bruto
       - 'net_income': Laba Bersih Tahun Berjalan 
       - 'finance_cost': Beban Keuangan / Bunga (Pastikan ambil nilainya sebagai positif jika itu beban, nanti logika bisnis yang menentukan pengurangan). 
         Note: Di schema value harus float. Jika teks '(500)', value: -500.0. 
         Biasanya Beban Keuangan di Laporan Laba Rugi disajikan negatif atau positif di kurung. Ikuti nilai matematisnya.
    6. Jangan berhalusinasi. Jika field tidak ditemukan di teks, biarkan null.
    """
    
    try:
        completion = client.beta.chat.completions.parse(
            model="grok-4-1-fast-reasoning",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Extract financial data from this text:\n\n{text_content}"},
            ],
            response_format=ExtractedFinancials,
        )
        
        return completion.choices[0].message.parsed
        
    except Exception as e:
        print(f"Error in LLM extraction: {e}")
        raise e

def merge_financials(extracted_list: List[ExtractedFinancials]) -> ExtractedFinancials:
    """
    Merges multiple ExtractedFinancials objects into one.
    Strategy: Take the non-null values. If conflict, take the latter (assuming later pages might be more detailed? or just first non-null).
    """
    if not extracted_list:
        return None
        
    merged = extracted_list[0]
    
    for other in extracted_list[1:]:
        # Update Company / Period if missing
        if (not merged.company_name or merged.company_name == "Unknown") and other.company_name:
            merged.company_name = other.company_name
        if (not merged.report_period or merged.report_period == "Unknown") and other.report_period:
            merged.report_period = other.report_period
            
        # Update BS
        for field in merged.balance_sheet.model_fields:
            current_val = getattr(merged.balance_sheet, field)
            new_val = getattr(other.balance_sheet, field)
            if current_val is None and new_val is not None:
                setattr(merged.balance_sheet, field, new_val)
                
        # Update IS
        for field in merged.income_statement.model_fields:
            current_val = getattr(merged.income_statement, field)
            new_val = getattr(other.income_statement, field)
            if current_val is None and new_val is not None:
                setattr(merged.income_statement, field, new_val)
                
    return merged
