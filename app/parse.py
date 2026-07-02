import pandas as pd
import glob, re, sqlite3, os

RAW_DIR = '/data/raw/EXL'
DB_PATH = '/data/raw/exl_financials.db'

YEAR_RE = re.compile(r'^(20\d\d)(\.0)?(\(\d+\))?$')

def find_year_header_row(df):
    for i, row in df.iterrows():
        vals = [str(v).strip() for v in row.tolist()]
        year_cells = [v for v in vals if YEAR_RE.match(v)]
        if len(year_cells) >= 2:
            return i
    return None

def get_year_columns(df, header_row):
    row = df.iloc[header_row]
    cols = {}
    for col_idx, val in row.items():
        m = YEAR_RE.match(str(val).strip())
        if m:
            cols[col_idx] = int(m.group(1))
    return cols

def find_row(df, label_col, keyword, exclude=None):
    for i, val in df[label_col].items():
        if pd.isna(val):
            continue
        s = str(val).strip().lower()
        if keyword in s and (exclude is None or exclude not in s):
            return i
    return None

def to_number(v):
    if pd.isna(v):
        return None
    s = str(v).strip().replace(',', '')
    if s in ('—', '-', ''):
        return 0.0
    s = s.replace('(', '-').replace(')', '')
    try:
        return float(s)
    except ValueError:
        return None

records = []

for fpath in sorted(glob.glob(os.path.join(RAW_DIR, '*.xls'))):
    filing_year = int(os.path.basename(fpath).replace('.xls',''))
    df = pd.read_excel(fpath, sheet_name='income', header=None)
    label_col = 0
    header_row = find_year_header_row(df)
    if header_row is None:
        print(f'{filing_year}: no year header found, skipping')
        continue
    year_cols = get_year_columns(df, header_row)
    if not year_cols:
        print(f'{filing_year}: no year columns parsed, skipping')
        continue

    rev_row = find_row(df, label_col, 'revenues, net')
    opinc_row = find_row(df, label_col, 'income from operations')
    eps_row = find_row(df, label_col, 'diluted')

    if rev_row is None or opinc_row is None or eps_row is None:
        print(f'{filing_year}: missing a row (rev={rev_row}, opinc={opinc_row}, eps={eps_row})')
        continue

    for col_idx, fy in sorted(year_cols.items(), key=lambda x: -x[1]):
        rev = to_number(df.iat[rev_row, col_idx])
        opinc = to_number(df.iat[opinc_row, col_idx])
        eps = to_number(df.iat[eps_row, col_idx])
        if rev is None or rev == 0:
            continue
        op_margin = round((opinc / rev) * 100, 2) if opinc is not None else None
        records.append((fy, 'revenue', rev, filing_year))
        records.append((fy, 'operating_margin_pct', op_margin, filing_year))
        records.append((fy, 'diluted_eps', eps, filing_year))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute('DROP TABLE IF EXISTS silver_financial_facts')
cur.execute('DROP TABLE IF EXISTS silver_financial_facts_dedup')
cur.execute('''
CREATE TABLE silver_financial_facts (
    fiscal_year INTEGER,
    metric_name TEXT,
    value REAL,
    source_filing_year INTEGER,
    PRIMARY KEY (fiscal_year, metric_name, source_filing_year)
)
''')
cur.executemany(
    'INSERT OR IGNORE INTO silver_financial_facts (fiscal_year, metric_name, value, source_filing_year) VALUES (?,?,?,?)',
    records
)
conn.commit()

# Dedup: prefer the value reported in the filing FOR that fiscal year (source_filing_year = fiscal_year + 1, i.e. filed next year)
# over restated/comparative values shown in later filings. Fall back to earliest available report.
cur.execute('''
CREATE TABLE silver_financial_facts_dedup AS
SELECT fiscal_year, metric_name, value, source_filing_year
FROM silver_financial_facts s1
WHERE source_filing_year = (
    SELECT MIN(source_filing_year) FROM silver_financial_facts s2
    WHERE s2.fiscal_year = s1.fiscal_year AND s2.metric_name = s1.metric_name
)
''')
conn.commit()

print('Rows (raw):', cur.execute('SELECT COUNT(*) FROM silver_financial_facts').fetchone()[0])
print('Rows (deduped):', cur.execute('SELECT COUNT(*) FROM silver_financial_facts_dedup').fetchone()[0])
print()
for row in cur.execute('SELECT fiscal_year, metric_name, value, source_filing_year FROM silver_financial_facts_dedup ORDER BY metric_name, fiscal_year'):
    print(row)

conn.close()