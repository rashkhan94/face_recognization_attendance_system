from flask import Flask, render_template, request, jsonify, session, redirect
import sqlite3
import os
try:
    import psycopg2
    import psycopg2.extras
    PG_AVAILABLE = True
except ImportError:
    PG_AVAILABLE = False
try:
    import face_recognition
    FACE_RECOGNITION_AVAILABLE = True
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
try:
    import cv2
    import numpy as np
except ImportError:
    pass
import base64
import json
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'fras_hierarchy_key_2024_secure')
DB_PATH = 'smart_attendance.db'
DATABASE_URL = os.environ.get('DATABASE_URL', '')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
USE_PG = bool(DATABASE_URL and PG_AVAILABLE)

def get_db():
    if USE_PG:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

def db_execute(conn, sql, params=None):
    """Execute a query, translating ? to %s for PostgreSQL."""
    if USE_PG:
        sql = sql.replace('?', '%s')
        # Fix SQLite date functions
        sql = sql.replace("date('now')", "CURRENT_DATE")
    if USE_PG:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur

def db_fetchall(cur):
    """Fetch all rows as list of dicts."""
    if USE_PG:
        return cur.fetchall()  # RealDictCursor returns dicts
    return [dict(r) for r in cur.fetchall()]

def db_fetchone(cur):
    """Fetch one row as dict."""
    row = db_fetchone(cur)
    if row is None:
        return None
    if USE_PG:
        return row  # RealDictCursor returns dict
    return dict(row)

def dict_rows(rows):
    return [dict(r) for r in rows]

def decode_image(b64_str):
    _, encoded = b64_str.split(",", 1)
    arr = np.frombuffer(base64.b64decode(encoded), np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

def admin_required():
    return 'admin_org_id' in session

def sa_required():
    return 'super_admin' in session

# PAGE ROUTES
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/portal/<int:org_id>')
def user_portal(org_id):
    conn = get_db()
    cur = db_execute(conn, "SELECT id, org_name, room_type, venue_number, open_time, close_time FROM organizations WHERE id=?", (org_id,))
    site = db_fetchone(cur)
    conn.close()
    if not site: return redirect('/')
    return render_template('user_scanner.html', site=site)

@app.route('/admin/login/<int:org_id>')
def admin_login_page(org_id):
    conn = get_db()
    cur = db_execute(conn, "SELECT id, org_name, room_type FROM organizations WHERE id=?", (org_id,))
    site = db_fetchone(cur)
    conn.close()
    if not site: return redirect('/')
    return render_template('admin_login.html', site=site)

@app.route('/admin/dashboard')
def admin_dashboard():
    if not admin_required(): return redirect('/')
    conn = get_db()
    cur = db_execute(conn, "SELECT id, org_name, room_type, venue_number, cabin_number FROM organizations WHERE id=?",
                (session['admin_org_id'],))
    site = db_fetchone(cur)
    conn.close()
    if not site:
        session.clear()
        return redirect('/')
    return render_template('admin_dashboard.html', site=site)

@app.route('/superadmin')
def superadmin_page():
    return render_template('super_admin.html')

@app.route('/superadmin/dashboard')
def superadmin_dashboard():
    if not sa_required(): return redirect('/superadmin')
    return render_template('super_admin_dashboard.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# PUBLIC APIs
@app.route('/api/sites', methods=['GET'])
def api_get_sites():
    conn = get_db()
    cur = db_execute(conn, "SELECT id,org_name,room_type,venue_number,cabin_number,admin_user,capacity,open_time,close_time,total_classes FROM organizations ORDER BY org_name")
    sites = db_fetchall(cur)
    conn.close()
    return jsonify(sites)

@app.route('/api/public_venues', methods=['GET'])
def api_public_venues():
    conn = get_db()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = db_execute(conn, """UPDATE public_venues SET status='available',current_booker=NULL,
        booked_org_id=NULL,booked_from=NULL,booked_until=NULL
        WHERE status='occupied' AND booked_until < ?""", (now,))
    conn.commit()
    sf = request.args.get('status','all')
    if sf == 'available':
        cur = db_execute(conn, "SELECT * FROM public_venues WHERE status='available' ORDER BY venue_name")
    elif sf == 'occupied':
        cur = db_execute(conn, "SELECT * FROM public_venues WHERE status='occupied' ORDER BY venue_name")
    else:
        cur = db_execute(conn, "SELECT * FROM public_venues ORDER BY venue_name")
    venues = db_fetchall(cur)
    conn.close()
    result = []
    for v in venues:
        d = dict(v)
        for k in ('booked_from','booked_until','created_at'):
            if d.get(k): d[k] = str(d[k])
        result.append(d)
    return jsonify(result)

@app.route('/api/mark_attendance', methods=['POST'])
def api_mark_attendance():
    if not FACE_RECOGNITION_AVAILABLE:
        return jsonify({"status":"error","message":"Face recognition not installed. Use admin panel to mark attendance."})
    now = datetime.now()
    data = request.json
    org_id = data.get('org_id')
    # Check per-site operating hours
    conn_check = get_db()
    cur_check = conn_check.cursor()
    cur_check.execute("SELECT open_time, close_time FROM organizations WHERE id=?", (org_id,))
    site_row = cur_check.fetchone()
    conn_check.close()
    if site_row:
        s = dict(site_row)
        open_t = s.get('open_time') or '06:00'
        close_t = s.get('close_time') or '22:00'
        current_time = now.strftime('%H:%M')
        if current_time < open_t or current_time >= close_t:
            return jsonify({"status":"error","message":f"Portal closed. Operating hours: {open_t} – {close_t}."})
    try:
        rgb = decode_image(data['image'])
    except Exception:
        return jsonify({"status":"error","message":"Invalid image data."})
    unknown_encodings = face_recognition.face_encodings(rgb)
    if not unknown_encodings:
        return jsonify({"status":"error","message":"Face not recognised - please register first."})
    unknown_enc = unknown_encodings[0]
    conn = get_db()
    cur = db_execute(conn, "SELECT id,name,face_encoding FROM students WHERE org_id=?", (org_id,))
    for student in db_fetchall(cur):
        s = student
        if not s['face_encoding']: continue
        known_enc = np.array(json.loads(s['face_encoding']))
        if face_recognition.compare_faces([known_enc], unknown_enc, tolerance=0.50)[0]:
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H:%M:%S")
            day_str = now.strftime("%A")
            cur = db_execute(conn, "SELECT id FROM attendance WHERE student_id=? AND date=?",(s['id'],date_str))
            if db_fetchone(cur):
                conn.close()
                return jsonify({"status":"warning","message":f"Already Marked Present for today. Thank you, {s['name']}!"})
            cur = db_execute(conn, "INSERT INTO attendance (student_id,date,time) VALUES(?,?,?)",(s['id'],date_str,time_str))
            conn.commit()
            conn.close()
            return jsonify({"status":"success","message":f"Welcome {s['name']}  |  {day_str}  |  {time_str}"})
    conn.close()
    return jsonify({"status":"error","message":"Face not recognised - please register first."})

# ADMIN APIs
@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.json
    conn = get_db()
    cur = db_execute(conn, "SELECT id,org_name FROM organizations WHERE id=? AND admin_password=?",(data['org_id'],data['password']))
    site = db_fetchone(cur)
    if site:
        s = site
        session['admin_org_id'] = s['id']
        session['admin_org_name'] = s['org_name']
        today = datetime.now().strftime("%Y-%m-%d")
        cur = db_execute(conn, "UPDATE organizations SET admin_logged_today=? WHERE id=?",(today,s['id']))
        conn.commit()
        conn.close()
        return jsonify({"status":"success"})
    conn.close()
    return jsonify({"status":"error","message":"Incorrect password."})

@app.route('/api/admin/students', methods=['GET'])
def api_admin_students():
    if not admin_required(): return jsonify({"error":"Unauthorized"}),401
    org_id = session['admin_org_id']
    date = request.args.get('date',datetime.now().strftime("%Y-%m-%d"))
    conn = get_db()
    cur = db_execute(conn, """
        SELECT s.id,s.name,s.roll_number,s.age,s.class_name,
               CASE WHEN a.id IS NOT NULL THEN 1 ELSE 0 END AS is_present,
               (SELECT COUNT(*) FROM attendance WHERE student_id=s.id) AS total_attended,
               (SELECT total_classes FROM organizations WHERE id=s.org_id) AS total_classes
        FROM students s
        LEFT JOIN attendance a ON a.student_id=s.id AND a.date=?
        WHERE s.org_id=? ORDER BY s.name
    """,(date,org_id))
    students = db_fetchall(cur)
    conn.close()
    return jsonify(students)

@app.route('/api/admin/add_student', methods=['POST'])
def api_admin_add_student():
    if not admin_required(): return jsonify({"status":"error","message":"Unauthorized"}),401
    data=request.json; org_id=session['admin_org_id']; password=data.get('password')
    conn=get_db()
    cur = db_execute(conn, "SELECT id FROM organizations WHERE id=? AND admin_password=?",(org_id,password))
    if not db_fetchone(cur):
        conn.close(); return jsonify({"status":"error","message":"Incorrect admin password."})
    enc_json = None
    if FACE_RECOGNITION_AVAILABLE and data.get('image'):
        try:
            rgb=decode_image(data['image'])
            encodings=face_recognition.face_encodings(rgb)
            if not encodings:
                conn.close(); return jsonify({"status":"error","message":"No face detected. Try again."})
            enc_json=json.dumps(encodings[0].tolist())
        except Exception:
            conn.close(); return jsonify({"status":"error","message":"Invalid image data."})
    try:
        cur = db_execute(conn, "INSERT INTO students (org_id,name,roll_number,age,class_name,face_encoding) VALUES(?,?,?,?,?,?)",
                     (org_id,data['name'],data['roll_number'],data.get('age',0),data.get('class_name','N/A'),enc_json))
        conn.commit(); conn.close()
        return jsonify({"status":"success","message":f"{data['name']} added successfully."})
    except Exception as ie:
        ie_str = str(ie).lower()
        if "unique" in ie_str or "duplicate" in ie_str:
            conn.close(); return jsonify({"status":"error","message":"Roll number already exists."})
        conn.close(); return jsonify({"status":"error","message":str(ie)})

@app.route('/api/admin/mark_present', methods=['POST'])
def api_admin_mark_present():
    if not admin_required(): return jsonify({"status":"error"}),401
    data=request.json; org_id=session['admin_org_id']; password=data.get('password')
    conn=get_db()
    cur = db_execute(conn, "SELECT id FROM organizations WHERE id=? AND admin_password=?",(org_id,password))
    if not db_fetchone(cur):
        conn.close(); return jsonify({"status":"error","message":"Incorrect password."})
    student_id=data['student_id']; date_str=data.get('date',datetime.now().strftime("%Y-%m-%d")); time_str=datetime.now().strftime("%H:%M:%S")
    cur = db_execute(conn, "SELECT id FROM attendance WHERE student_id=? AND date=?",(student_id,date_str))
    if db_fetchone(cur):
        conn.close(); return jsonify({"status":"warning","message":"Already marked for this date."})
    cur = db_execute(conn, "INSERT INTO attendance (student_id,date,time) VALUES(?,?,?)",(student_id,date_str,time_str))
    conn.commit(); conn.close()
    return jsonify({"status":"success","message":"Marked present."})

@app.route('/api/admin/edit_student', methods=['POST'])
def api_admin_edit_student():
    if not admin_required(): return jsonify({"status":"error"}),401
    data=request.json; org_id=session['admin_org_id']; password=data.get('password')
    conn=get_db()
    cur = db_execute(conn, "SELECT id FROM organizations WHERE id=? AND admin_password=?",(org_id,password))
    if not db_fetchone(cur):
        conn.close(); return jsonify({"status":"error","message":"Incorrect password."})
    cur = db_execute(conn, "UPDATE students SET name=?,roll_number=?,age=?,class_name=? WHERE id=? AND org_id=?",
                 (data['name'],data['roll_number'],data.get('age',0),data.get('class_name','N/A'),data['student_id'],org_id))
    conn.commit(); conn.close()
    return jsonify({"status":"success","message":"Student updated."})

@app.route('/api/admin/delete_student', methods=['POST'])
def api_admin_delete_student():
    if not admin_required(): return jsonify({"status":"error"}),401
    data=request.json; org_id=session['admin_org_id']; password=data.get('password')
    conn=get_db()
    cur = db_execute(conn, "SELECT id FROM organizations WHERE id=? AND admin_password=?",(org_id,password))
    if not db_fetchone(cur):
        conn.close(); return jsonify({"status":"error","message":"Incorrect password."})
    cur = db_execute(conn, "DELETE FROM students WHERE id=? AND org_id=?",(data['student_id'],org_id))
    conn.commit(); conn.close()
    return jsonify({"status":"success","message":"Student deleted."})

@app.route('/api/admin/absents', methods=['GET'])
def api_admin_absents():
    if not admin_required(): return jsonify({"error":"Unauthorized"}),401
    org_id=session['admin_org_id']; date=request.args.get('date',datetime.now().strftime("%Y-%m-%d"))
    conn=get_db()
    cur = db_execute(conn, "SELECT s.id,s.name,s.roll_number FROM students s WHERE s.org_id=? AND s.id NOT IN (SELECT student_id FROM attendance WHERE date=?) ORDER BY s.name",(org_id,date))
    absents = db_fetchall(cur); conn.close()
    return jsonify(absents)

@app.route('/api/admin/request_venue', methods=['POST'])
def api_admin_request_venue():
    if not admin_required():
        return jsonify({"status":"error","message":"You must be logged in to request a venue."}),401
    data=request.json; org_id=session['admin_org_id']
    conn=get_db()
    cur = db_execute(conn, "SELECT admin_user FROM organizations WHERE id=?",(org_id,))
    org = db_fetchone(cur)
    if not org: conn.close(); return jsonify({"status":"error","message":"Organization not found."})
    o=org; admin_name=o['admin_user'] or f"Admin #{org_id}"
    cur = db_execute(conn, "SELECT id,venue_name FROM public_venues WHERE id=?",(data['venue_id'],))
    venue = db_fetchone(cur)
    if not venue: conn.close(); return jsonify({"status":"error","message":"Venue not found."})
    v=venue
    cur = db_execute(conn, """SELECT id FROM venue_requests WHERE venue_id=? AND booking_date=? AND status='approved'
        AND NOT (end_time<=? OR start_time>=?)""",(data['venue_id'],data['booking_date'],data['start_time'],data['end_time']))
    if db_fetchone(cur):
        conn.close(); return jsonify({"status":"error","message":"This venue already has an approved booking in that time slot."})
    cur = db_execute(conn, "INSERT INTO venue_requests (venue_id,org_id,admin_name,purpose,booking_date,start_time,end_time) VALUES(?,?,?,?,?,?,?)",
                 (data['venue_id'],org_id,admin_name,data.get('purpose',''),data['booking_date'],data['start_time'],data['end_time']))
    conn.commit(); conn.close()
    return jsonify({"status":"success","message":f"Request submitted for {v['venue_name']}. Awaiting Super Admin approval."})

@app.route('/api/admin/my_venue_requests', methods=['GET'])
def api_admin_my_venue_requests():
    if not admin_required(): return jsonify({"error":"Unauthorized"}),401
    org_id=session['admin_org_id']
    conn=get_db()
    cur = db_execute(conn, """SELECT vr.id,vr.purpose,vr.booking_date,vr.start_time,vr.end_time,vr.status,vr.requested_at,
               pv.venue_name,pv.venue_number
        FROM venue_requests vr JOIN public_venues pv ON pv.id=vr.venue_id
        WHERE vr.org_id=? ORDER BY vr.requested_at DESC""",(org_id,))
    rows = db_fetchall(cur); conn.close()
    result=[]
    for r in rows:
        d=r
        for k in ('booking_date','start_time','end_time','requested_at'):
            if d.get(k): d[k]=str(d[k])
        result.append(d)
    return jsonify(result)

# SUPER ADMIN APIs
@app.route('/api/superadmin/login', methods=['POST'])
def api_superadmin_login():
    data=request.json; conn=get_db()
    cur = db_execute(conn, "SELECT id FROM super_admin WHERE username=? AND password=?",(data['username'],data['password']))
    if db_fetchone(cur):
        session['super_admin']=True; conn.close()
        return jsonify({"status":"success"})
    conn.close()
    return jsonify({"status":"error","message":"Invalid credentials."})

@app.route('/api/superadmin/stats', methods=['GET'])
def api_sa_stats():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    today=datetime.now().strftime("%Y-%m-%d")
    conn=get_db()
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM organizations"); sites=db_fetchone(cur)['v']
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM public_venues"); pv=db_fetchone(cur)['v']
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM students"); students=db_fetchone(cur)['v']
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM attendance WHERE date=date('now')"); today_a=db_fetchone(cur)['v']
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM venue_requests WHERE status='pending'"); pending=db_fetchone(cur)['v']
    cur = db_execute(conn, "SELECT COUNT(*) AS v FROM organizations WHERE admin_logged_today=?",(today,)); logged=db_fetchone(cur)['v']
    conn.close()
    return jsonify({"total_sites":sites,"total_public_venues":pv,"total_students":students,
                    "total_today":today_a,"pending_requests":pending,"admins_logged_today":logged})

@app.route('/api/superadmin/sites', methods=['GET'])
def api_sa_sites():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    today=datetime.now().strftime("%Y-%m-%d")
    conn=get_db()
    cur = db_execute(conn, """SELECT o.id,o.org_name,o.room_type,o.venue_number,o.cabin_number,
               o.admin_user,o.admin_password,o.capacity,o.admin_logged_today,o.open_time,o.close_time,o.total_classes,
               (SELECT COUNT(*) FROM students WHERE org_id=o.id) AS student_count
        FROM organizations o ORDER BY o.org_name""")
    sites = db_fetchall(cur); conn.close()
    result=[]
    for s in sites:
        d=s
        d['logged_today']=(str(d['admin_logged_today'])==today) if d['admin_logged_today'] else False
        d['admin_logged_today']=str(d['admin_logged_today']) if d['admin_logged_today'] else None
        result.append(d)
    return jsonify(result)

@app.route('/api/superadmin/add_site', methods=['POST'])
def api_sa_add_site():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    data=request.json
    if not data.get('org_name') or not data.get('admin_pass'):
        return jsonify({"status":"error","message":"Site name and admin password required."})
    conn=get_db()
    try:
        cur = db_execute(conn, "INSERT INTO organizations (org_name,room_type,venue_number,cabin_number,admin_user,admin_password,capacity,open_time,close_time,total_classes) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (data['org_name'],data.get('room_type','Classroom'),data.get('venue_number',''),
                     data.get('cabin_number',''),data.get('admin_user',''),data['admin_pass'],int(data.get('capacity',0)),
                     data.get('open_time','06:00'),data.get('close_time','22:00'),int(data.get('total_classes',30))))
        conn.commit(); conn.close(); return jsonify({"status":"success"})
    except Exception as e:
        conn.close(); return jsonify({"status":"error","message":str(e)})

@app.route('/api/superadmin/edit_site', methods=['POST'])
def api_sa_edit_site():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    data=request.json; conn=get_db()
    new_pass = data.get('admin_pass','')
    tc = int(data.get('total_classes',30))
    if new_pass:
        cur = db_execute(conn, "UPDATE organizations SET org_name=?,room_type=?,venue_number=?,cabin_number=?,admin_user=?,admin_password=?,capacity=?,open_time=?,close_time=?,total_classes=? WHERE id=?",
                    (data['org_name'],data['room_type'],data.get('venue_number',''),data.get('cabin_number',''),
                     data['admin_user'],new_pass,int(data.get('capacity',0)),
                     data.get('open_time','06:00'),data.get('close_time','22:00'),tc,data['site_id']))
    else:
        cur = db_execute(conn, "UPDATE organizations SET org_name=?,room_type=?,venue_number=?,cabin_number=?,admin_user=?,capacity=?,open_time=?,close_time=?,total_classes=? WHERE id=?",
                    (data['org_name'],data['room_type'],data.get('venue_number',''),data.get('cabin_number',''),
                     data['admin_user'],int(data.get('capacity',0)),
                     data.get('open_time','06:00'),data.get('close_time','22:00'),tc,data['site_id']))
    conn.commit(); conn.close(); return jsonify({"status":"success"})

@app.route('/api/superadmin/delete_site/<int:site_id>', methods=['DELETE'])
def api_sa_delete_site(site_id):
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    cur = db_execute(conn, "DELETE FROM organizations WHERE id=?",(site_id,))
    conn.commit(); conn.close(); return jsonify({"status":"success"})

@app.route('/api/superadmin/public_venues', methods=['GET'])
def api_sa_public_venues():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    cur = db_execute(conn, "SELECT * FROM public_venues ORDER BY venue_name")
    venues = db_fetchall(cur); conn.close()
    result=[]
    for v in venues:
        d=dict(v)
        for k in ('booked_from','booked_until','created_at'):
            if d.get(k): d[k]=str(d[k])
        result.append(d)
    return jsonify(result)

@app.route('/api/superadmin/add_public_venue', methods=['POST'])
def api_sa_add_public_venue():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    data=request.json
    if not data.get('venue_name'): return jsonify({"status":"error","message":"Venue name required."})
    conn=get_db()
    try:
        cur = db_execute(conn, "INSERT INTO public_venues (venue_name,venue_type,venue_number,capacity) VALUES(?,?,?,?)",
                    (data['venue_name'],data.get('venue_type','Hall'),data.get('venue_number',''),int(data.get('capacity',0))))
        conn.commit(); conn.close(); return jsonify({"status":"success"})
    except Exception as e:
        conn.close(); return jsonify({"status":"error","message":str(e)})

@app.route('/api/superadmin/edit_public_venue', methods=['POST'])
def api_sa_edit_public_venue():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    data=request.json; conn=get_db()
    cur = db_execute(conn, "UPDATE public_venues SET venue_name=?,venue_type=?,venue_number=?,capacity=? WHERE id=?",
                (data['venue_name'],data['venue_type'],data.get('venue_number',''),int(data.get('capacity',0)),data['venue_id']))
    conn.commit(); conn.close(); return jsonify({"status":"success"})

@app.route('/api/superadmin/delete_public_venue/<int:venue_id>', methods=['DELETE'])
def api_sa_delete_public_venue(venue_id):
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    cur = db_execute(conn, "DELETE FROM public_venues WHERE id=?",(venue_id,))
    conn.commit(); conn.close(); return jsonify({"status":"success"})

@app.route('/api/superadmin/venue_requests', methods=['GET'])
def api_sa_venue_requests():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    sf=request.args.get('status','pending')
    conn=get_db()
    base="""SELECT vr.*,pv.venue_name,pv.venue_number,o.org_name FROM venue_requests vr
            JOIN public_venues pv ON pv.id=vr.venue_id JOIN organizations o ON o.id=vr.org_id """
    if sf=='all': cur = db_execute(conn, base+"ORDER BY vr.requested_at DESC")
    else: cur = db_execute(conn, base+"WHERE vr.status=? ORDER BY vr.requested_at DESC",(sf,))
    rows = db_fetchall(cur); conn.close()
    result=[]
    for r in rows:
        d=r
        for k in ('booking_date','start_time','end_time','requested_at','reviewed_at'):
            if d.get(k): d[k]=str(d[k])
        result.append(d)
    return jsonify(result)

@app.route('/api/superadmin/approve_request/<int:req_id>', methods=['POST'])
def api_sa_approve_request(req_id):
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    cur = db_execute(conn, "SELECT vr.*,pv.venue_name FROM venue_requests vr JOIN public_venues pv ON pv.id=vr.venue_id WHERE vr.id=?",(req_id,))
    req = db_fetchone(cur)
    if not req: conn.close(); return jsonify({"status":"error","message":"Request not found."})
    r=req
    cur = db_execute(conn, "UPDATE venue_requests SET status='approved',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(req_id,))
    booked_from=f"{r['booking_date']} {r['start_time']}"
    booked_until=f"{r['booking_date']} {r['end_time']}"
    cur = db_execute(conn, "UPDATE public_venues SET status='occupied',current_booker=?,booked_org_id=?,booked_from=?,booked_until=? WHERE id=?",
                 (r['admin_name'],r['org_id'],booked_from,booked_until,r['venue_id']))
    conn.commit(); conn.close()
    return jsonify({"status":"success","message":"Request approved and venue assigned."})

@app.route('/api/superadmin/deny_request/<int:req_id>', methods=['POST'])
def api_sa_deny_request(req_id):
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    conn=get_db()
    cur = db_execute(conn, "UPDATE venue_requests SET status='denied',reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(req_id,))
    conn.commit(); conn.close(); return jsonify({"status":"success"})

@app.route('/api/superadmin/admin_overview', methods=['GET'])
def api_sa_admin_overview():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    today=datetime.now().strftime("%Y-%m-%d")
    conn=get_db()
    cur = db_execute(conn, """SELECT o.id,o.org_name,o.room_type,o.admin_user,o.venue_number,o.cabin_number,o.admin_logged_today,
               (SELECT COUNT(*) FROM students WHERE org_id=o.id) AS total_students
        FROM organizations o ORDER BY o.org_name""")
    rows = db_fetchall(cur); conn.close()
    result=[]
    for r in rows:
        d=r
        d['logged_today']=(str(d['admin_logged_today'])==today) if d['admin_logged_today'] else False
        d['admin_logged_today']=str(d['admin_logged_today']) if d['admin_logged_today'] else None
        result.append(d)
    return jsonify(result)

@app.route('/api/superadmin/all_attendance', methods=['GET'])
def api_sa_all_attendance():
    if not sa_required(): return jsonify({"error":"Unauthorized"}),401
    date=request.args.get('date',datetime.now().strftime("%Y-%m-%d"))
    conn=get_db()
    cur = db_execute(conn, """SELECT o.org_name AS site_name,COUNT(DISTINCT s.id) AS total_students,COUNT(DISTINCT a.student_id) AS present_count
        FROM organizations o LEFT JOIN students s ON s.org_id=o.id
        LEFT JOIN attendance a ON a.student_id=s.id AND a.date=?
        GROUP BY o.id,o.org_name ORDER BY o.org_name""",(date,))
    rows = db_fetchall(cur); conn.close()
    return jsonify(rows)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
