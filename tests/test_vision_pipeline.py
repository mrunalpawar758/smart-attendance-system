"""
Smart Attendance System - Vision Pipeline Unit Test
Tests dataset parsing, student metadata mapping, and session cooldown database logging.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from face_recognition_module import (
    load_student_encodings,
    get_or_create_face_session,
    log_attendance_entry,
    get_student_metadata_by_roll,
    DATASET_DIR
)
from app import get_db

class VisionPipelineTestCase(unittest.TestCase):

    def test_01_student_dataset_directory(self):
        """Test that dataset/students exists and contains reference portrait files."""
        self.assertTrue(os.path.exists(DATASET_DIR), "dataset/students directory must exist.")
        images = [f for f in os.listdir(DATASET_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        self.assertGreaterEqual(len(images), 3, "Should have at least 3 reference portraits.")

    def test_02_student_metadata_lookup(self):
        """Test roll number resolution to database student record."""
        user = get_student_metadata_by_roll('CS2026_01')
        self.assertIsNotNone(user, "User with roll CS2026_01 must exist in database.")
        self.assertEqual(user['full_name'], 'Aarav Sharma')

    def test_03_session_creation_and_cooldown_logging(self):
        """Test automated session creation and duplicate entry prevention (cooldown)."""
        course_id = 1
        student_id = 4 # Aarav Sharma
        student_name = "Aarav Sharma"

        session_id = get_or_create_face_session(course_id)
        self.assertIsInstance(session_id, int)
        self.assertGreater(session_id, 0)

        # Clear any prior log for this specific test run in this session to test fresh insert
        conn = get_db()
        conn.execute("DELETE FROM attendance_logs WHERE session_id = ? AND student_id = ?", (session_id, student_id))
        conn.commit()
        conn.close()

        # First recognition event -> Successfully recorded
        first_attempt = log_attendance_entry(session_id, student_id, course_id, student_name)
        self.assertTrue(first_attempt, "First face detection must log attendance successfully.")

        # Second recognition event within same session -> Prevent duplicate logging
        second_attempt = log_attendance_entry(session_id, student_id, course_id, student_name)
        self.assertFalse(second_attempt, "Second face detection must be blocked by cooldown/uniqueness.")

        # Verify entry in database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT verification_method, status FROM attendance_logs WHERE session_id = ? AND student_id = ?", (session_id, student_id))
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row['verification_method'], 'FACE_RECOGNITION')
        self.assertEqual(row['status'], 'PRESENT')
        conn.close()

if __name__ == '__main__':
    unittest.main()
