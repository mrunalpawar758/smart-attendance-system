-- ====================================================================
-- SMART ATTENDANCE SYSTEM - RELATIONAL DATABASE SCHEMA (SQLite / MySQL)
-- B.Tech Minor Project Database Architecture
-- ====================================================================

-- 1. ROLES TABLE
-- Defines Access Control Levels: admin, teacher, student
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(20) NOT NULL UNIQUE,       -- 'admin', 'teacher', 'student'
    description VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. USERS TABLE
-- Stores all system actors with password hashes and role relationships
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    role_id INTEGER NOT NULL,
    roll_number VARCHAR(30) UNIQUE,          -- Specific to students (e.g. 'CS2026_01')
    department VARCHAR(50) DEFAULT 'Computer Science & Engineering',
    is_active INTEGER DEFAULT 1,             -- 1 for Active, 0 for Inactive
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE RESTRICT
);

-- 3. COURSES / SUBJECTS TABLE
-- Stores subjects assigned to faculty members
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_code VARCHAR(20) NOT NULL UNIQUE, -- e.g. 'CS401'
    course_name VARCHAR(120) NOT NULL,       -- e.g. 'Computer Networks & Security'
    teacher_id INTEGER NOT NULL,
    semester INTEGER NOT NULL CHECK(semester BETWEEN 1 AND 8),
    academic_year VARCHAR(10) NOT NULL,      -- e.g. '2026-27'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 4. ENROLLMENTS TABLE
-- Maps students to their enrolled courses (Many-to-Many relationship)
CREATE TABLE IF NOT EXISTS enrollments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'ACTIVE',     -- 'ACTIVE', 'DROPPED'
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    CONSTRAINT unique_student_course UNIQUE (student_id, course_id)
);

-- 5. ATTENDANCE SESSIONS TABLE
-- Tracks each lecture/class occurrence, supporting Manual, Dynamic QR, and Face Recognition
CREATE TABLE IF NOT EXISTS attendance_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id INTEGER NOT NULL,
    teacher_id INTEGER NOT NULL,
    session_date DATE NOT NULL,              -- YYYY-MM-DD
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP NULL,
    session_token VARCHAR(255) NULL,         -- Ephemeral token for dynamic QR verification
    token_expires_at TIMESTAMP NULL,         -- Expiry timestamp for 15-second rotating QR
    method VARCHAR(30) DEFAULT 'MANUAL',     -- 'MANUAL', 'DYNAMIC_QR', 'FACE_RECOGNITION'
    is_active INTEGER DEFAULT 1,             -- 1 if session is currently open for attendance
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 6. ATTENDANCE LOGS TABLE
-- Granular log per student per class session
CREATE TABLE IF NOT EXISTS attendance_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    status VARCHAR(15) NOT NULL CHECK(status IN ('PRESENT', 'ABSENT', 'LATE')),
    marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    verification_method VARCHAR(30) DEFAULT 'MANUAL', -- 'MANUAL', 'DYNAMIC_QR', 'FACE_RECOGNITION'
    ip_address VARCHAR(45) NULL,             -- Network IP for anti-proxy auditing
    remarks TEXT NULL,
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
    CONSTRAINT unique_session_student UNIQUE (session_id, student_id)
);

-- ====================================================================
-- PERFORMANCE INDEXES
-- ====================================================================
CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);
CREATE INDEX IF NOT EXISTS idx_users_roll ON users(roll_number);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_course ON enrollments(course_id);
CREATE INDEX IF NOT EXISTS idx_sessions_course_date ON attendance_sessions(course_id, session_date);
CREATE INDEX IF NOT EXISTS idx_logs_student_course ON attendance_logs(student_id, course_id);
CREATE INDEX IF NOT EXISTS idx_logs_session ON attendance_logs(session_id);

-- ====================================================================
-- SAMPLE INSERT QUERIES FOR TESTING
-- ====================================================================

-- 1. Populate Roles
INSERT OR IGNORE INTO roles (id, name, description) VALUES
(1, 'admin', 'System Administrator with full platform privileges'),
(2, 'teacher', 'Faculty member managing courses and attendance'),
(3, 'student', 'Enrolled candidate viewing attendance stats');

-- 2. Populate Sample Users
-- Password for all mock accounts: 'password123'
-- SHA256 of 'password123': 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f'
INSERT OR IGNORE INTO users (id, username, email, password_hash, full_name, role_id, roll_number, department) VALUES
(1, 'admin', 'admin@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Dr. Ramesh Sharma (Admin)', 1, NULL, 'Administration'),
(2, 'prof_gupta', 'gupta@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Prof. Priya Gupta', 2, NULL, 'Computer Science & Engineering'),
(3, 'prof_verma', 'verma@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Prof. Anil Verma', 2, NULL, 'Information Technology'),
(4, 'aarav_sharma', 'aarav@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Aarav Sharma', 3, 'CS2026_01', 'Computer Science & Engineering'),
(5, 'ananya_patel', 'ananya@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Ananya Patel', 3, 'CS2026_02', 'Computer Science & Engineering'),
(6, 'rohan_mehta', 'rohan@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Rohan Mehta', 3, 'CS2026_03', 'Computer Science & Engineering'),
(7, 'sneha_reddy', 'sneha@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Sneha Reddy', 3, 'CS2026_04', 'Computer Science & Engineering'),
(8, 'vikram_singh', 'vikram@college.edu', 'ef92b778bafe771e89245b89ecbc08a44a4e166c06659911881f383d4473e94f', 'Vikram Singh', 3, 'CS2026_05', 'Computer Science & Engineering');

-- 3. Populate Courses
INSERT OR IGNORE INTO courses (id, course_code, course_name, teacher_id, semester, academic_year) VALUES
(1, 'CS401', 'Computer Networks & Security', 2, 6, '2026-27'),
(2, 'CS402', 'Database Management Systems', 2, 6, '2026-27'),
(3, 'CS403', 'Artificial Intelligence & ML', 3, 6, '2026-27');

-- 4. Enroll Students in CS401
INSERT OR IGNORE INTO enrollments (student_id, course_id) VALUES
(4, 1), -- Aarav Sharma
(5, 1), -- Ananya Patel
(6, 1), -- Rohan Mehta
(7, 1), -- Sneha Reddy
(8, 1); -- Vikram Singh
