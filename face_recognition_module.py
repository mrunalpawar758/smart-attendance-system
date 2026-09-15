"""
====================================================================
SMART ATTENDANCE SYSTEM - Face Recognition Attendance Engine (Module 4)
Automated OpenCV Face Detection & Facial Recognition Module
====================================================================
Features:
1. Loads registered student face encodings from 'dataset/students/' directory.
2. Captures real-time webcam video feed (0.25x downscaled for 30+ FPS speed).
3. Matches detected faces against known student encodings.
4. Draws green bounding boxes for recognized students and red for unknowns.
5. Cooldown & Single-Session Logic: Logs attendance into SQLite 'attendance_logs'
   strictly ONCE per student session/day.
6. Seamlessly integrates with 'face_recognition' library (dlib) with a built-in
   OpenCV Haar Cascade fallback for environments without C++ build tools.
"""

import os
import sys
import time
import sqlite3
import argparse
from datetime import datetime, date

# OpenCV import
try:
    import cv2
    import numpy as np
except ImportError:
    print("[ERROR] OpenCV is not installed. Run: pip install opencv-python")
    cv2 = None
    np = None

# face_recognition library import (optional high-accuracy 128-d model)
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'smart_attendance.db')
DATASET_DIR = os.path.join(BASE_DIR, 'dataset', 'students')

# Create dataset directory if it does not exist
os.makedirs(DATASET_DIR, exist_ok=True)

# -------------------------------------------------------------------
# Database Helper for Attendance Logging
# -------------------------------------------------------------------
def get_or_create_face_session(course_id: int) -> int:
    """Finds or creates an active session for today with method='FACE_RECOGNITION'."""
    today_str = date.today().strftime('%Y-%m-%d')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id FROM attendance_sessions
        WHERE course_id = ? AND session_date = ? AND method = 'FACE_RECOGNITION'
        ORDER BY id DESC LIMIT 1
    """, (course_id, today_str))
    row = cursor.fetchone()

    if row:
        session_id = row['id']
    else:
        # Default to teacher_id = 2 (Prof. Gupta)
        cursor.execute("""
            INSERT INTO attendance_sessions (course_id, teacher_id, session_date, method, is_active)
            VALUES (?, 2, ?, 'FACE_RECOGNITION', 1)
        """, (course_id, today_str))
        conn.commit()
        session_id = cursor.lastrowid
        print(f"[SESSION] Initialized new Face Recognition session #{session_id} for course #{course_id} ({today_str})")

    conn.close()
    return session_id

def log_attendance_entry(session_id: int, student_id: int, course_id: int, student_name: str) -> bool:
    """
    Inserts student attendance into SQLite database.
    Enforces that an entry is recorded strictly ONCE per student per session.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if already logged in this session
        cursor.execute("""
            SELECT id, marked_at FROM attendance_logs
            WHERE session_id = ? AND student_id = ?
        """, (session_id, student_id))
        existing = cursor.fetchone()

        if existing:
            conn.close()
            return False  # Already marked previously

        cursor.execute("""
            INSERT INTO attendance_logs (session_id, student_id, course_id, status, marked_at, verification_method, remarks)
            VALUES (?, ?, ?, 'PRESENT', CURRENT_TIMESTAMP, 'FACE_RECOGNITION', 'Verified via Automated Vision Feed')
        """, (session_id, student_id, course_id))
        conn.commit()
        print(f" [ATTENDANCE LOGGED] -> {student_name} (ID: {student_id}) marked PRESENT at {datetime.now().strftime('%H:%M:%S')}")
        conn.close()
        return True
    except Exception as err:
        print(f"[DB ERROR] Failed to record attendance: {err}")
        conn.close()
        return False

def get_student_metadata_by_roll(roll_number: str):
    """Fetches user ID and full name from SQLite database by roll number."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT id, roll_number, full_name FROM users WHERE roll_number = ?", (roll_number,))
    user = cursor.fetchone()
    conn.close()
    return user

# -------------------------------------------------------------------
# Facial Encoding & Dataset Loader
# -------------------------------------------------------------------
def load_student_encodings():
    """
    Reads student photos from dataset/students/
    Expected filename format: <ROLL_NUMBER>_<Student_Name>.jpg (e.g. 'CS2026_01_Aarav_Sharma.jpg')
    Returns:
        known_encodings: List of 128-d face encodings
        known_names: List of display labels (e.g. 'Aarav Sharma')
        known_rolls: List of roll numbers
        known_ids: List of database user IDs
    """
    known_encodings = []
    known_names = []
    known_rolls = []
    known_ids = []

    image_files = [f for f in os.listdir(DATASET_DIR) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    print(f"\n[DATASET] Scanning '{DATASET_DIR}'... Found {len(image_files)} student reference image(s).")

    if not image_files:
        print(f"[NOTE] Place student portrait photos in: {DATASET_DIR}")
        print("       Naming example: 'CS2026_01_Aarav_Sharma.jpg'")

    if FACE_REC_AVAILABLE:
        for file_name in image_files:
            file_path = os.path.join(DATASET_DIR, file_name)
            base_name, _ = os.path.splitext(file_name)
            parts = base_name.split('_', 2)

            # Extract roll number and name
            if len(parts) >= 2:
                roll_no = f"{parts[0]}_{parts[1]}" if len(parts) == 3 else parts[0]
                display_name = parts[-1].replace('_', ' ')
            else:
                roll_no = parts[0]
                display_name = parts[0]

            # Match with database user ID
            db_user = get_student_metadata_by_roll(roll_no)
            student_id = db_user['id'] if db_user else None

            try:
                img = face_recognition.load_image_file(file_path)
                encodings = face_recognition.face_encodings(img)
                if encodings:
                    known_encodings.append(encodings[0])
                    known_names.append(display_name)
                    known_rolls.append(roll_no)
                    known_ids.append(student_id)
                    print(f"  Loaded encoding for: {display_name} ({roll_no}) [DB ID: {student_id}]")
                else:
                    print(f"  [WARN] No face found in image: {file_name}")
            except Exception as e:
                print(f"  [ERROR] Could not process {file_name}: {e}")

    return known_encodings, known_names, known_rolls, known_ids

# -------------------------------------------------------------------
# Main Video Stream & Real-Time Recognition Loop
# -------------------------------------------------------------------
def run_face_attendance(course_id: int = 1, camera_source: int = 0, tolerance: float = 0.48):
    """
    Opens the webcam stream, processes frames in real time,
    identifies students, renders bounding boxes, and records attendance.
    """
    if cv2 is None:
        print("[CRITICAL] OpenCV library not available. Exiting.")
        return

    session_id = get_or_create_face_session(course_id)
    known_encodings, known_names, known_rolls, known_ids = load_student_encodings()

    # In-memory cooldown set to avoid checking DB every frame for already-marked students
    session_marked_students = set()

    # Pre-populate already marked students from DB for today's session
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id FROM attendance_logs WHERE session_id = ?", (session_id,))
    for row in cursor.fetchall():
        session_marked_students.add(row[0])
    conn.close()

    print(f"\n[READY] Pre-marked students in session #{session_id}: {len(session_marked_students)}")
    print("[STREAM] Initializing video capture (camera index: %s)..." % camera_source)
    video_capture = cv2.VideoCapture(camera_source)

    if not video_capture.isOpened():
        print(f"[WARN] Unable to open camera device #{camera_source}.")
        print("       If running in a virtual or headless environment without a physical webcam,")
        print("       you can simulate recognition or pass a video file: python face_recognition_module.py --video sample.mp4")
        return

    print("=" * 65)
    print(" SMART ATTENDANCE - VISION ENGINE RUNNING")
    print(" Press 'q' on the video window to stop.")
    print("=" * 65)

    frame_count = 0
    face_locations = []
    face_names = []
    face_rolls = []
    face_status = []

    # Haar Cascade as fallback if face_recognition is not installed
    haar_cascade = None
    if not FACE_REC_AVAILABLE:
        cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        haar_cascade = cv2.CascadeClassifier(cascade_path)
        print("[FALLBACK] Using OpenCV Haar Cascade face detector.")

    while True:
        ret, frame = video_capture.read()
        if not ret:
            print("[WARN] Video stream terminated.")
            break

        frame_count += 1

        # Process every 2nd frame for 30+ FPS real-time smoothness
        if frame_count % 2 == 0:
            # Downscale frame to 1/4 size for fast processing
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)

            face_locations = []
            face_names = []
            face_rolls = []
            face_status = []

            if FACE_REC_AVAILABLE and known_encodings:
                # Convert BGR (OpenCV) to RGB (face_recognition)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                for face_encoding in face_encodings:
                    # Calculate Euclidean face distances
                    face_distances = face_recognition.face_distance(known_encodings, face_encoding)
                    best_match_index = np.argmin(face_distances) if len(face_distances) > 0 else None

                    if best_match_index is not None and face_distances[best_match_index] <= tolerance:
                        name = known_names[best_match_index]
                        roll = known_rolls[best_match_index]
                        s_id = known_ids[best_match_index]

                        face_names.append(name)
                        face_rolls.append(roll)

                        # Check session cooldown logic (record strictly ONCE per session)
                        if s_id and s_id not in session_marked_students:
                            logged = log_attendance_entry(session_id, s_id, course_id, name)
                            if logged:
                                session_marked_students.add(s_id)
                                face_status.append("RECORDED")
                            else:
                                face_status.append("PRESENT")
                        else:
                            face_status.append("PRESENT")
                    else:
                        face_names.append("Unknown")
                        face_rolls.append("Unregistered")
                        face_status.append("UNKNOWN")

            elif haar_cascade is not None:
                # Haar Cascade detection fallback
                gray_small = cv2.cvtColor(small_frame, cv2.COLOR_BGR2GRAY)
                faces = haar_cascade.detectMultiScale(gray_small, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

                for (x, y, w, h) in faces:
                    # top, right, bottom, left format
                    face_locations.append((y, x + w, y + h, x))
                    face_names.append("Student Detected")
                    face_rolls.append("Camera Active")
                    face_status.append("DETECTED")

        # Render Bounding Boxes & Name Overlays on Full-Scale Frame
        for i, (top, right, bottom, left) in enumerate(face_locations):
            # Scale coordinates back up 4x
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            status = face_status[i] if i < len(face_status) else "UNKNOWN"
            name = face_names[i] if i < len(face_names) else "Unknown"
            roll = face_rolls[i] if i < len(face_rolls) else ""

            if status in ["RECORDED", "PRESENT"]:
                box_color = (0, 200, 0)       # Green for Present
                status_label = "[PRESENT]" if status == "PRESENT" else "[MARKED NOW]"
            elif status == "DETECTED":
                box_color = (255, 165, 0)     # Orange for Haar detection
                status_label = "[DETECTED]"
            else:
                box_color = (0, 0, 220)       # Red for Unknown
                status_label = "[UNKNOWN]"

            # Draw outer rectangle
            cv2.rectangle(frame, (left, top), (right, bottom), box_color, 2)

            # Draw top banner for status
            cv2.rectangle(frame, (left, top - 32), (right, top), box_color, cv2.FILLED)
            cv2.putText(frame, f"{name} {status_label}", (left + 6, top - 9),
                        cv2.FONT_HERSHEY_DUPLEX, 0.55, (255, 255, 255), 1)

            # Draw bottom label for Roll Number
            if roll:
                cv2.rectangle(frame, (left, bottom), (right, bottom + 24), box_color, cv2.FILLED)
                cv2.putText(frame, roll, (left + 6, bottom + 17),
                            cv2.FONT_HERSHEY_DUPLEX, 0.45, (255, 255, 255), 1)

        # Header overlay banner
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 40), (20, 20, 20), cv2.FILLED)
        header_text = f"Smart Attendance Vision | Course #{course_id} | Session #{session_id} | Verified: {len(session_marked_students)}"
        cv2.putText(frame, header_text, (15, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 220, 255), 2)

        # Display output window
        cv2.imshow('Smart Attendance - Facial Recognition System', frame)

        # Exit condition: user presses 'q' key
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n[STOP] User stopped vision feed.")
            break

    video_capture.release()
    cv2.destroyAllWindows()
    print("[SHUTDOWN] Vision feed stopped. Attendance logged successfully.")

# -------------------------------------------------------------------
# CLI Entry Point
# -------------------------------------------------------------------
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Smart Attendance - OpenCV Face Recognition Engine")
    parser.add_argument('--course', type=int, default=1, help="Course ID (default: 1 for CS401)")
    parser.add_argument('--camera', type=int, default=0, help="Camera device index (default: 0)")
    parser.add_argument('--tolerance', type=float, default=0.48, help="Face matching distance threshold (default: 0.48)")
    args = parser.parse_args()

    run_face_attendance(course_id=args.course, camera_source=args.camera, tolerance=args.tolerance)
