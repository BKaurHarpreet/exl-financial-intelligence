import sqlite3
import os

db_path = r"C:\Users\Harmeet Kaur\OneDrive\ドキュメント\exl-financial-intelligence\data\exl_financial_intelligence.db"
print("File exists:", os.path.exists(db_path))
if os.path.exists(db_path):
    print("File size:", os.path.getsize(db_path))

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [t[0] for t in cursor.fetchall()]
print("Tables in database:", tables)

# Print counts for each table
for table in tables:
    try:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"Table '{table}': {count} rows")
    except Exception as e:
        print(f"Error counting table '{table}': {e}")

conn.close()
