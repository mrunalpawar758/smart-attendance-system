"""
Smart Attendance System - Automated Verification Test Suite
Tests authentication, calculation logic, dynamic QR validity, and export reports.
"""

import os
import sys
import unittest
import time
import io
import openpyxl

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, get_db, hash_password, generate_dynamic_token, verify_dynamic_token, QR_VALIDITY_SECONDS
from export_service import fetch_attendance_analytics, generate_csv_report, generate_excel_report

class SmartAttendanceTestCase(unittest.TestCase):

    def setUp(self):
        """Set up Flask test client and ensure test database connection."""
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_01_password_hashing(self):
        """Test SHA-256 password hash consistency."""
        raw = "password123"
        hashed = hash_password(raw)
        # Expected SHA-256 of 'password123'
        expected = "ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f"
        self.assertEqual(hashed, expected, "Password hash must match SHA-256 standard.")

    def test_02_database_integrity(self):
        """Test that all relational tables exist and sample data is populated."""
        conn = get_db()
        cursor = conn.cursor()

        tables = ['roles', 'users', 'courses', 'enrollments', 'attendance_sessions', 'attendance_logs']
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            self.assertGreater(count, 0, f"Table '{table}' should have seeded records.")

        conn.close()

    def test_03_percentage_and_defaulter_calculation(self):
        """Test aggregate calculation and flagging of defaulters (< 75%)."""
        analytics = fetch_attendance_analytics(course_id=1)
        records = analytics['records']

        self.assertGreater(len(records), 0, "Should have enrolled student records.")
        self.assertGreaterEqual(analytics['total_classes'], 20, "Should have at least 20 class sessions.")

        # Verify specific student attendance patterns
        student_map = {r['Roll Number']: r for r in records}

        # Aarav Sharma: High attendance -> Satisfactory
        aarav = student_map.get('CS2026_01')
        self.assertIsNotNone(aarav)
        self.assertGreaterEqual(aarav['Attended'], 18)
        self.assertGreaterEqual(aarav['Attendance %'], 80.0)
        self.assertFalse(aarav['Is Defaulter'])

        # Rohan Mehta: Low attendance -> Defaulter (< 75%)
        rohan = student_map.get('CS2026_03')
        self.assertIsNotNone(rohan)
        self.assertLess(rohan['Attendance %'], 75.0)
        self.assertTrue(rohan['Is Defaulter'], "Student below 75% must be marked as Defaulter.")

        # Vikram Singh: Low attendance -> Defaulter (< 75%)
        vikram = student_map.get('CS2026_05')
        self.assertIsNotNone(vikram)
        self.assertLess(vikram['Attendance %'], 75.0)
        self.assertTrue(vikram['Is Defaulter'], "Student below 75% must be marked as Defaulter.")

    def test_04_dynamic_qr_token_rotation_and_expiry(self):
        """Test HMAC 15-second token validity window and expiration."""
        session_id = 999
        now = int(time.time())

        # 1. Generate current token
        valid_token = generate_dynamic_token(session_id, now)
        self.assertTrue(verify_dynamic_token(session_id, valid_token), "Freshly generated token must be valid.")

        # 2. Token from 60 seconds ago (outside 15-second grace period)
        expired_token = generate_dynamic_token(session_id, now - 60)
        self.assertFalse(verify_dynamic_token(session_id, expired_token), "Token from 60s ago must be rejected as expired.")

        # 3. Tampered token signature
        tampered_token = valid_token[:-4] + "ffff"
        self.assertFalse(verify_dynamic_token(session_id, tampered_token), "Tampered signature must be rejected.")

    def test_05_report_export_generators(self):
        """Test CSV and styled Excel generation."""
        analytics = fetch_attendance_analytics(course_id=1)

        # CSV Export Test
        csv_output = generate_csv_report(analytics)
        self.assertIn("Roll Number,Student Name", csv_output)
        self.assertIn("CS2026_01", csv_output)
        self.assertIn("Defaulter (< 75%)", csv_output)

        # Excel Export Test
        excel_buffer = generate_excel_report(analytics)
        self.assertIsInstance(excel_buffer, io.BytesIO)
        self.assertGreater(excel_buffer.getbuffer().nbytes, 1000, "Excel buffer must contain valid binary data.")

        # Verify Excel workbook structure with openpyxl
        excel_buffer.seek(0)
        wb = openpyxl.load_workbook(excel_buffer)
        sheet = wb['Attendance Summary']
        self.assertIn("SMART ATTENDANCE REPORT", sheet['A1'].value)

    def test_06_flask_routes_and_auth(self):
        """Test Flask HTTP endpoints for login and protected dashboards."""
        # 1. Unauthenticated access to dashboard should redirect to login
        res = self.client.get('/dashboard')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/login', res.headers['Location'])

        # 2. Successful Teacher Login
        res_login = self.client.post('/login', data={
            'username': 'prof_gupta',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(res_login.status_code, 200)
        self.assertIn(b"Faculty Attendance Dashboard", res_login.data)
        self.assertIn(b"Computer Networks", res_login.data)

        # 3. Dynamic QR API Token Endpoint
        res_api = self.client.get('/api/qr/token/1')
        self.assertEqual(res_api.status_code, 200)
        json_data = res_api.get_json()
        self.assertIn('token', json_data)
        self.assertIn('qr_base64', json_data)
        self.assertTrue(json_data['qr_base64'].startswith('data:image/png;base64,'))

if __name__ == '__main__':
    unittest.main()
