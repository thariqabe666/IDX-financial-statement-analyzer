import os
import pypdf
from typing import List, Dict, Any
from schemas import ExtractedFinancials, BalanceSheet, IncomeStatement
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed
import json
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_text_from_pdf(pdf_path: str) -> List[str]:
    """
    Extracts text from each page of the PDF.
    Returns a list of strings, where each string is the text content of a page.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        
    pages_text = []
    try:
        reader = pypdf.PdfReader(pdf_path)
        for page in reader.pages:
            text = page.extract_text()
            pages_text.append(text if text else "")
    except Exception as e:
        print(f"Error reading PDF: {e}")
        return []
        
    return pages_text

def filter_relevant_pages(pages_text: List[str]) -> Dict[str, List[int]]:
    """
    Identifies relevant pages for Balance Sheet (Posisi Keuangan) and Income Statement (Laba Rugi)
    based on keyword density and heuristics.
    Returns a dictionary with keys 'balance_sheet' and 'income_statement' containing lists of page indices.
    """
    relevant_pages = {
        'balance_sheet': [],
        'income_statement': []
    }
    
    # Keywords
    kw_bs = ["laporan posisi keuangan", "statement of financial position", "jumlah aset", "total assets"]
    kw_is = ["laporan laba rugi", "statement of profit or loss", "laba rugi", "pendapatan", "revenue"]
    
    # Exclude keywords to avoid Table of Contents or Notes
    kw_exclude = ["daftar isi", "content", "catatan atas", "notes to"]

    for i, text in enumerate(pages_text):
        text_lower = text.lower()
        
        # Simple exclusion
        if any(ex in text_lower for ex in kw_exclude):
             # But be careful, sometimes actual tables have "notes" column. 
             # Check if it's strictly a TOC page? For now, let's keep it simple.
             # If "daftar isi" is in the first few lines, skip.
             header = text_lower[:500]
             if "daftar isi" in header or "table of contents" in header:
                 continue

        # Score for Balance Sheet
        score_bs = sum(1 for kw in kw_bs if kw in text_lower)
        
        # Score for Income Statement
        score_is = sum(1 for kw in kw_is if kw in text_lower)
        
        # Special case for PSAK 111 (Supplementary info)
        if "psak 111" in text_lower:
            relevant_pages['balance_sheet'].append(i)
            relevant_pages['income_statement'].append(i)
            continue

        # Thresholds (adjust as needed)
        if score_bs >= 2:
            relevant_pages['balance_sheet'].append(i)
            
        if score_is >= 2:
            relevant_pages['income_statement'].append(i)
            
    # Refine: usually these statements are early in the document (financial part)
    # but after general info.
    # Take top 3 max to affect context window? 
    # Let's just return what we found, strict filtering will be done by LLM loop if needed.
    
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
    5. PRIORITASKAN PSAK 111: Jika Anda melihat teks "Setelah PSAK 111" atau "Informasi Keuangan Tambahan", set `is_psak_111` menjadi `true`. 
       PENTING: Jika ada dua kolom ("Metode Konsolidasi" vs "Setelah PSAK 111"), ABAIKAN kolom "Metode Konsolidasi" dan GUNAKAN angka dari kolom "Setelah PSAK 111".
    6. Mapping field sesuai schema:
       - 'revenues': Pendapatan Usaha / Penjualan
       - 'gross_profit': Laba Bruto
       - 'net_income': Laba Bersih Tahun Berjalan / Laba yang dapat diatribusikan ke entitas induk
       - 'finance_cost': Beban Keuangan / Bunga (Pastikan ambil nilainya sebagai positif jika itu beban, nanti logika bisnis yang menentukan pengurangan). 
         Note: Di schema value harus float. Jika teks '(500)', value: -500.0. 
         Biasanya Beban Keuangan di Laporan Laba Rugi disajikan negatif atau positif di kurung. Ikuti nilai matematisnya.
    7. Jangan berhalusinasi. Jika field tidak ditemukan di teks, biarkan null.
    """
    
    try:
        completion = client.beta.chat.completions.parse(
            model="gpt-4o",
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
    Strategy: Prioritize objects with is_psak_111=True.
    """
    if not extracted_list:
        return None
        
    # Sort: put PSAK 111 objects at the beginning, so they get processed first or overwrite.
    # Actually, if we want them to overwrite, we should process them LAST if using a simple loop,
    # or just separate them.
    
    psak_data = [x for x in extracted_list if x.is_psak_111]
    main_data = [x for x in extracted_list if not x.is_psak_111]
    
    # Combined list: Main first, then PSAK to overwrite
    ordered_list = main_data + psak_data
    
    if not ordered_list:
        return None
        
    merged = ordered_list[0]
    
    for other in ordered_list[1:]:
        # Update Company / Period if missing
        if (not merged.company_name or merged.company_name == "Unknown") and other.company_name:
            merged.company_name = other.company_name
        if (not merged.report_period or merged.report_period == "Unknown") and other.report_period:
            merged.report_period = other.report_period
        if other.is_psak_111:
            merged.is_psak_111 = True
            
        # Update BS
        for field in merged.balance_sheet.model_fields:
            new_val = getattr(other.balance_sheet, field)
            if new_val is not None:
                # If 'other' is PSAK 111, it ALWAYS overwrites.
                # If 'merged' current value is None, it also overwrites.
                if other.is_psak_111:
                    setattr(merged.balance_sheet, field, new_val)
                elif getattr(merged.balance_sheet, field) is None:
                    setattr(merged.balance_sheet, field, new_val)
                
        # Update IS
        for field in merged.income_statement.model_fields:
            new_val = getattr(other.income_statement, field)
            if new_val is not None:
                if other.is_psak_111:
                    setattr(merged.income_statement, field, new_val)
                elif getattr(merged.income_statement, field) is None:
                    setattr(merged.income_statement, field, new_val)
                
    return merged
