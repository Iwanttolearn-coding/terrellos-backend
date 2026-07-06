#!/usr/bin/env python3
"""One-off runner: executes migrations/001_bible_local_system.sql against DATABASE_URL."""
import os, sys
import psycopg2

db_url = os.environ.get("DATABASE_URL", "")
if not db_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

sql_path = os.path.join(os.path.dirname(__file__), "migrations", "001_bible_local_system.sql")
with open(sql_path) as f:
    sql = f.read()

print("Connecting to Supabase postgres...")
conn = psycopg2.connect(db_url, connect_timeout=15)
conn.autocommit = True
cur = conn.cursor()
print("Connected OK. Running migration...")
cur.execute(sql)
print("Migration executed successfully.")

cur.execute("SELECT slug, name, scope, is_enabled FROM bible_versions ORDER BY slug;")
rows = cur.fetchall()
print(f"\nbible_versions now has {len(rows)} rows:")
for r in rows:
    print(" -", r)

cur.execute("""
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_name IN
('bible_versions','bible_books','bible_version_books','bible_chapters','bible_verses',
 'saved_bible_studies','bible_import_logs','bible_generation_logs')
ORDER BY table_name;
""")
print("\nTables confirmed present:")
for r in cur.fetchall():
    print(" -", r[0])

cur.close()
conn.close()
