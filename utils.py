import re
import pdfplumber
import pandas as pd
import streamlit as st

def clean_currency(value_str):
    """
    Membersihkan format angka string dari Laporan Keuangan IDX.
    Rules:
    - '1.000.000' -> 1000000.0 (Hapus titik ribuan)
    - '(100)' -> -100.0 (Kurung berarti negatif)
    - '-' -> 0.0 (Strip berarti nol)
    """
    if not isinstance(value_str, str):
        return value_str
    
    # Remove whitespace
    value_str = value_str.strip()
    
    if value_str == '-' or value_str == '' or value_str == '–':
        return 0.0
        
    is_negative = False
    if value_str.startswith('(') and value_str.endswith(')'):
        is_negative = True
        value_str = value_str[1:-1] # Remove parens
        
    # Remove thousand separator (.)
    value_str = value_str.replace('.', '')
    
    # Handle decimal separator (,) -> change to . just in case, though usually financial main numbers are ints
    value_str = value_str.replace(',', '.')
    
    try:
        val = float(value_str)
        return -val if is_negative else val
    except ValueError:
        return 0.0

def find_financial_pages(pdf):
    """
    Mencari rentang halaman Neraca dan Laba Rugi.
    Returns dictionary: {'neraca': [indices], 'labarugi': [indices]}
    """
    pages = {'neraca': [], 'labarugi': []}
    
    found_neraca_start = False
    found_labarugi_start = False
    
    # Keywords for Start
    kw_neraca_start = ["laporan posisi keuangan", "statement of financial position"]
    kw_labarugi_start = ["laporan laba rugi", "statement of profit or loss"]
    
    # Keywords for End (Termination)
    kw_neraca_end = ["jumlah liabilitas dan ekuitas", "total liabilities and equity"]
    kw_labarugi_end = ["laba (rugi) per saham", "earnings (loss) per share", "laba per saham"]

    for i, page in enumerate(pdf.pages):
        text = page.extract_text()
        if not text:
            continue
            
        text_lower = text.lower()
        
        # Abaikan halaman Daftar Isi
        if "daftar isi" in text_lower or "table of contents" in text_lower:
            continue
            
        # 1. Detection for NERACA
        if not found_neraca_start:
            # Check if this page starts the Balance Sheet
            # Usually the title is in the top part
            header_area = " ".join(text_lower.split('\n')[:10])
            if any(kw in header_area for kw in kw_neraca_start):
                found_neraca_start = True
                pages['neraca'].append(i)
        elif found_neraca_start and not any(kw in text_lower for kw in kw_neraca_end):
            # If we are in Neraca section and haven't hit the end, add page
            # But check if it's the next section already
            if any(kw in text_lower for kw in kw_labarugi_start):
                 found_neraca_start = True # Keep it true but stop adding here? No, sections are usually sequential.
                 pass
            else:
                 pages['neraca'].append(i)
        elif found_neraca_start and any(kw in text_lower for kw in kw_neraca_end):
            pages['neraca'].append(i)
            found_neraca_start = False # Finished collecting Neraca
            
        # 2. Detection for LABA RUGI
        if not found_labarugi_start:
            header_area = " ".join(text_lower.split('\n')[:10])
            if any(kw in header_area for kw in kw_labarugi_start):
                # Avoid "Changes in Equity"
                if "ekuitas" not in header_area and "equity" not in header_area:
                    found_labarugi_start = True
                    pages['labarugi'].append(i)
        elif found_labarugi_start and not any(kw in text_lower for kw in kw_labarugi_end):
            pages['labarugi'].append(i)
        elif found_labarugi_start and any(kw in text_lower for kw in kw_labarugi_end):
            pages['labarugi'].append(i)
            found_labarugi_start = False # Finished
            
    # Cleaning: if we never found an end, but collected many pages, it might be a false positive.
    # Standard usually 1-3 pages.
    return pages

def extract_table_from_page(page):
    """
    Ekstrak tabel dari halaman PDF, bersihkan baris kosong/header invalid.
    Returns: DataFrame dengan kolom ['Label', 'Value_Raw', 'Value_Clean']
    """
    if not page:
        return pd.DataFrame(columns=['Label', 'Value_Raw', 'Value_Clean'])
    
    # Pendekatan: Coba default dulu, jika gagal (kolom < 2) coba 'text' strategy
    settings = [
        {}, # Default
        {"vertical_strategy": "text", "horizontal_strategy": "text", "snap_tolerance": 3},
        {"vertical_strategy": "text", "horizontal_strategy": "lines"}
    ]
    
    table = None
    for setting in settings:
        table = page.extract_table(table_settings=setting)
        if table and len(table) > 0 and len(table[0]) >= 2:
            break
            
    if not table:
        return pd.DataFrame(columns=['Label', 'Value_Raw', 'Value_Clean'])
    
    data = []
    
    for row in table:
        if not row or len(row) < 2:
            continue
            
        # Bersihkan label: Ambil kolom 0 (biasanya teks)
        label_candidate = str(row[0]).strip() if row[0] else ""
        if not label_candidate or len(label_candidate) < 3:
            continue
            
        # Potentially matching a financial row.
        # We look for the "Current Year" value.
        # Heuristic: Scan columns from index 1 to end.
        found_val = None
        
        # Check from left to right (after label)
        for col in row[1:]:
            if col is None: continue
            s_col = str(col).strip()
            
            # Key features of a financial value in IDX:
            # 1. Contains numbers
            # 2. Or is a dash/strip '-'
            # 3. Usually not just a few letters unless it's a small number
            
            if s_col == '-' or s_col == '–' or s_col == '( - )' or s_col == '0':
                found_val = '0'
                break
                
            # Regex to find numbers, potentially with (.) thousand separator or (,) decimal
            # and potentially in parentheses (negative)
            if re.search(r'[\d\(\)]', s_col):
                # We need to distinguish between "Note number" and "Financial Value".
                # Note numbers are usually small (1-digit or 2-digits).
                # Values are usually large (thousand+) or have separators.
                
                # Check if it has thousand separator '.' or is a large number
                # Or check if it's the 3rd column (index 2) - commonly [Label, Note, Value]
                is_likely_note = False
                if len(s_col) < 3 and '.' not in s_col and ',' not in s_col:
                    is_likely_note = True
                
                if not is_likely_note:
                    found_val = s_col
                    break
        
        # Fallback: if we didn't find a "good" value, but there's at least one numeric column, take it
        if not found_val:
            for col in reversed(row[1:]):
                if col and re.search(r'[\d\-–]', str(col)):
                    found_val = str(col)
                    break

        if found_val:
             data.append([label_candidate, found_val])
             
    if not data:
        return pd.DataFrame(columns=['Label', 'Value_Raw', 'Value_Clean'])
        
    df = pd.DataFrame(data, columns=['Label', 'Value_Raw'])
    df['Value_Clean'] = df['Value_Raw'].apply(clean_currency)
    
    return df

def map_financial_data(df_neraca, df_labarugi):
    """
    Mapping extracted rows ke variabel standar menggunakan Regex.
    """
    
    mapping_results = {
        # Neraca
        'total_assets': 0.0,
        'current_assets': 0.0,
        'cash_equivalents': 0.0,
        'inventories': 0.0,
        'total_liabilities': 0.0,
        'current_liabilities': 0.0,
        'total_equity': 0.0,
        # Laba Rugi
        'revenues': 0.0,
        'gross_profit': 0.0,
        'net_income': 0.0,
        'finance_cost': 0.0
    }
    
    # Define regex patterns for each key
    # List of keywords for each item. Logic: First match wins.
    patterns = {
        'total_assets': [r'^jumlah aset$', r'^total assets$', r'jumlah aset \/ total assets'],
        'current_assets': [r'jumlah aset lancar', r'total current assets'],
        'cash_equivalents': [r'kas dan setara kas', r'cash and cash equivalents'],
        'inventories': [r'persediaan', r'inventories'],
        'total_liabilities': [r'^jumlah liabilitas$', r'^total liabilities$'],
        'current_liabilities': [r'jumlah liabilitas jangka pendek', r'total current liabilities'],
        'total_equity': [r'^jumlah ekuitas$', r'^total equity$'],
        
        'revenues': [r'pendapatan usaha', r'pendapatan bersih', r'revenues', r'sales', r'pendapatan pokok'],
        'gross_profit': [r'laba bruto', r'gross profit'],
        'net_income': [
            r'laba .* atribusi .* pemilik entitas induk', 
            r'profit .* attributable to owners of the parent',
            r'laba tahun berjalan', 
            r'profit for the year'
        ],
        'finance_cost': [r'beban keuangan', r'finance costs']
    }
    
    def search_df(df, patterns_list):
        if df.empty or 'Label' not in df.columns:
            return 0.0
        for pattern in patterns_list:
            # Case insensitive search
            # We look for rows where 'Label' matches pattern
            matches = df[df['Label'].str.contains(pattern, case=False, na=False, regex=True)]
            if not matches.empty:
                # Return the Clean Value of the first match
                # Sometimes there are multiple (e.g. Header and Total), usually Total is the one with Number (Headers might be empty or 0 if parsed wrong)
                # But our extractor filters rows with numbers.
                # Optimization: "Jumlah" usually implies the total.
                return matches.iloc[0]['Value_Clean']
        return 0.0

    # Map Neraca Items
    for key in ['total_assets', 'current_assets', 'cash_equivalents', 'inventories', 
                'total_liabilities', 'current_liabilities', 'total_equity']:
        val = search_df(df_neraca, patterns[key])
        mapping_results[key] = val
        
    # Map Laba Rugi Items
    for key in ['revenues', 'gross_profit', 'net_income', 'finance_cost']:
        val = search_df(df_labarugi, patterns[key])
        mapping_results[key] = val
        
    return mapping_results

from schemas import ExtractedFinancials

def format_currency(value):
    """Formats large numbers with thousand separators."""
    if value is None:
        return "-"
    return f"{value:,.0f}"

def calculate_ratios_structured(data: ExtractedFinancials):
    """
    Menghitung rasio finansial berdasarkan objek ExtractedFinancials.
    """
    ratios = {}
    
    # Extract values for easier access
    bs = data.balance_sheet
    is_stmt = data.income_statement
    
    # Helper for safe division
    def div(n, d):
        if n is None or d is None or d.value == 0:
            return 0.0
        return (n.value / d.value * 100)
    
    def div_raw(n, d):
        if n is None or d is None or d.value == 0:
            return 0.0
        return (n.value / d.value)

    # Profitability
    ratios['GPM'] = div(is_stmt.gross_profit, is_stmt.revenues)
    ratios['NPM'] = div(is_stmt.net_income, is_stmt.revenues)
    ratios['ROE'] = div(is_stmt.net_income, bs.total_equity)
    ratios['ROA'] = div(is_stmt.net_income, bs.total_assets)
    
    # Solvency
    ratios['DER'] = div_raw(bs.total_liabilities, bs.total_equity)
    
    # Interest Coverage
    if is_stmt.net_income and is_stmt.finance_cost and is_stmt.finance_cost.value != 0:
        # Note: finance_cost is usually negative in IS, we need to handle signs
        # EBIT Proxy = Net Income + |Finance Cost|
        ebit_proxy = is_stmt.net_income.value + abs(is_stmt.finance_cost.value)
        ratios['Interest Coverage'] = ebit_proxy / abs(is_stmt.finance_cost.value)
    else:
        ratios['Interest Coverage'] = 0.0
    
    # Liquidity
    ratios['Current Ratio'] = div_raw(bs.current_assets, bs.current_liabilities)
    ratios['Cash Ratio'] = div_raw(bs.cash_equivalents, bs.current_liabilities)
    
    # Quick Ratio: (Current Assets - Inventories) / Current Liabilities
    if bs.current_assets and bs.current_liabilities:
        inv_val = bs.inventories.value if bs.inventories else 0.0
        ratios['Quick Ratio'] = (bs.current_assets.value - inv_val) / bs.current_liabilities.value
    else:
        ratios['Quick Ratio'] = 0.0
    
    return ratios
