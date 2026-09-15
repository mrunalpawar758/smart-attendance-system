"""
Smart Attendance System - Analytics & Export Service (Module 5)
Calculates attendance metrics, defaulters (< 75%), and exports reports to Excel (.xlsx) and CSV.
"""

import sqlite3
import os
import io
import pandas as pd
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'smart_attendance.db')

def get_db_connection():
    """Returns a SQLite connection with row dictionary access."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def fetch_attendance_analytics(course_id: int, start_date: str = None, end_date: str = None):
    """
    Fetches aggregate attendance records for a specific course and optional date range.
    Calculates total classes conducted, classes attended, classes absent, attendance %,
    and flags defaulters (< 75%).
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get course details
    cursor.execute("""
        SELECT c.id, c.course_code, c.course_name, u.full_name as teacher_name
        FROM courses c
        JOIN users u ON c.teacher_id = u.id
        WHERE c.id = ?
    """, (course_id,))
    course_row = cursor.fetchone()
    if not course_row:
        conn.close()
        raise ValueError(f"Course ID {course_id} not found.")

    course_info = dict(course_row)

    # Date range filters
    date_filter = ""
    params = [course_id]
    if start_date:
        date_filter += " AND s.session_date >= ?"
        params.append(start_date)
    if end_date:
        date_filter += " AND s.session_date <= ?"
        params.append(end_date)

    # Get all distinct sessions for this course within the date range
    cursor.execute(f"""
        SELECT id, session_date, method 
        FROM attendance_sessions s 
        WHERE s.course_id = ? {date_filter}
        ORDER BY s.session_date ASC
    """, params)
    sessions = cursor.fetchall()
    total_classes = len(sessions)

    # Query enrolled students and their attendance status
    query = f"""
        SELECT 
            u.id as student_id,
            u.roll_number,
            u.full_name,
            u.email,
            COUNT(DISTINCT s.id) as total_sessions,
            SUM(CASE WHEN l.status = 'PRESENT' THEN 1 ELSE 0 END) as attended_count,
            SUM(CASE WHEN l.status = 'ABSENT' THEN 1 ELSE 0 END) as absent_count,
            SUM(CASE WHEN l.status = 'LATE' THEN 1 ELSE 0 END) as late_count
        FROM enrollments e
        JOIN users u ON e.student_id = u.id
        LEFT JOIN attendance_sessions s ON s.course_id = e.course_id {date_filter}
        LEFT JOIN attendance_logs l ON l.session_id = s.id AND l.student_id = u.id
        WHERE e.course_id = ?
        GROUP BY u.id
        ORDER BY u.roll_number ASC
    """
    # Note params order: date_filter params then course_id
    query_params = []
    if start_date:
        query_params.append(start_date)
    if end_date:
        query_params.append(end_date)
    query_params.append(course_id)

    cursor.execute(query, query_params)
    rows = cursor.fetchall()
    conn.close()

    records = []
    for r in rows:
        attended = r['attended_count'] or 0
        classes_count = total_classes if total_classes > 0 else 0
        percentage = round((attended / classes_count * 100.0), 2) if classes_count > 0 else 0.0
        is_defaulter = percentage < 75.0

        records.append({
            'Student ID': r['student_id'],
            'Roll Number': r['roll_number'] or 'N/A',
            'Student Name': r['full_name'],
            'Email': r['email'],
            'Total Classes': classes_count,
            'Attended': attended,
            'Absent': classes_count - attended,
            'Attendance %': percentage,
            'Defaulter Status': 'Defaulter (< 75%)' if is_defaulter else 'Satisfactory (>= 75%)',
            'Is Defaulter': is_defaulter
        })

    return {
        'course': course_info,
        'total_classes': total_classes,
        'records': records
    }

def generate_csv_report(analytics_data: dict) -> str:
    """Generates a standardized CSV string from analytics data."""
    records = analytics_data['records']
    df = pd.DataFrame(records)
    # Drop internal boolean column for clean public report
    if 'Is Defaulter' in df.columns:
        df = df.drop(columns=['Is Defaulter'])
    return df.to_csv(index=False)

def generate_excel_report(analytics_data: dict) -> io.BytesIO:
    """
    Generates a professionally styled Excel spreadsheet (.xlsx) with:
    - Header banner with course info
    - Styled column headers
    - Soft red highlighting for low attendance defaulters (< 75%)
    - Soft green highlighting for satisfactory attendance (>= 75%)
    """
    course = analytics_data['course']
    records = analytics_data['records']

    df = pd.DataFrame(records)
    if 'Is Defaulter' in df.columns:
        df = df.drop(columns=['Is Defaulter'])

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Attendance Summary', startrow=4, index=False)
        worksheet = writer.sheets['Attendance Summary']

        # Title Block
        worksheet['A1'] = f"SMART ATTENDANCE REPORT: {course['course_name']} ({course['course_code']})"
        worksheet['A1'].font = Font(name='Calibri', size=15, bold=True, color='FFFFFF')
        worksheet['A1'].fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid') # Deep Navy
        worksheet.merge_cells('A1:I1')

        worksheet['A2'] = f"Instructor: {course['teacher_name']} | Total Classes Conducted: {analytics_data['total_classes']}"
        worksheet['A2'].font = Font(name='Calibri', size=11, italic=True)
        worksheet.merge_cells('A2:I2')

        # Header formatting (row 5)
        header_fill = PatternFill(start_color='3B82F6', end_color='3B82F6', fill_type='solid') # Slate Blue
        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')

        for col_idx in range(1, len(df.columns) + 1):
            cell = worksheet.cell(row=5, column=col_idx)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center')

        # Conditional Styling Fills
        defaulter_fill = PatternFill(start_color='FEE2E2', end_color='FEE2E2', fill_type='solid') # Soft Red
        defaulter_font = Font(name='Calibri', size=11, color='991B1B', bold=True)
        ok_fill = PatternFill(start_color='ECFDF5', end_color='ECFDF5', fill_type='solid') # Soft Green
        ok_font = Font(name='Calibri', size=11, color='065F46')

        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        # Apply formatting to data rows
        start_data_row = 6
        for row_idx, record in enumerate(records, start=start_data_row):
            is_defaulter = record['Is Defaulter']
            current_fill = defaulter_fill if is_defaulter else ok_fill
            current_font = defaulter_font if is_defaulter else ok_font

            for col_idx in range(1, len(df.columns) + 1):
                cell = worksheet.cell(row=row_idx, column=col_idx)
                cell.border = thin_border
                # Highlight the Defaulter Status and Attendance % specifically
                if df.columns[col_idx - 1] in ['Attendance %', 'Defaulter Status']:
                    cell.fill = current_fill
                    cell.font = current_font
                    cell.alignment = Alignment(horizontal='center')
                else:
                    cell.alignment = Alignment(horizontal='left' if col_idx <= 4 else 'center')

        from openpyxl.utils import get_column_letter
        # Auto-adjust column widths safely
        for col_idx, col in enumerate(worksheet.columns, start=1):
            col_letter = get_column_letter(col_idx)
            max_len = 12
            for cell in col:
                # Avoid calculating length on merged title row which causes excessively wide first column
                if cell.row > 4 and hasattr(cell, 'value') and cell.value is not None:
                    max_len = max(max_len, len(str(cell.value)))
            worksheet.column_dimensions[col_letter].width = max_len + 4

    output.seek(0)
    return output
