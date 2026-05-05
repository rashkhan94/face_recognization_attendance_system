import sqlite3
c = sqlite3.connect('smart_attendance.db')
try:
    c.execute("ALTER TABLE organizations ADD COLUMN open_time TEXT DEFAULT '06:00'")
    print("Added open_time")
except:
    print("open_time already exists")
try:
    c.execute("ALTER TABLE organizations ADD COLUMN close_time TEXT DEFAULT '22:00'")
    print("Added close_time")
except:
    print("close_time already exists")
c.commit()
c.close()
print("Done!")
