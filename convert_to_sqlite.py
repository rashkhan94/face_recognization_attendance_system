"""Convert app.py from MySQL to SQLite"""
import re

with open('app.py', 'r') as f:
    code = f.read()

# Backup
with open('app_mysql_backup.py', 'w') as f:
    f.write(code)

# Replace imports
code = code.replace("import mysql.connector", "import sqlite3")

# Replace get_db
old_db = '''def get_db():
    return mysql.connector.connect(
        host="localhost", user="root",
        password="f@h@d321", database="smart_attendance"
    )'''
new_db = '''DB_PATH = 'smart_attendance.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn'''
code = code.replace(old_db, new_db)

# Replace cursor(dictionary=True) with cursor()
code = code.replace('.cursor(dictionary=True)', '.cursor()')
code = code.replace('.cursor()', '.cursor()')

# Replace %s with ? for parameterized queries
# This is tricky - need to handle it carefully
lines = code.split('\n')
new_lines = []
for line in lines:
    # Skip lines that are comments or don't have SQL
    if '%s' in line and ('execute' in line or 'VALUES' in line or 'WHERE' in line or 'AND' in line or 'SET' in line or 'JOIN' in line or 'ON' in line or 'NOT IN' in line or 'INSERT' in line or 'UPDATE' in line or 'SELECT' in line or 'DELETE' in line or 'GROUP' in line or 'LEFT' in line or 'CASE' in line or 'FROM' in line or 'booked_until' in line):
        line = line.replace('%s', '?')
    new_lines.append(line)
code = '\n'.join(new_lines)

# Replace MySQL-specific syntax
code = code.replace('CURDATE()', "date('now')")
code = code.replace('NOW()', "datetime('now')")
code = code.replace('AUTO_INCREMENT', '')
code = code.replace('LONGTEXT', 'TEXT')

# Replace IntegrityError reference
code = code.replace('mysql.connector.IntegrityError', 'sqlite3.IntegrityError')

# Fix row access - sqlite3.Row supports dict-like access already
# But fetchall returns Row objects, need to convert for jsonify
old_jsonify_pattern = "return jsonify(sites)"
code = code.replace("return jsonify(sites)", "return jsonify([dict(r) for r in sites])")
code = code.replace("return jsonify(students)", "return jsonify([dict(r) for r in students])")
code = code.replace("return jsonify(venues)", "return jsonify([dict(r) for r in venues])")
code = code.replace("return jsonify(absents)", "return jsonify([dict(r) for r in absents])")
code = code.replace("return jsonify(rows)", "return jsonify([dict(r) for r in rows])")

# Write converted file
with open('app.py', 'w') as f:
    f.write(code)

print("Conversion done! Now run: python init_db.py && python app.py")
