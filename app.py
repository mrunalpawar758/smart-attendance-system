"""
====================================================================
SMART ATTENDANCE SYSTEM - B.Tech Minor Project Backend
Flask Full-Stack Application Engine with RBAC, Dynamic QR & Analytics
====================================================================
"""

import os
import sqlite3
import hashlib
import hmac
import time
import io
import base64
from functools import wraps
from datetime import datetime, date

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, send_file, abort
)
import qrcode

# Import export analytics engine (Module 5)
from export_service import (
    fetch_attendance_analytics,
    generate_excel_report,
    generate_csv_report
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'smart-attendance-super-secret-key-2026')

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smart_attendance.db')
QR_SECRET_KEY = b"dynamic_qr_hmac_secret_key_15s"
QR_VALIDITY_SECONDS = 15  # Token rotation window

# -------------------------------------------------------------------
# Database Helpers
# -------------------------------------------------------------------
def get_db():
    """Returns a SQLite connection with dict-like row access and FK constraints."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def hash_password(password: str) -> str:
    """Computes SHA-256 hash of a plaintext password."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# -------------------------------------------------------------------
# Authentication & Role Decorators
# -------------------------------------------------------------------
def login_required(f):
    """Enforces that a user must be authenticated."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def teacher_required(f):
    """Enforces that the authenticated user has Teacher or Admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        if session.get('role') not in ['teacher', 'admin']:
            flash("Access denied. Faculty privileges required.", "danger")
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    """Enforces that the authenticated user has Student role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for('login'))
        if session.get('role') != 'student':
            flash("Access denied. Student portal only.", "danger")
            return redirect(url_for('teacher_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# -------------------------------------------------------------------
# Core Routes (Module 2)
# -------------------------------------------------------------------
@app.route('/')
def index():
    """Landing route - redirects to appropriate dashboard based on user role."""
    if 'user_id' in session:
        if session.get('role') in ['teacher', 'admin']:
            return redirect(url_for('teacher_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Handles user authentication for Teachers, Students, and Administrators.
    Validates username and SHA-256 hashed password.
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username or not password:
            flash("Both username and password are required.", "danger")
            return render_template('login.html')

        pwd_hash = hash_password(password)
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT u.id, u.username, u.full_name, u.email, u.roll_number,
                   u.password_hash, r.name as role_name
            FROM users u
            JOIN roles r ON u.role_id = r.id
            WHERE u.username = ? AND u.is_active = 1
        """, (username,))
        user = cursor.fetchone()
        conn.close()

        if user and user['password_hash'] == pwd_hash:
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role_name']
            session['roll_number'] = user['roll_number']

            flash(f"Welcome back, {user['full_name']}!", "success")

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)

            if user['role_name'] in ['teacher', 'admin']:
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash("Invalid username or password. Please try again.", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs out current user and clears session."""
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
@teacher_required
def teacher_dashboard():
    """
    Teacher Interface:
    1. Displays list of assigned courses.
    2. Displays enrolled students with calculated attendance percentages.
    3. Highlights low-attendance defaulters (< 75%) with visual alert badges.
    4. Provides interactive toggle switches for daily attendance entry.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Get teacher's courses
    cursor.execute("""
        SELECT id, course_code, course_name, semester, academic_year
        FROM courses
        WHERE teacher_id = ? OR ? = 'admin'
        ORDER BY course_code ASC
    """, (session['user_id'], session['role']))
    courses = cursor.fetchall()

    if not courses:
        conn.close()
        return render_template('dashboard.html', courses=[], selected_course=None, students=[])

    # Select active course (from query param or default to first course)
    selected_course_id = request.args.get('course_id', type=int)
    if not selected_course_id or not any(c['id'] == selected_course_id for c in courses):
        selected_course_id = courses[0]['id']

    # Fetch selected course info
    cursor.execute("SELECT * FROM courses WHERE id = ?", (selected_course_id,))
    selected_course = cursor.fetchone()

    # Calculate total classes conducted for selected course
    cursor.execute("""
        SELECT COUNT(id) as total_sessions
        FROM attendance_sessions
        WHERE course_id = ?
    """, (selected_course_id,))
    total_sessions = cursor.fetchone()['total_sessions']

    # Fetch enrolled students and their attendance statistics
    cursor.execute("""
        SELECT 
            u.id as student_id,
            u.roll_number,
            u.full_name,
            u.email,
            COUNT(l.id) as classes_recorded,
            SUM(CASE WHEN l.status = 'PRESENT' THEN 1 ELSE 0 END) as attended_count
        FROM enrollments e
        JOIN users u ON e.student_id = u.id
        LEFT JOIN attendance_logs l ON l.student_id = u.id AND l.course_id = e.course_id
        WHERE e.course_id = ?
        GROUP BY u.id
        ORDER BY u.roll_number ASC
    """, (selected_course_id,))
    raw_students = cursor.fetchall()

    students = []
    defaulters_count = 0
    total_pct_sum = 0

    for s in raw_students:
        attended = s['attended_count'] or 0
        percentage = round((attended / total_sessions * 100.0), 1) if total_sessions > 0 else 100.0
        is_defaulter = percentage < 75.0

        if is_defaulter:
            defaulters_count += 1
        total_pct_sum += percentage

        students.append({
            'id': s['student_id'],
            'roll_number': s['roll_number'],
            'full_name': s['full_name'],
            'email': s['email'],
            'attended': attended,
            'total_sessions': total_sessions,
            'percentage': percentage,
            'is_defaulter': is_defaulter
        })

    avg_attendance = round(total_pct_sum / len(students), 1) if students else 0.0

    # Check if a session has already been recorded for today
    today_str = date.today().strftime('%Y-%m-%d')
    cursor.execute("""
        SELECT id, is_active FROM attendance_sessions
        WHERE course_id = ? AND session_date = ?
        ORDER BY id DESC LIMIT 1
    """, (selected_course_id, today_str))
    today_session = cursor.fetchone()

    # Fetch today's marked status if already taken
    today_status_map = {}
    if today_session:
        cursor.execute("""
            SELECT student_id, status FROM attendance_logs
            WHERE session_id = ?
        """, (today_session['id'],))
        for row in cursor.fetchall():
            today_status_map[row['student_id']] = row['status']

    conn.close()

    return render_template(
        'dashboard.html',
        courses=courses,
        selected_course=selected_course,
        students=students,
        total_sessions=total_sessions,
        defaulters_count=defaulters_count,
        avg_attendance=avg_attendance,
        today_session=today_session,
        today_status_map=today_status_map,
        today_date=today_str
    )

@app.route('/attendance/submit', methods=['POST'])
@teacher_required
def submit_attendance():
    """
    Submits daily attendance from the Teacher Dashboard toggle switches.
    Creates an attendance_session and commits individual student logs.
    """
    course_id = request.form.get('course_id', type=int)
    session_date = request.form.get('session_date', date.today().strftime('%Y-%m-%d'))
    student_ids = request.form.getlist('student_ids', type=int)

    if not course_id:
        flash("Invalid course specified.", "danger")
        return redirect(url_for('teacher_dashboard'))

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Check if session exists for this date or create new
        cursor.execute("""
            SELECT id FROM attendance_sessions
            WHERE course_id = ? AND session_date = ?
        """, (course_id, session_date))
        session_row = cursor.fetchone()

        if session_row:
            session_id = session_row['id']
        else:
            cursor.execute("""
                INSERT INTO attendance_sessions (course_id, teacher_id, session_date, method, is_active)
                VALUES (?, ?, ?, 'MANUAL', 0)
            """, (course_id, session['user_id'], session_date))
            session_id = cursor.lastrowid

        # Insert or update each student's attendance log
        present_count = 0
        for s_id in student_ids:
            # Form field: 'status_<student_id>' == 'PRESENT' when toggle switch is on
            toggle_val = request.form.get(f'status_{s_id}')
            status = 'PRESENT' if toggle_val == 'PRESENT' else 'ABSENT'
            if status == 'PRESENT':
                present_count += 1

            cursor.execute("""
                INSERT INTO attendance_logs (session_id, student_id, course_id, status, marked_at, verification_method)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'MANUAL')
                ON CONFLICT(session_id, student_id) DO UPDATE SET
                    status = excluded.status,
                    marked_at = CURRENT_TIMESTAMP,
                    verification_method = 'MANUAL'
            """, (session_id, s_id, course_id, status))

        conn.commit()
        flash(f"Attendance recorded for {session_date}: {present_count} Present, {len(student_ids) - present_count} Absent.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error recording attendance: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('teacher_dashboard', course_id=course_id))

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    """
    Student View:
    Displays enrolled subjects, total classes held, individual attendance %,
    defaulter status alert (< 75%), and historical session log.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Query all enrolled courses with teacher info and attendance calculations
    cursor.execute("""
        SELECT 
            c.id as course_id,
            c.course_code,
            c.course_name,
            u_teach.full_name as teacher_name,
            (SELECT COUNT(id) FROM attendance_sessions WHERE course_id = c.id) as total_sessions,
            COUNT(l.id) as classes_logged,
            SUM(CASE WHEN l.status = 'PRESENT' THEN 1 ELSE 0 END) as attended_count
        FROM enrollments e
        JOIN courses c ON e.course_id = c.id
        JOIN users u_teach ON c.teacher_id = u_teach.id
        LEFT JOIN attendance_logs l ON l.student_id = e.student_id AND l.course_id = c.id
        WHERE e.student_id = ?
        GROUP BY c.id
        ORDER BY c.course_code ASC
    """, (session['user_id'],))
    enrolled_courses = cursor.fetchall()

    courses_data = []
    overall_attended = 0
    overall_total = 0

    for c in enrolled_courses:
        tot = c['total_sessions'] or 0
        att = c['attended_count'] or 0
        pct = round((att / tot * 100.0), 1) if tot > 0 else 100.0

        overall_attended += att
        overall_total += tot

        courses_data.append({
            'course_id': c['course_id'],
            'course_code': c['course_code'],
            'course_name': c['course_name'],
            'teacher_name': c['teacher_name'],
            'total_sessions': tot,
            'attended_count': att,
            'percentage': pct,
            'is_defaulter': pct < 75.0
        })

    overall_pct = round((overall_attended / overall_total * 100.0), 1) if overall_total > 0 else 100.0

    # Recent attendance logs for this student
    cursor.execute("""
        SELECT 
            c.course_code,
            c.course_name,
            s.session_date,
            l.status,
            l.verification_method,
            l.marked_at
        FROM attendance_logs l
        JOIN attendance_sessions s ON l.session_id = s.id
        JOIN courses c ON l.course_id = c.id
        WHERE l.student_id = ?
        ORDER BY s.session_date DESC, l.marked_at DESC
        LIMIT 15
    """, (session['user_id'],))
    recent_logs = cursor.fetchall()

    conn.close()

    return render_template(
        'student_dashboard.html',
        courses=courses_data,
        overall_pct=overall_pct,
        overall_attended=overall_attended,
        overall_total=overall_total,
        is_overall_defaulter=overall_pct < 75.0,
        recent_logs=recent_logs
    )

# -------------------------------------------------------------------
# Dynamic QR Code Verification (Module 3)
# -------------------------------------------------------------------
def generate_dynamic_token(session_id: int, timestamp: int) -> str:
    """Generates an HMAC-SHA256 signature for a (session_id, timestamp_window)."""
    # Group into 15-second epoch windows
    window = timestamp // QR_VALIDITY_SECONDS
    message = f"{session_id}:{window}".encode('utf-8')
    sig = hmac.new(QR_SECRET_KEY, message, hashlib.sha256).hexdigest()[:16]
    return f"{window}-{sig}"

def verify_dynamic_token(session_id: int, token: str) -> bool:
    """
    Validates a submitted QR token against the current 15s window
    (and allows 1 window grace period for network latency).
    """
    try:
        token_window_str, _ = token.split('-', 1)
        token_window = int(token_window_str)
    except Exception:
        return False

    current_window = int(time.time()) // QR_VALIDITY_SECONDS

    # Allow current window and previous window (grace period)
    if token_window not in [current_window, current_window - 1]:
        return False

    expected_sig = hmac.new(
        QR_SECRET_KEY,
        f"{session_id}:{token_window}".encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:16]

    return token == f"{token_window}-{expected_sig}"

@app.route('/qr/display/<int:course_id>')
@teacher_required
def qr_display(course_id: int):
    """
    Teacher Projector View:
    Displays dynamic QR code that refreshes every 15 seconds.
    Students scan from their mobile devices to mark attendance.
    """
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM courses WHERE id = ?", (course_id,))
    course = cursor.fetchone()
    if not course:
        conn.close()
        flash("Course not found.", "danger")
        return redirect(url_for('teacher_dashboard'))

    today_str = date.today().strftime('%Y-%m-%d')

    # Get or create today's dynamic QR session
    cursor.execute("""
        SELECT * FROM attendance_sessions
        WHERE course_id = ? AND session_date = ? AND method = 'DYNAMIC_QR' AND is_active = 1
        ORDER BY id DESC LIMIT 1
    """, (course_id, today_str))
    active_session = cursor.fetchone()

    if not active_session:
        cursor.execute("""
            INSERT INTO attendance_sessions (course_id, teacher_id, session_date, method, is_active)
            VALUES (?, ?, ?, 'DYNAMIC_QR', 1)
        """, (course_id, session['user_id'], today_str))
        conn.commit()
        session_id = cursor.lastrowid
    else:
        session_id = active_session['id']

    conn.close()

    return render_template('qr_display.html', course=course, session_id=session_id)

@app.route('/api/qr/token/<int:session_id>')
@teacher_required
def api_qr_token(session_id: int):
    """
    API called by teacher screen every 15 seconds to fetch the updated QR code.
    Generates a QR code image as Base64 data URI containing the verification link.
    """
    now = int(time.time())
    token = generate_dynamic_token(session_id, now)
    seconds_remaining = QR_VALIDITY_SECONDS - (now % QR_VALIDITY_SECONDS)

    # Verification URL that student scans:
    # Uses request.host_url so it automatically points to current local server / LAN IP
    verify_url = f"{request.host_url.rstrip('/')}/attendance/verify-qr?session_id={session_id}&token={token}"

    # Generate QR Code image with qrcode library
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E3A8A", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')

    return jsonify({
        'session_id': session_id,
        'token': token,
        'verify_url': verify_url,
        'qr_base64': f"data:image/png;base64,{qr_b64}",
        'seconds_remaining': seconds_remaining,
        'timestamp': now
    })

@app.route('/api/qr/attendees/<int:session_id>')
@teacher_required
def api_qr_attendees(session_id: int):
    """Teacher screen polls this to display live attendees as students scan."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.full_name, u.roll_number, l.marked_at
        FROM attendance_logs l
        JOIN users u ON l.student_id = u.id
        WHERE l.session_id = ?
        ORDER BY l.marked_at DESC
    """, (session_id,))
    attendees = cursor.fetchall()
    conn.close()

    return jsonify({
        'count': len(attendees),
        'attendees': [dict(a) for a in attendees]
    })

@app.route('/attendance/verify-qr', methods=['GET', 'POST'])
def verify_qr():
    """
    Student QR Verification Endpoint:
    Invoked when student scans the QR or clicks the link on mobile.
    Enforces:
    1. Student logged in
    2. Student enrolled in the course
    3. Token freshness within 15-second window
    4. Anti-proxy / single attendance per session constraint
    """
    session_id = request.args.get('session_id', type=int) or request.form.get('session_id', type=int)
    token = request.args.get('token', '').strip() or request.form.get('token', '').strip()

    if 'user_id' not in session:
        flash("Please log in to your student account to record attendance.", "warning")
        return redirect(url_for('login', next=request.full_path))

    if session.get('role') != 'student':
        flash("Only enrolled students can verify attendance via QR code.", "danger")
        return redirect(url_for('index'))

    student_id = session['user_id']

    if not session_id or not token:
        flash("Invalid QR code link or missing verification token.", "danger")
        return redirect(url_for('student_dashboard'))

    # 1. Validate Token Cryptographic Signature & Expiry
    if not verify_dynamic_token(session_id, token):
        flash("QR Code expired! Dynamic tokens rotate every 15 seconds. Please scan the current code on screen.", "danger")
        return redirect(url_for('student_dashboard'))

    conn = get_db()
    cursor = conn.cursor()

    # 2. Check Session Validity
    cursor.execute("""
        SELECT s.id, s.course_id, s.is_active, c.course_name, c.course_code
        FROM attendance_sessions s
        JOIN courses c ON s.course_id = c.id
        WHERE s.id = ?
    """, (session_id,))
    sess_row = cursor.fetchone()

    if not sess_row or sess_row['is_active'] == 0:
        conn.close()
        flash("This attendance session is no longer active.", "danger")
        return redirect(url_for('student_dashboard'))

    course_id = sess_row['course_id']

    # 3. Check Student Enrollment
    cursor.execute("""
        SELECT id FROM enrollments
        WHERE student_id = ? AND course_id = ?
    """, (student_id, course_id))
    if not cursor.fetchone():
        conn.close()
        flash(f"You are not enrolled in {sess_row['course_code']} - {sess_row['course_name']}.", "danger")
        return redirect(url_for('student_dashboard'))

    # 4. Check if already marked for this session (Anti-Proxy)
    cursor.execute("""
        SELECT id, marked_at FROM attendance_logs
        WHERE session_id = ? AND student_id = ?
    """, (session_id, student_id))
    existing_log = cursor.fetchone()

    if existing_log:
        conn.close()
        flash(f"Attendance already marked for this session at {existing_log['marked_at']}.", "info")
        return redirect(url_for('student_dashboard'))

    # 5. Record Verified Attendance
    client_ip = request.remote_addr or '127.0.0.1'
    try:
        cursor.execute("""
            INSERT INTO attendance_logs (session_id, student_id, course_id, status, marked_at, verification_method, ip_address)
            VALUES (?, ?, ?, 'PRESENT', CURRENT_TIMESTAMP, 'DYNAMIC_QR', ?)
        """, (session_id, student_id, course_id, client_ip))
        conn.commit()
        flash(f"Success! Attendance verified & recorded for {sess_row['course_code']} via Dynamic QR.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error marking attendance: {str(e)}", "danger")
    finally:
        conn.close()

    return redirect(url_for('student_dashboard'))

# -------------------------------------------------------------------
# Report Generation & Analytics (Module 5)
# -------------------------------------------------------------------
@app.route('/reports/<int:course_id>')
@teacher_required
def reports_view(course_id: int):
    """Interactive analytics and report preview page."""
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    try:
        analytics = fetch_attendance_analytics(course_id, start_date or None, end_date or None)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for('teacher_dashboard'))

    # Calculate overall stats for summary cards
    records = analytics['records']
    total_students = len(records)
    defaulters = [r for r in records if r['Is Defaulter']]
    avg_pct = round(sum(r['Attendance %'] for r in records) / total_students, 1) if total_students > 0 else 0.0

    return render_template(
        'reports.html',
        course=analytics['course'],
        records=records,
        total_classes=analytics['total_classes'],
        total_students=total_students,
        defaulters_count=len(defaulters),
        avg_percentage=avg_pct,
        start_date=start_date,
        end_date=end_date
    )

@app.route('/reports/export/<format_type>/<int:course_id>')
@teacher_required
def export_report(format_type: str, course_id: int):
    """
    Downloads attendance report as either .xlsx (with color highlighting) or .csv.
    """
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')

    try:
        analytics = fetch_attendance_analytics(course_id, start_date or None, end_date or None)
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for('teacher_dashboard'))

    course_code = analytics['course']['course_code']
    date_stamp = datetime.now().strftime('%Y%m%d')

    if format_type == 'excel':
        excel_buffer = generate_excel_report(analytics)
        filename = f"Attendance_Report_{course_code}_{date_stamp}.xlsx"
        return send_file(
            excel_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    elif format_type == 'csv':
        csv_data = generate_csv_report(analytics)
        filename = f"Attendance_Report_{course_code}_{date_stamp}.csv"
        return send_file(
            io.BytesIO(csv_data.encode('utf-8')),
            as_attachment=True,
            download_name=filename,
            mimetype='text/csv'
        )
    else:
        abort(400, "Invalid export format. Choose 'excel' or 'csv'.")

# -------------------------------------------------------------------
# Application Entry Point
# -------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 65)
    print(" SMART ATTENDANCE SYSTEM - FLASK SERVER")
    print(" Teacher Login: prof_gupta / password123")
    print(" Student Login: aarav_sharma / password123")
    print("=" * 65)
    app.run(host='0.0.0.0', port=5000, debug=True)
