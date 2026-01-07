from pydantic import BaseModel, Field
from typing import Optional

class FinancialMetric(BaseModel):
    raw_text: str = Field(..., description="Teks asli yang ditemukan di PDF (misal: 'Jumlah Aset Lancar')")
    value: float = Field(..., description="Nilai numerik yang sudah dibersihkan. Pastikan dalam satuan penuh (bukan jutaan).")
    
class BalanceSheet(BaseModel):
    total_assets: Optional[FinancialMetric] = Field(None, description="Total Aset / Jumlah Aset")
    total_liabilities: Optional[FinancialMetric] = Field(None, description="Total Liabilitas / Jumlah Liabilitas")
    total_equity: Optional[FinancialMetric] = Field(None, description="Total Ekuitas / Jumlah Ekuitas")
    current_assets: Optional[FinancialMetric] = Field(None, description="Aset Lancar / Jumlah Aset Lancar")
    current_liabilities: Optional[FinancialMetric] = Field(None, description="Liabilitas Jangka Pendek / Jumlah Liabilitas Jangka Pendek")
    cash_equivalents: Optional[FinancialMetric] = Field(None, description="Kas dan Setara Kas")
    inventories: Optional[FinancialMetric] = Field(None, description="Persediaan")

class IncomeStatement(BaseModel):
    revenues: Optional[FinancialMetric] = Field(None, description="Pendapatan Usaha / Penjualan Bersih / Revenues")
    gross_profit: Optional[FinancialMetric] = Field(None, description="Laba Bruto / Gross Profit")
    net_income: Optional[FinancialMetric] = Field(None, description="Laba Bersih Tahun Berjalan / Profit for the Year")
    finance_cost: Optional[FinancialMetric] = Field(None, description="Beban Keuangan / Finance Costs")

class ExtractedFinancials(BaseModel):
    company_name: str = Field(..., description="Nama Perusahaan")
    report_period: str = Field(..., description="Periode Laporan (misal: '31 Maret 2025')")
    currency: str = Field(..., description="Mata Uang Laporan (IDR/USD)")
    is_psak_111: bool = Field(False, description="Set True jika data ini berasal dari halaman penyesuaian/lampiran 'Setelah PSAK 111'")
    balance_sheet: BalanceSheet
    income_statement: IncomeStatement
