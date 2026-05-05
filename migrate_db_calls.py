import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace cur = conn.cursor() followed by cur.execute → db_execute
# Pattern: conn.cursor()\n...cur.execute("SQL", params) → db_execute(conn, "SQL", params)
# We need to remove standalone conn.cursor() lines and convert cur.execute to db_execute

# Remove standalone "cur = conn.cursor()" lines  
code = re.sub(r'\n\s*cur\s*=\s*conn\.cursor\(\)\n', '\n', code)
# Also handle inline: conn=get_db(); cur=conn.cursor()
code = code.replace('; cur=conn.cursor()', '')

# Replace cur.execute( with cur = db_execute(conn, 
# But only where it's a statement, not already db_execute
code = re.sub(r'(\s+)cur\.execute\(', r'\1cur = db_execute(conn, ', code)
# Handle inline cur.execute after semicolons
code = code.replace('; cur.execute(', '; cur = db_execute(conn, ')

# Replace cur.fetchall() with db_fetchall(cur) in assignments
code = re.sub(r'(\w+)\s*=\s*cur\.fetchall\(\)', r'\1 = db_fetchall(cur)', code)
# Replace standalone cur.fetchall() 
code = code.replace('for student in cur.fetchall():', 'for student in db_fetchall(cur):')

# Replace cur.fetchone() with db_fetchone(cur) in assignments
code = re.sub(r'(\w+)\s*=\s*cur\.fetchone\(\)', r'\1 = db_fetchone(cur)', code)
# Handle dict(cur.fetchone()) patterns
code = code.replace('dict(cur.fetchone())', 'db_fetchone(cur)')

# Handle "if cur.fetchone():" and "if not cur.fetchone():"
code = code.replace('if cur.fetchone():', 'if db_fetchone(cur):')
code = code.replace('if not cur.fetchone():', 'if not db_fetchone(cur):')

# Remove dict() wrapping on site/row since db_fetchone already returns dict
code = code.replace('site=dict(site)', '')
code = code.replace('s = dict(site)', 's = site')
code = code.replace('d=dict(s)', 'd=s')
code = code.replace('d=dict(r)', 'd=r')
code = code.replace('o=dict(org)', 'o=org')
code = code.replace('r=dict(req)', 'r=req')
code = code.replace('v=dict(venue)', 'v=venue')
code = code.replace('s = dict(student)', 's = student')

# Replace dict_rows() calls with db_fetchall references
code = code.replace('return jsonify(dict_rows(sites))', 'return jsonify(sites)')
code = code.replace('return jsonify(dict_rows(students))', 'return jsonify(students)')
code = code.replace('return jsonify(dict_rows(absents))', 'return jsonify(absents)')
code = code.replace('return jsonify(dict_rows(rows))', 'return jsonify(rows)')

# Fix sqlite3.IntegrityError to also catch psycopg2 errors
code = code.replace('except sqlite3.IntegrityError:', 'except Exception as ie:\n        if "UNIQUE" in str(ie).upper() or "unique" in str(ie) or "duplicate" in str(ie).lower():')

# Fix datetime('now') for PostgreSQL - replace in SQL strings
code = code.replace("datetime('now')", "CURRENT_TIMESTAMP")

# Fix the db_execute that references psycopg2 when it might not be available
old_db_execute = '''    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) if USE_PG else conn.cursor()'''
new_db_execute = '''    if USE_PG:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()'''
code = code.replace(old_db_execute, new_db_execute)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Migration complete! All database calls updated for dual SQLite/PostgreSQL support.")
