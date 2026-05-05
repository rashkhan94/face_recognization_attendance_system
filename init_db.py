"""Initialize PostgreSQL database tables for FRAS."""
import os

DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import psycopg2
    # Fix Render's postgres:// to postgresql://
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS organizations (
        id SERIAL PRIMARY KEY,
        org_name TEXT NOT NULL,
        room_type TEXT DEFAULT 'Classroom',
        venue_number TEXT DEFAULT '',
        cabin_number TEXT DEFAULT '',
        admin_user TEXT DEFAULT '',
        admin_password TEXT NOT NULL,
        capacity INTEGER DEFAULT 0,
        admin_logged_today TEXT,
        open_time TEXT DEFAULT '06:00',
        close_time TEXT DEFAULT '22:00',
        total_classes INTEGER DEFAULT 30
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id SERIAL PRIMARY KEY,
        org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        roll_number TEXT NOT NULL,
        age INTEGER DEFAULT 0,
        class_name TEXT DEFAULT 'N/A',
        face_encoding TEXT,
        registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(org_id, roll_number)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id SERIAL PRIMARY KEY,
        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        UNIQUE(student_id, date)
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS public_venues (
        id SERIAL PRIMARY KEY,
        venue_name TEXT NOT NULL,
        venue_type TEXT DEFAULT 'Hall',
        venue_number TEXT DEFAULT '',
        capacity INTEGER DEFAULT 0,
        status TEXT DEFAULT 'available',
        current_booker TEXT,
        booked_org_id INTEGER,
        booked_from TEXT,
        booked_until TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS venue_requests (
        id SERIAL PRIMARY KEY,
        venue_id INTEGER REFERENCES public_venues(id) ON DELETE CASCADE,
        org_id INTEGER REFERENCES organizations(id) ON DELETE CASCADE,
        org_name TEXT,
        admin_name TEXT,
        booking_date TEXT,
        start_time TEXT,
        end_time TEXT,
        purpose TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        reviewed_at TIMESTAMP
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS super_admin (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )""")

    # Insert default superadmin if not exists
    cur.execute("SELECT id FROM super_admin WHERE username='superadmin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO super_admin (username, password) VALUES ('superadmin', 'admin123')")
        print("Default super admin created: superadmin / admin123")

    conn.commit()
    cur.close()
    conn.close()
    print("PostgreSQL tables initialized successfully!")
else:
    print("No DATABASE_URL found. Skipping PostgreSQL init (using SQLite locally).")
