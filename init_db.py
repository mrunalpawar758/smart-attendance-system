"""
Smart Attendance System - Database Initializer & Seeder
Creates tables and seeds realistic demo data including courses,
faculty, students, and 20 historical attendance sessions.
"""

import sqlite3
import os
import hashlib
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smart_attendance.db')
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')

def hash_password(password: str) -> str:
    """Standard SHA-256 password hash for authentication."""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def get_db_connection():
    """Returns a SQLite connection with row dict access and foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_database():
    """Reads schema.sql and executes the DDL."""
    print(" [1/3] Applying database schema from schema.sql...")
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema_sql = f.read()

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executescript(schema_sql)
    conn.commit()
    conn.close()
    print(" [1/3] Schema created successfully.")

def seed_historical_attendance():
    """Seeds 20 historical class sessions to demonstrate percentage calculation & defaulter alerts."""
    print(" [2/3] Seeding 20 past class sessions and attendance logs for CS401...")
    conn = get_db_connection()
    cursor = conn.cursor()

    course_id = 1      # CS401: Computer Networks
    teacher_id = 2     # prof_gupta

    # Defined attendance patterns for 20 classes:
    # Aarav: 18/20 = 90%
    # Ananya: 19/20 = 95%
    # Rohan: 13/20 = 65% (Defaulter)
    # Sneha: 16/20 = 80%
    # Vikram: 10/20 = 50% (Defaulter)
    attendance_pattern = {
        4: [1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 1], # Aarav (id 4)
        5: [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1], # Ananya (id 5)
        6: [1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 1, 0, 1, 0, 1, 1, 1], # Rohan (id 6) -> 13
        7: [1, 1, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 0, 1, 1], # Sneha (id 7) -> 16
        8: [0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]  # Vikram (id 8) -> 10
    }

    base_date = datetime.now() - timedelta(days=28)

    # Check if sessions already seeded
    cursor.execute("SELECT COUNT(*) FROM attendance_sessions WHERE course_id = ?", (course_id,))
    if cursor.fetchone()[0] == 0:
        day_counter = 0
        for i in range(20):
            # Skip weekends (Saturday=5, Sunday=6)
            session_date = base_date + timedelta(days=day_counter)
            while session_date.weekday() >= 5:
                day_counter += 1
                session_date = base_date + timedelta(days=day_counter)
            day_counter += 1

            date_str = session_date.strftime('%Y-%m-%d')
            start_str = f"{date_str} 10:00:00"
            end_str = f"{date_str} 11:00:00"

            cursor.execute("""
                INSERT INTO attendance_sessions (course_id, teacher_id, session_date, start_time, end_time, method, is_active)
                VALUES (?, ?, ?, ?, ?, 'MANUAL', 0)
            """, (course_id, teacher_id, date_str, start_str, end_str))
            session_id = cursor.lastrowid

            for student_id, records in attendance_pattern.items():
                is_present = records[i] == 1
                status = 'PRESENT' if is_present else 'ABSENT'
                cursor.execute("""
                    INSERT INTO attendance_logs (session_id, student_id, course_id, status, marked_at, verification_method)
                    VALUES (?, ?, ?, ?, ?, 'MANUAL')
                """, (session_id, student_id, course_id, status, start_str))

        conn.commit()
        print(" [2/3] Successfully seeded 20 sessions and 100 attendance records.")
    else:
        print(" [2/3] Sessions already exist, skipping duplicate seed.")

    conn.close()

def display_summary():
    """Prints a verified summary of database accounts and baseline stats."""
    conn = get_db_connection()
    cursor = conn.cursor()

    print("\n" + "=" * 65)
    print(" SMART ATTENDANCE SYSTEM - DATABASE READY")
    print("=" * 65)
    print(f" Database Path: {DB_PATH}")

    cursor.execute("""
        SELECT u.id, u.username, u.full_name, r.name as role, u.roll_number
        FROM users u JOIN roles r ON u.role_id = r.id
    """)
    users = cursor.fetchall()
    print(f"\n Seeded Users ({len(users)} Total):")
    print(f" {'ID':<3} | {'Username':<14} | {'Role':<8} | {'Roll No':<10} | {'Full Name'}")
    print("-" * 65)
    for u in users:
        roll = u['roll_number'] or 'N/A'
        print(f" {u['id']:<3} | {u['username']:<14} | {u['role']:<8} | {roll:<10} | {u['full_name']}")

    cursor.execute("""
        SELECT 
            u.full_name, 
            u.roll_number,
            COUNT(l.id) as total_classes,
            SUM(CASE WHEN l.status = 'PRESENT' THEN 1 ELSE 0 END) as attended,
            ROUND(100.0 * SUM(CASE WHEN l.status = 'PRESENT' THEN 1 ELSE 0 END) / COUNT(l.id), 1) as percentage
        FROM enrollments e
        JOIN users u ON e.student_id = u.id
        LEFT JOIN attendance_logs l ON l.student_id = u.id AND l.course_id = e.course_id
        WHERE e.course_id = 1
        GROUP BY u.id
    """)
    stats = cursor.fetchall()
    print(f"\n Baseline Statistics for CS401 (Computer Networks):")
    print(f" {'Roll No':<10} | {'Student Name':<16} | {'Attended':<9} | {'Percentage':<10} | {'Defaulter (<75%)'}")
    print("-" * 65)
    for s in stats:
        pct = s['percentage'] or 0.0
        is_defaulter = "YES (ALERT)" if pct < 75.0 else "Satisfactory"
        print(f" {s['roll_number']:<10} | {s['full_name']:<16} | {s['attended']}/{s['total_classes']:<7} | {pct:>5.1f}%     | {is_defaulter}")

    print("=" * 65)
    print(" Default login credentials for all test accounts:")
    print(" Password: password123")
    print("=" * 65 + "\n")
    conn.close()

if __name__ == '__main__':
    init_database()
    seed_historical_attendance()
    display_summary()
