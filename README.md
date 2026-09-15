# Smart Attendance System (B.Tech Minor Project)

A complete, production-grade **Smart Attendance System** built using **Python Flask, SQLite/MySQL, Bootstrap 5, Dynamic QR Verification, OpenCV Face Recognition, and Excel/CSV Analytics Reporting**.

---

## System Overview & Architecture

```
 smart_attendance_system/
 ├── app.py                      # Flask Server (Routes, Auth, Dashboard, QR API, Reports)
 ├── schema.sql                  # Dual SQLite/MySQL Relational Database DDL
 ├── init_db.py                  # Database Initializer & Historical Data Seeder
 ├── export_service.py           # Pandas Analytics & OpenPyXL Styled Excel/CSV Engine
 ├── face_recognition_module.py  # Standalone OpenCV + face_recognition Attendance Script
 ├── requirements.txt            # Python Dependencies
 ├── dataset/
 │   └── students/               # Student reference images (<ROLL>_<Name>.jpg)
 ├── templates/                  # Jinja2 Modern Bootstrap 5 UI Templates
 │   ├── base.html               # Glassmorphic Layout & Navigation
 │   ├── login.html              # Clean Authentication Form with 1-click Demo Fill
 │   ├── dashboard.html          # Teacher Dashboard with Attendance Toggles & Defaulter Alert
 │   ├── student_dashboard.html  # Student Portal with Subject % & Defaulter Warnings
 │   ├── qr_display.html         # Teacher Projector View (15s Dynamic Rotating QR)
 │   └── reports.html            # Analytics Preview with Date-Range Filter & Exports
 └── tests/
     └── test_attendance_system.py # Automated Test Suite (6 Unit & Integration Tests)
```

---

## 1. Database Schema & Architecture (Module 1)

The system implements a normalized relational database schema (`schema.sql`):
- **`roles`**: Role-based access control (`admin`, `teacher`, `student`).
- **`users`**: User identities, roles, SHA-256 password hashes, department, roll numbers.
- **`courses`**: Academic subjects assigned to faculty with semester and year.
- **`enrollments`**: Many-to-many relationship linking students to courses (`UNIQUE(student_id, course_id)`).
- **`attendance_sessions`**: Class occurrences supporting methods (`MANUAL`, `DYNAMIC_QR`, `FACE_RECOGNITION`), tokens, and timestamps.
- **`attendance_logs`**: Atomic student logs with status (`PRESENT`, `ABSENT`, `LATE`), verification method, and timestamp (`UNIQUE(session_id, student_id)`).

To reset and seed the database with 20 historical class sessions and realistic attendance percentages:
```bash
python init_db.py
```

---

## 2. Full-Stack Web Application (Module 2)

### Default Test Credentials
| Role | Username | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Faculty (Teacher)** | `prof_gupta` | `password123` | Assigned to CS401: Computer Networks |
| **Faculty (Teacher)** | `prof_verma` | `password123` | Assigned to CS403: Artificial Intelligence |
| **Student (Normal)** | `aarav_sharma` | `password123` | Roll No: `CS2026_01` (90% Attendance) |
| **Student (Defaulter)**| `rohan_mehta` | `password123` | Roll No: `CS2026_03` (65% Attendance - Alert) |
| **Student (Defaulter)**| `vikram_singh` | `password123` | Roll No: `CS2026_05` (50% Attendance - Alert) |
| **Administrator** | `admin` | `password123` | Full privileges |

### Running the Web Server
```bash
python app.py
```
Open **http://127.0.0.1:5000** in your browser.

- **Teacher Dashboard**: Displays student roster with Present/Absent toggle switches. Computes real-time monthly percentage. Automatically highlights students below **75%** with red alert badges (`Defaulter (<75%)`) and soft-red row styling.
- **Student Portal**: Shows cumulative and subject-wise percentages, total lectures attended, and clear warning banners if attendance is below 75%.

---

## 3. Dynamic QR Code Verification (Module 3)

### Anti-Proxy Mechanism:
1. The teacher clicks **Launch Dynamic QR (15s)** from their dashboard to display the projector view.
2. Every 15 seconds, the teacher's screen requests a cryptographic HMAC-SHA256 token from `/api/qr/token/<session_id>`.
3. The server generates a token containing `(session_id, epoch_window)` signed with a secret key.
4. When a student scans the QR code using their mobile camera or opens the verification link:
   - The server verifies that the student is logged in.
   - The server checks that the token is strictly within the current 15-second window (with a 1-window grace period for network transit).
   - The server enforces single-entry logging (`UNIQUE(session_id, student_id)`), preventing duplicate scans.
   - Screenshots forwarded to absent friends will expire within seconds and fail verification!
5. The teacher projector screen polls `/api/qr/attendees/<session_id>` in real-time, popping student names up as they scan.

---

## 4. Advanced Face Recognition Module (Module 4)

A standalone vision script using **OpenCV** and **face_recognition**:
```bash
python face_recognition_module.py --course 1
```

### Features:
- Reads student portrait reference photos from `dataset/students/` (named `<ROLL>_<Name>.jpg`).
- Generates 128-dimensional facial encodings.
- Connects to the classroom webcam feed (`cv2.VideoCapture(0)`).
- Downscales video frames (0.25x) and processes alternating frames for smooth **30+ FPS** performance.
- Draws green bounding boxes with Student Name and Roll Number for recognized students.
- Draws red bounding boxes for unknown or unregistered faces.
- **Session Cooldown Engine**: Records an entry in the SQLite `attendance_logs` table strictly **ONCE per student per session/day**, preventing repeated logging while students sit in front of the camera.

---

## 5. Report Generation & Defaulter Analytics (Module 5)

Accessible at `/reports/<course_id>`:
- **Filtering**: Filter records by Date Range (`start_date`, `end_date`) and Subject.
- **Defaulters Identification**: Dynamically calculates attendance percentages and marks all students below **75%** as Defaulters.
- **Excel Export (`.xlsx`)**: Formatted spreadsheet generated using **openpyxl** with customized navy title banners, column formatting, and **automated soft-red cell highlighting for defaulters**.
- **CSV Export (`.csv`)**: Standardized CSV file ready for university administrative ERP import.

---

## Automated Verification Suite

Run all automated unit and integration tests:
```bash
python -m unittest tests/test_attendance_system.py
```
This tests:
1. Password hashing consistency (SHA-256).
2. Database table creation and foreign key constraints.
3. Accurate attendance percentage calculation and defaulter `< 75%` detection.
4. 15-second Dynamic QR token rotation and expiration validation.
5. Excel (.xlsx) and CSV export file generation without corruption.
6. Flask endpoints and session authentication.
