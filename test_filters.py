import os
import pypdf
from typing import List, Dict

def extract_text_from_pdf(pdf_path: str, max_pages: int = 20) -> List[str]:
    pages_text = []
    reader = pypdf.PdfReader(pdf_path)
    pages_to_read = reader.pages[:max_pages]
    for page in pages_to_read:
        text = page.extract_text()
        pages_text.append(text if text else "")
    return pages_text

def filter_relevant_pages(pages_text: List[str]) -> Dict[str, List[int]]:
    relevant_pages = {
        'balance_sheet': [],
        'income_statement': []
    }
    kw_bs_start = ["laporan posisi keuangan", "statement of financial position"]
    kw_is_start = ["laporan laba rugi", "statement of profit or loss", "laba rugi dan penghasilan komprehensif"]
    kw_bs_end = ["jumlah liabilitas dan ekuitas", "total liabilities and equity"]
    kw_is_end = ["laba (rugi) per saham", "earnings (loss) per share", "laba per saham"]
    kw_exclude = ["daftar isi", "table of contents"]
    kw_stop_all = ["catatan atas laporan keuangan", "notes to the financial statements"]
    
    current_section = None 

    for i, text in enumerate(pages_text):
        text_lower = text.lower()
        if any(ex in text_lower[:500] for ex in kw_exclude):
            continue
        
        # Global stop
        if any(stop in text_lower[:500] for stop in kw_stop_all):
            current_section = None

        if any(kw in text_lower[:1000] for kw in kw_bs_start):
            current_section = 'bs'
            relevant_pages['balance_sheet'].append(i)
            if any(kw in text_lower for kw in kw_bs_end):
                current_section = None
            continue
        if any(kw in text_lower[:1000] for kw in kw_is_start):
            current_section = 'is'
            relevant_pages['income_statement'].append(i)
            if any(kw in text_lower for kw in kw_is_end):
                current_section = None
            continue
        if current_section == 'bs':
            relevant_pages['balance_sheet'].append(i)
            if any(kw in text_lower for kw in kw_bs_end):
                current_section = None
        elif current_section == 'is':
            relevant_pages['income_statement'].append(i)
            if any(kw in text_lower for kw in kw_is_end):
                current_section = None
            
    return relevant_pages

if __name__ == "__main__":
    pdf_path = "BUMI - Laporan Keuangan Q1 31 Mar 2025.pdf"
    print(f"Testing filter on {pdf_path}...")
    texts = extract_text_from_pdf(pdf_path)
    res = filter_relevant_pages(texts)
    print(f"Detected Pages: {res}")
    for section, pages in res.items():
        print(f"{section}: {[p+1 for p in pages]}")
