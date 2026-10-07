"""Build the Capital IQ Excel template for 100 Indian listed companies.

Open the generated workbook in Excel with the S&P Capital IQ plug-in and
refresh: every cell in the Data sheet pulls one financial line item for one
company and fiscal year. The filled workbook is then read back by the
dashboard, which calculates the 25 ratios itself (see the "Ratio Formulas"
sheet), so every company is treated identically.

Run:  python scripts/make_capiq_template.py
"""

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

OUT = Path(__file__).resolve().parent.parent / "data" / "capiq_template.xlsx"

N_YEARS = 10  # IQ_FY (latest = FY2026 for March year-ends) back to IQ_FY-9 (FY2017)

# (Industry, company name, NSE symbol, note)
COMPANIES = [
    ("Technology / Software", "Tata Consultancy Services", "TCS", ""),
    ("Technology / Software", "Infosys", "INFY", ""),
    ("Technology / Software", "HCL Technologies", "HCLTECH", ""),
    ("Technology / Software", "Wipro", "WIPRO", ""),
    ("Technology / Software", "Tech Mahindra", "TECHM", ""),
    ("Technology / Software", "LTIMindtree", "LTIM", "LTI + Mindtree merger (Nov 2022)"),
    ("Technology / Software", "Persistent Systems", "PERSISTENT", ""),
    ("Technology / Software", "Coforge", "COFORGE", ""),
    ("Technology / Software", "Mphasis", "MPHASIS", ""),
    ("Technology / Software", "Oracle Financial Services Software", "OFSS", ""),
    ("Technology / Software", "Tata Elxsi", "TATAELXSI", ""),
    ("Technology / Software", "L&T Technology Services", "LTTS", "Listed Sep 2016"),
    ("Technology / Software", "KPIT Technologies", "KPITTECH", "Demerged/relisted 2019; earlier years may be missing"),
    ("Technology / Software", "Cyient", "CYIENT", ""),
    ("Technology / Software", "Sonata Software", "SONATSOFTW", ""),
    ("Technology / Software", "Birlasoft", "BSOFT", ""),
    ("Technology / Software", "Zensar Technologies", "ZENSARTECH", ""),
    ("Technology / Software", "Mastek", "MASTEK", ""),
    ("Technology / Software", "Intellect Design Arena", "INTELLECT", ""),
    ("Technology / Software", "eClerx Services", "ECLERX", ""),
    ("Technology / Software", "Newgen Software", "NEWGEN", "Listed Jan 2018"),
    ("Technology / Software", "Tanla Platforms", "TANLA", ""),
    ("Technology / Software", "Sasken Technologies", "SASKEN", ""),
    ("Technology / Software", "Happiest Minds Technologies", "HAPPSTMNDS", "Listed Sep 2020"),
    ("Technology / Software", "Nucleus Software Exports", "NUCLEUS", ""),
    ("Retail / E-Commerce", "Avenue Supermarts (DMart)", "DMART", "Listed Mar 2017"),
    ("Retail / E-Commerce", "Trent", "TRENT", ""),
    ("Retail / E-Commerce", "Titan Company", "TITAN", ""),
    ("Retail / E-Commerce", "Aditya Birla Fashion and Retail", "ABFRL", "Madura business demerged 2025"),
    ("Retail / E-Commerce", "Shoppers Stop", "SHOPERSTOP", ""),
    ("Retail / E-Commerce", "V-Mart Retail", "VMART", ""),
    ("Retail / E-Commerce", "Bata India", "BATAINDIA", ""),
    ("Retail / E-Commerce", "Relaxo Footwears", "RELAXO", ""),
    ("Retail / E-Commerce", "Page Industries", "PAGEIND", ""),
    ("Retail / E-Commerce", "Jubilant FoodWorks", "JUBLFOOD", ""),
    ("Retail / E-Commerce", "Westlife Foodworld", "WESTLIFE", ""),
    ("Retail / E-Commerce", "Arvind Fashions", "ARVINDFASN", "Listed 2018"),
    ("Retail / E-Commerce", "Spencer's Retail", "SPENCERS", "Listed 2019"),
    ("Retail / E-Commerce", "FSN E-Commerce (Nykaa)", "NYKAA", "Listed Nov 2021"),
    ("Retail / E-Commerce", "Eternal (Zomato)", "ETERNAL", "Listed Jul 2021; renamed from Zomato 2025"),
    ("Retail / E-Commerce", "Info Edge (Naukri)", "NAUKRI", ""),
    ("Retail / E-Commerce", "IndiaMART InterMESH", "INDIAMART", "Listed Jul 2019"),
    ("Retail / E-Commerce", "Just Dial", "JUSTDIAL", ""),
    ("Retail / E-Commerce", "CarTrade Tech", "CARTRADE", "Listed Aug 2021"),
    ("Retail / E-Commerce", "Easy Trip Planners (EaseMyTrip)", "EASEMYTRIP", "Listed Mar 2021"),
    ("Retail / E-Commerce", "Metro Brands", "METROBRAND", "Listed Dec 2021"),
    ("Retail / E-Commerce", "Devyani International", "DEVYANI", "Listed Aug 2021"),
    ("Retail / E-Commerce", "Kalyan Jewellers", "KALYANKJIL", "Listed Mar 2021"),
    ("Retail / E-Commerce", "Campus Activewear", "CAMPUS", "Listed May 2022"),
    ("Retail / E-Commerce", "Ethos", "ETHOSLTD", "Listed May 2022"),
    ("Heavy Manufacturing", "Larsen & Toubro", "LT", ""),
    ("Heavy Manufacturing", "Bharat Heavy Electricals", "BHEL", ""),
    ("Heavy Manufacturing", "Siemens", "SIEMENS", "Sep year-end; energy business demerged 2025"),
    ("Heavy Manufacturing", "ABB India", "ABB", "Dec year-end"),
    ("Heavy Manufacturing", "Cummins India", "CUMMINSIND", ""),
    ("Heavy Manufacturing", "Thermax", "THERMAX", ""),
    ("Heavy Manufacturing", "Bharat Forge", "BHARATFORG", ""),
    ("Heavy Manufacturing", "Tata Steel", "TATASTEEL", ""),
    ("Heavy Manufacturing", "JSW Steel", "JSWSTEEL", ""),
    ("Heavy Manufacturing", "Hindalco Industries", "HINDALCO", ""),
    ("Heavy Manufacturing", "Steel Authority of India", "SAIL", ""),
    ("Heavy Manufacturing", "Jindal Steel & Power", "JINDALSTEL", ""),
    ("Heavy Manufacturing", "UltraTech Cement", "ULTRACEMCO", ""),
    ("Heavy Manufacturing", "Hindustan Aeronautics", "HAL", "Listed Mar 2018"),
    ("Heavy Manufacturing", "Bharat Electronics", "BEL", ""),
    ("Heavy Manufacturing", "BEML", "BEML", ""),
    ("Heavy Manufacturing", "AIA Engineering", "AIAENG", ""),
    ("Heavy Manufacturing", "Kirloskar Oil Engines", "KIRLOSENG", ""),
    ("Heavy Manufacturing", "Elgi Equipments", "ELGIEQUIP", ""),
    ("Heavy Manufacturing", "Timken India", "TIMKEN", ""),
    ("Heavy Manufacturing", "SKF India", "SKFINDIA", ""),
    ("Heavy Manufacturing", "Grindwell Norton", "GRINDWELL", ""),
    ("Heavy Manufacturing", "Ashok Leyland", "ASHOKLEY", ""),
    ("Heavy Manufacturing", "KEC International", "KEC", ""),
    ("Heavy Manufacturing", "Schaeffler India", "SCHAEFFLER", "Dec year-end"),
    ("Banking / Finance", "HDFC Bank", "HDFCBANK", "Merged with HDFC Ltd Jul 2023"),
    ("Banking / Finance", "ICICI Bank", "ICICIBANK", ""),
    ("Banking / Finance", "State Bank of India", "SBIN", "Absorbed associate banks 2017"),
    ("Banking / Finance", "Kotak Mahindra Bank", "KOTAKBANK", ""),
    ("Banking / Finance", "Axis Bank", "AXISBANK", ""),
    ("Banking / Finance", "IndusInd Bank", "INDUSINDBK", ""),
    ("Banking / Finance", "Bank of Baroda", "BANKBARODA", "Merged Vijaya & Dena 2019"),
    ("Banking / Finance", "Punjab National Bank", "PNB", "Merged OBC & United 2020"),
    ("Banking / Finance", "Canara Bank", "CANBK", "Merged Syndicate 2020"),
    ("Banking / Finance", "Union Bank of India", "UNIONBANK", "Merged Andhra & Corporation 2020"),
    ("Banking / Finance", "Federal Bank", "FEDERALBNK", ""),
    ("Banking / Finance", "IDFC First Bank", "IDFCFIRSTB", "Mergers 2018 and 2024"),
    ("Banking / Finance", "Bandhan Bank", "BANDHANBNK", "Listed Mar 2018"),
    ("Banking / Finance", "AU Small Finance Bank", "AUBANK", "Listed Jul 2017"),
    ("Banking / Finance", "Yes Bank", "YESBANK", "Reconstructed 2020"),
    ("Banking / Finance", "IDBI Bank", "IDBI", ""),
    ("Banking / Finance", "Indian Bank", "INDIANB", "Merged Allahabad Bank 2020"),
    ("Banking / Finance", "Bank of India", "BANKINDIA", ""),
    ("Banking / Finance", "RBL Bank", "RBLBANK", "Listed Aug 2016"),
    ("Banking / Finance", "City Union Bank", "CUB", ""),
    ("Banking / Finance", "Karur Vysya Bank", "KARURVYSYA", ""),
    ("Banking / Finance", "South Indian Bank", "SOUTHBANK", ""),
    ("Banking / Finance", "Bank of Maharashtra", "MAHABANK", ""),
    ("Banking / Finance", "Central Bank of India", "CENTRALBK", ""),
    ("Banking / Finance", "DCB Bank", "DCBBANK", ""),
]

# (column header, Capital IQ mnemonic, used for). Mnemonics sit in row 3 of
# the Data sheet, so fixing one cell fixes the whole column.
ITEMS = [
    ("Period End Date", "IQ_PERIODDATE", "Labels the fiscal year"),
    ("Total Revenue", "IQ_TOTAL_REV", "Margins, turnover, P/S"),
    ("Cost of Goods Sold", "IQ_COGS", "Inventory turnover"),
    ("Gross Profit", "IQ_GP", "Gross margin"),
    ("EBIT", "IQ_EBIT", "Operating margin, interest coverage"),
    ("EBITDA", "IQ_EBITDA", "EV/EBITDA, DSCR"),
    ("Interest Expense", "IQ_INTEREST_EXP", "Interest coverage, DSCR"),
    ("Net Income", "IQ_NI", "Net margin, ROA, ROE, P/E"),
    ("Total Current Assets", "IQ_TOTAL_CA", "Liquidity ratios"),
    ("Total Current Liabilities", "IQ_TOTAL_CL", "Liquidity ratios"),
    ("Cash & ST Investments", "IQ_CASH_ST_INVEST", "Cash ratio"),
    ("Inventory", "IQ_INVENTORY", "Quick ratio, inventory turnover"),
    ("Total Receivables", "IQ_TOTAL_RECEIV", "Receivables turnover"),
    ("Total Assets", "IQ_TOTAL_ASSETS", "ROA, asset turnover, leverage"),
    ("Total Debt", "IQ_TOTAL_DEBT", "Debt ratios"),
    ("Total Equity", "IQ_TOTAL_EQUITY", "ROE, D/E, P/B"),
    ("Cash from Operations", "IQ_CASH_OPER", "Operating cash flow ratio"),
    ("Debt Repaid", "IQ_TOTAL_DEBT_REPAID", "DSCR"),
    ("Dividend per Share", "IQ_DIV_SHARE", "Dividend yield"),
    ("Share Price (period end)", "IQ_CLOSEPRICE", "Dividend yield"),
    ("Market Cap", "IQ_MARKETCAP", "P/E, P/S, P/B"),
    ("Total Enterprise Value", "IQ_TEV", "EV/EBITDA"),
    ("Total Deposits (banks)", "IQ_TOTAL_DEPOSITS", "Bank liquidity"),
    ("Net Interest Income (banks)", "IQ_NET_INTEREST_INC", "Bank margins"),
]

RATIO_FORMULAS = [
    ("Liquidity", "Current Ratio", "Total Current Assets / Total Current Liabilities"),
    ("Liquidity", "Quick Ratio", "(Total Current Assets − Inventory) / Total Current Liabilities"),
    ("Liquidity", "Cash Ratio", "Cash & ST Investments / Total Current Liabilities"),
    ("Liquidity", "Operating Cash Flow Ratio", "Cash from Operations / Total Current Liabilities"),
    ("Liquidity", "Working Capital Ratio", "(Total Current Assets − Total Current Liabilities) / Total Assets"),
    ("Profitability", "Gross Profit Margin", "Gross Profit / Total Revenue × 100"),
    ("Profitability", "Operating Profit Margin", "EBIT / Total Revenue × 100"),
    ("Profitability", "Net Profit Margin", "Net Income / Total Revenue × 100"),
    ("Profitability", "Return on Assets (ROA)", "Net Income / Total Assets × 100"),
    ("Profitability", "Return on Equity (ROE)", "Net Income / Total Equity × 100"),
    ("Efficiency", "Asset Turnover", "Total Revenue / Total Assets"),
    ("Efficiency", "Inventory Turnover", "Cost of Goods Sold / Inventory"),
    ("Efficiency", "Receivables Turnover", "Total Revenue / Total Receivables"),
    ("Efficiency", "Days Sales Outstanding (DSO)", "365 / Receivables Turnover"),
    ("Efficiency", "Days Inventory Outstanding (DIO)", "365 / Inventory Turnover"),
    ("Leverage", "Debt-to-Equity", "Total Debt / Total Equity"),
    ("Leverage", "Debt-to-Assets", "Total Debt / Total Assets"),
    ("Leverage", "Interest Coverage Ratio", "EBIT / Interest Expense"),
    ("Leverage", "Equity Multiplier", "Total Assets / Total Equity"),
    ("Leverage", "Debt Service Coverage Ratio (DSCR)", "EBITDA / (Interest Expense + Debt Repaid)"),
    ("Valuation", "Price-to-Earnings (P/E)", "Market Cap / Net Income"),
    ("Valuation", "Price-to-Sales (P/S)", "Market Cap / Total Revenue"),
    ("Valuation", "Price-to-Book (P/B)", "Market Cap / Total Equity"),
    ("Valuation", "EV/EBITDA", "Total Enterprise Value / EBITDA"),
    ("Valuation", "Dividend Yield", "Dividend per Share / Share Price × 100"),
]

HEADER_FILL = PatternFill("solid", fgColor="1E4620")
HEADER_FONT = Font(bold=True, color="FFFFFF")
MNEMONIC_FILL = PatternFill("solid", fgColor="FFF2CC")
BOLD = Font(bold=True)

INSTRUCTIONS = [
    "Capital IQ data template: 100 Indian listed companies × 10 fiscal years (FY2017–FY2026)",
    "",
    "HOW TO FILL",
    "1. Open this file in Excel on a computer with the S&P Capital IQ Office plug-in, and sign in.",
    "2. Go to the 'Data' sheet. In the Capital IQ ribbon choose Refresh → Refresh Workbook.",
    "   10,000 rows of formulas take a few minutes. If your account has a download limit, refresh one industry at a time.",
    "3. Any column showing an error: select a cell, open Formula Builder, find the right data item, and type",
    "   its mnemonic into the yellow cell in row 3 of that column. The whole column updates.",
    "4. Save as a normal .xlsx. Optionally use Capital IQ 'Paste as values' first so the file opens without the plug-in.",
    "5. Upload the saved file. The dashboard calculates the 25 ratios from these figures (see 'Ratio Formulas').",
    "",
    "PERIODS",
    "IQ_FY is each company's latest reported fiscal year; IQ_FY-1 the year before, and so on.",
    "For March year-end companies IQ_FY = FY2026 (Apr 2025–Mar 2026). Dec/Sep year-end companies (ABB, Schaeffler,",
    "Siemens) will show their own latest year; the Period End Date column records exactly which year each row is.",
    "",
    "NOTES",
    "• Banks do not report inventory, COGS or current assets/liabilities; those cells will be blank or NA. That is expected.",
    "• Companies listed recently (see 'Companies' sheet) will have fewer than 10 years.",
    "• Figures come back in Capital IQ's default units (INR millions). Ratios are unit-free, so this does not matter.",
    "• Check your institution's Capital IQ licence before sharing the filled file outside your coursework.",
]


def build() -> Path:
    wb = Workbook()

    ws = wb.active
    ws.title = "Instructions"
    for i, line in enumerate(INSTRUCTIONS, start=1):
        cell = ws.cell(row=i, column=1, value=line)
        if i == 1 or line in ("HOW TO FILL", "PERIODS", "NOTES"):
            cell.font = Font(bold=True, size=13 if i == 1 else 11)
    ws.column_dimensions["A"].width = 130

    cs = wb.create_sheet("Companies")
    cs.append(["Industry", "Company", "NSE Symbol", "Capital IQ Ticker", "Note"])
    for industry, name, symbol, note in COMPANIES:
        cs.append([industry, name, symbol, f"NSEI:{symbol}", note])
    for c, width in zip("ABCDE", (24, 38, 14, 20, 52)):
        cs.column_dimensions[c].width = width
    for cell in cs[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    cs.freeze_panes = "A2"

    ds = wb.create_sheet("Data")
    fixed = ["Industry", "Company", "Capital IQ Ticker", "Period"]
    first_item_col = len(fixed) + 1
    ds.cell(row=1, column=1, value="Row 2 = item name, row 3 (yellow) = Capital IQ mnemonic used by every formula below it.")
    ds.cell(row=1, column=1).font = Font(italic=True)
    for j, name in enumerate(fixed + [i[0] for i in ITEMS], start=1):
        cell = ds.cell(row=2, column=j, value=name)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for j, (_, mnemonic, _) in enumerate(ITEMS, start=first_item_col):
        cell = ds.cell(row=3, column=j, value=mnemonic)
        cell.fill, cell.font = MNEMONIC_FILL, BOLD

    row = 4
    for industry, name, symbol, _ in COMPANIES:
        ticker = f"NSEI:{symbol}"
        for k in range(N_YEARS):
            period = "IQ_FY" if k == 0 else f"IQ_FY-{k}"
            ds.cell(row=row, column=1, value=industry)
            ds.cell(row=row, column=2, value=name)
            ds.cell(row=row, column=3, value=ticker)
            ds.cell(row=row, column=4, value=period)
            for j in range(first_item_col, first_item_col + len(ITEMS)):
                col = get_column_letter(j)
                ds.cell(row=row, column=j, value=f"=CIQ($C{row},{col}$3,{period})")
            row += 1
    for c, width in zip("ABCD", (22, 34, 18, 10)):
        ds.column_dimensions[c].width = width
    for j in range(first_item_col, first_item_col + len(ITEMS)):
        ds.column_dimensions[get_column_letter(j)].width = 16
    ds.row_dimensions[2].height = 32
    ds.freeze_panes = ds.cell(row=4, column=first_item_col)

    rs = wb.create_sheet("Ratio Formulas")
    rs.append(["Category", "Ratio", "Formula (from the Data sheet columns)"])
    for r in RATIO_FORMULAS:
        rs.append(list(r))
    for cell in rs[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for c, width in zip("ABC", (16, 36, 70)):
        rs.column_dimensions[c].width = width

    ms = wb.create_sheet("Mnemonics")
    ms.append(["Data Sheet Column", "Capital IQ Mnemonic", "Used For"])
    for item in ITEMS:
        ms.append(list(item))
    for cell in ms[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
    for c, width in zip("ABC", (30, 26, 40)):
        ms.column_dimensions[c].width = width

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    return OUT


if __name__ == "__main__":
    assert len(COMPANIES) == 100 and len({c[2] for c in COMPANIES}) == 100
    path = build()
    print(f"Wrote {path}")
