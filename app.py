import os
import secrets
import csv
import io
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_from_directory, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import pymysql
import pymysql.cursors

# ReportLab Imports for PDF Report
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from config import Config

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Database Connection Wrapper to map DictCursor compatibility
class PymysqlConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn
    
    def cursor(self, dictionary=False, **kwargs):
        if dictionary:
            return self._conn.cursor(pymysql.cursors.DictCursor)
        return self._conn.cursor()
        
    def commit(self):
        return self._conn.commit()
        
    def rollback(self):
        return self._conn.rollback()
        
    def close(self):
        return self._conn.close()

db_pool = None

def init_pool():
    global db_pool
    if db_pool is None:
        try:
            # Pre-check database existence
            conn = pymysql.connect(
                host=app.config['DB_HOST'],
                user=app.config['DB_USER'],
                password=app.config['DB_PASSWORD'],
                port=app.config['DB_PORT']
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {app.config['DB_NAME']}")
            cursor.close()
            conn.close()
            
            db_pool = True # Mark verified
        except Exception as err:
            app.logger.error(f"Failed to connect to MySQL database: {err}")
            raise err

def get_db():
    if db_pool is None:
        init_pool()
    conn = pymysql.connect(
        host=app.config['DB_HOST'],
        user=app.config['DB_USER'],
        password=app.config['DB_PASSWORD'],
        database=app.config['DB_NAME'],
        port=app.config['DB_PORT']
    )
    return PymysqlConnectionWrapper(conn)

# Allowed file extension helper
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

# Custom Template Filter for formatting Datetime safely
@app.template_filter('datetimeformat')
def datetimeformat(value, format='%Y-%m-%d %H:%M'):
    if value is None:
        return 'Date unavailable'
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except ValueError:
                return value
    try:
        return value.strftime(format)
    except Exception:
        return str(value)

# Custom Context Processor for layout data (unread notifications)
@app.context_processor
def inject_notifications():
    if 'user_id' in session:
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM notifications WHERE user_id = %s AND is_read = FALSE ORDER BY created_at DESC",
            (session['user_id'],)
        )
        notifications = cursor.fetchall()
        cursor.close()
        conn.close()
        return dict(unread_notifications=notifications, unread_count=len(notifications))
    return dict(unread_notifications=[], unread_count=0)

# Authentication Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Access denied. Administrators only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def principal_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'principal':
            flash('Access denied. Principal only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def authority_or_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') not in ['admin', 'principal', 'department', 'warden']:
            flash('Access denied. Authorities or Administrators only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def staff_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'staff':
            flash('Access denied. Staff members only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def warden_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'warden':
            flash('Access denied. Warden only.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------- ROUTES -----------------

# Landing Page / Index
@app.route('/')
def index():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch general statistics
    cursor.execute("SELECT COUNT(*) as total FROM grievances")
    total_g = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as resolved FROM grievances WHERE status = 'resolved'")
    resolved_g = cursor.fetchone()['resolved']
    
    cursor.execute("SELECT COUNT(*) as active_students FROM users WHERE role = 'student'")
    students_count = cursor.fetchone()['active_students']
    
    cursor.close()
    conn.close()
    
    return render_template(
        'index.html',
        total_grievances=total_g,
        resolved_grievances=resolved_g,
        total_students=students_count
    )

# Search Tracking Widget Route
@app.route('/track-status')
def track_status():
    grievance_id = request.args.get('id', '').strip()
    if not grievance_id or not grievance_id.isdigit():
        return jsonify({'success': False, 'message': 'Please enter a valid numeric Grievance ID.'})
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT g.id, g.title, g.status, g.category, g.created_at, g.is_anonymous, u.name as student_name 
           FROM grievances g 
           JOIN users u ON g.user_id = u.id 
           WHERE g.id = %s""",
        (int(grievance_id),)
    )
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        if result.get('is_anonymous'):
            result['student_name'] = 'Anonymous'
        # Format date for response
        result['created_at'] = result['created_at'].strftime('%Y-%m-%d %H:%M')
        return jsonify({'success': True, 'data': result})
    else:
        return jsonify({'success': False, 'message': 'Grievance not found. Please verify the ID.'})

# User Registration (Self registration allowed for students only)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        department = request.form.get('department', '').strip()
        
        # Validation
        if not name or not email or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')
            
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')
            
        if len(password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('register.html')
            
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        # Check if user already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('Email address is already registered.', 'danger')
            cursor.close()
            conn.close()
            return render_template('register.html')
            
        # Insert user with hashed password (always Student role)
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department, profile_photo) VALUES (%s, %s, %s, 'student', %s, 'student.png')",
            (name, email, hashed_password, department if department else None)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

# User Login - Unified Login page for all roles
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        selected_role = request.form.get('role', '').strip()
        
        if not email or not password or not selected_role:
            flash('Please enter email, password, and select your role.', 'danger')
            return render_template('login.html')
            
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            # Check role matching
            if user['role'] != selected_role:
                flash('Invalid role selected for these credentials.', 'danger')
                return render_template('login.html')
            
            # Check if active
            if not user['is_active']:
                flash('Your account is currently deactivated. Please contact the administrator.', 'danger')
                return render_template('login.html')
                
            session['user_id'] = user['id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role']
            session['department'] = user['department']
            session['profile_photo'] = user['profile_photo']
            
            flash(f"Welcome back, {user['name']}!", 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return render_template('login.html')
            
    return render_template('login.html')

# User Logout
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# Forgot Password Request
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        user = cursor.fetchone()
        
        if user:
            token = secrets.token_hex(20)
            cursor.execute("INSERT INTO password_resets (email, token) VALUES (%s, %s)", (email, token))
            conn.commit()
            
            # Simulate email sending: print to server logs
            reset_url = url_for('reset_password', token=token, _external=True)
            app.logger.info(f"--- DEMO EMAIL RESET LINK FOR {email} ---")
            app.logger.info(reset_url)
            app.logger.info("------------------------------------------")
            
            # Also display it in the flash for easy local demo testing
            flash(f"[DEMO SIMULATION] Reset link logged to console. Click here to reset: {reset_url}", 'success')
        else:
            # Prevent user enumeration by displaying a generic message
            flash('If the email is registered, you will receive password reset instructions.', 'info')
            
        cursor.close()
        conn.close()
        return redirect(url_for('forgot_password'))
        
    return render_template('forgot_password.html')

# Reset Password Form
@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token', '').strip()
    if not token:
        flash('Invalid or missing password reset token.', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Check token validity (we assume tokens don't expire for this simple simulation, or check datetime)
    cursor.execute("SELECT email, created_at FROM password_resets WHERE token = %s ORDER BY created_at DESC LIMIT 1", (token,))
    reset_request = cursor.fetchone()
    
    if not reset_request:
        flash('The password reset link is invalid or has expired.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        new_password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not new_password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('reset_password.html', token=token)
            
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
            
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return render_template('reset_password.html', token=token)
            
        email = reset_request['email']
        hashed_pwd = generate_password_hash(new_password)
        
        # Update password
        cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_pwd, email))
        # Clear reset tokens for this email
        cursor.execute("DELETE FROM password_resets WHERE email = %s", (email,))
        conn.commit()
        
        flash('Your password has been reset successfully. Please log in.', 'success')
        cursor.close()
        conn.close()
        return redirect(url_for('login'))
        
    cursor.close()
    conn.close()
    return render_template('reset_password.html', token=token)

# Unified Dashboard Redirect
@app.route('/dashboard')
@login_required
def dashboard():
    role = session.get('role')
    if role == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif role == 'principal':
        return redirect(url_for('principal_dashboard'))
    elif role == 'staff':
        return redirect(url_for('staff_dashboard'))
    elif role == 'warden':
        return redirect(url_for('warden_dashboard'))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    user_id = session['user_id']
    
    if role == 'department':
        # Department Authority Dashboard - All department and hostel grievances
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category IN ('Department', 'Hostel')")
        total_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category IN ('Department', 'Hostel') AND status = 'pending'")
        pending_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category IN ('Department', 'Hostel') AND status = 'resolved'")
        resolved_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category IN ('Department', 'Hostel') AND status = 'in-progress'")
        inprogress_g = cursor.fetchone()['count']
        
        cursor.execute(
            """SELECT g.*, u.name as student_name, u.email as student_email 
               FROM grievances g 
               JOIN users u ON g.user_id = u.id 
               WHERE g.category IN ('Department', 'Hostel') 
               ORDER BY g.created_at DESC LIMIT 5"""
        )
        recent_grievances = cursor.fetchall()
        
    elif role == 'warden':
        # Hostel Warden Dashboard - Only hostel complaints
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category = 'Hostel'")
        total_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category = 'Hostel' AND status = 'pending'")
        pending_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category = 'Hostel' AND status = 'resolved'")
        resolved_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE category = 'Hostel' AND status = 'in-progress'")
        inprogress_g = cursor.fetchone()['count']
        
        cursor.execute(
            """SELECT g.*, u.name as student_name, u.email as student_email 
               FROM grievances g 
               JOIN users u ON g.user_id = u.id 
               WHERE g.category = 'Hostel' 
               ORDER BY g.created_at DESC LIMIT 5"""
        )
        recent_grievances = cursor.fetchall()
        
    else:
        # Student Dashboard - Only their own raised complaints
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE user_id = %s", (user_id,))
        total_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE user_id = %s AND status = 'pending'", (user_id,))
        pending_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE user_id = %s AND status = 'resolved'", (user_id,))
        resolved_g = cursor.fetchone()['count']
        
        cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE user_id = %s AND status = 'in-progress'", (user_id,))
        inprogress_g = cursor.fetchone()['count']
        
        cursor.execute(
            "SELECT * FROM grievances WHERE user_id = %s ORDER BY created_at DESC LIMIT 5",
            (user_id,)
        )
        recent_grievances = cursor.fetchall()
    
    # Process anonymity: mask student details if the grievance is anonymous and not owned by current user
    for g in recent_grievances:
        if g.get('is_anonymous') and g.get('user_id') != session.get('user_id'):
            g['student_name'] = 'Anonymous'
            if 'student_email' in g:
                g['student_email'] = 'N/A'

    # Fetch notification alerts
    cursor.execute(
        "SELECT * FROM notifications WHERE user_id = %s ORDER BY created_at DESC LIMIT 5",
        (user_id,)
    )
    activities = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'dashboard.html',
        total=total_g,
        pending=pending_g,
        resolved=resolved_g,
        inprogress=inprogress_g,
        recent_grievances=recent_grievances,
        activities=activities
    )

# Staff Dashboard
@app.route('/staff')
@staff_required
def staff_dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    staff_id = session['user_id']
    
    # Get staff member's department
    cursor.execute("SELECT department FROM users WHERE id = %s", (staff_id,))
    staff_user = cursor.fetchone()
    staff_dept = staff_user['department'] if staff_user else None
    
    # Count grievances by status
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE staff_id = %s AND status = 'pending'
    """, (staff_id,))
    pending_count = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE staff_id = %s AND status = 'staff_review'
    """, (staff_id,))
    in_review_count = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE staff_id = %s AND status = 'in-progress'
    """, (staff_id,))
    resolved_count = cursor.fetchone()['count']
    
    # Get all grievances assigned to this staff member
    cursor.execute("""
        SELECT g.*, u.name as student_name, u.email as student_email 
        FROM grievances g 
        JOIN users u ON g.user_id = u.id 
        WHERE g.staff_id = %s 
        ORDER BY g.created_at DESC
    """, (staff_id,))
    grievances = cursor.fetchall()
    for g in grievances:
        if g.get('is_anonymous'):
            g['student_name'] = 'Anonymous Student'
            g['student_email'] = 'N/A'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'staff_dashboard.html',
        grievances=grievances,
        pending_count=pending_count,
        in_review_count=in_review_count,
        resolved_count=resolved_count
    )

# Staff Grievance Details
@app.route('/staff/grievance/<int:grievance_id>', methods=['GET', 'POST'])
@staff_required
def staff_grievance_details(grievance_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    staff_id = session['user_id']
    
    # Get grievance details
    cursor.execute("""
        SELECT g.*, 
               u.name as student_name, u.email as student_email, u.department as student_dept, u.profile_photo as student_photo
        FROM grievances g 
        JOIN users u ON g.user_id = u.id 
        WHERE g.id = %s AND g.staff_id = %s
    """, (grievance_id, staff_id))
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found or you do not have access.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('staff_dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        remarks = request.form.get('remarks', '').strip()
        if action == 'resolve' and remarks:
            # Update grievance status to in-progress (hidden from student view)
            cursor.execute("""
                UPDATE grievances 
                SET status = %s, remarks = %s, staff_approved = TRUE, warden_resolved = FALSE, updated_at = NOW()
                WHERE id = %s
            """, ('in-progress', remarks, grievance_id))
            conn.commit()
            
            # Create notification for authority
            cursor.execute("""
                INSERT INTO notifications (user_id, message, is_read, created_at)
                SELECT id, %s, FALSE, NOW() FROM users 
                WHERE role IN ('department', 'principal', 'admin')
            """, (f'Grievance #{grievance_id} has been resolved by staff and is waiting for your approval.',))
            conn.commit()
            
            flash('Grievance marked as resolved successfully!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('staff_dashboard'))
        elif action == 'need_info':
            # Update status to indicate more info needed
            cursor.execute("""
                UPDATE grievances 
                SET status = %s, remarks = %s, updated_at = NOW()
                WHERE id = %s
            """, ('staff_review', remarks, grievance_id))
            conn.commit()
            flash('Note added. Waiting for more information.', 'info')
        else:
            flash('Please fill in all required fields.', 'danger')
    
    # Get replies for this grievance
    cursor.execute("""
        SELECT gr.*, u.name as sender_name, u.role as sender_role, u.profile_photo as sender_photo 
        FROM grievance_replies gr 
        JOIN users u ON gr.sender_id = u.id 
        WHERE gr.grievance_id = %s 
        ORDER BY gr.created_at ASC
    """, (grievance_id,))
    replies = cursor.fetchall()
    
    # Mask anonymity if the grievance is anonymous
    if grievance and grievance.get('is_anonymous'):
        grievance['student_name'] = 'Anonymous Student'
        grievance['student_email'] = 'N/A (Anonymous)'
        grievance['student_dept'] = 'N/A'
        grievance['student_photo'] = 'default.png'
        
        for r in replies:
            if r.get('sender_role') == 'student':
                r['sender_name'] = 'Anonymous Student'
                r['sender_photo'] = 'default.png'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'staff_grievance_details.html',
        grievance=grievance,
        replies=replies
    )

# Staff Add Reply
@app.route('/staff/grievance/<int:grievance_id>/reply', methods=['POST'])
@staff_required
def staff_add_reply(grievance_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    staff_id = session['user_id']
    
    # Verify grievance is assigned to this staff member
    cursor.execute("SELECT id FROM grievances WHERE id = %s AND staff_id = %s", (grievance_id, staff_id))
    if not cursor.fetchone():
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('staff_dashboard'))
    
    message = request.form.get('message', '').strip()
    if message:
        cursor.execute("""
            INSERT INTO grievance_replies (grievance_id, sender_id, message, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (grievance_id, staff_id, message))
        conn.commit()
        flash('Reply added successfully!', 'success')
    else:
        flash('Please enter a message.', 'danger')
    
    cursor.close()
    conn.close()
    return redirect(url_for('staff_grievance_details', grievance_id=grievance_id))

# Warden Dashboard
@app.route('/warden')
@warden_required
def warden_dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    warden_id = session['user_id']
    
    # Count grievances by status
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE warden_id = %s AND status = 'pending'
    """, (warden_id,))
    pending_count = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE warden_id = %s AND status = 'staff_review'
    """, (warden_id,))
    in_review_count = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count FROM grievances 
        WHERE warden_id = %s AND status = 'in-progress'
    """, (warden_id,))
    resolved_count = cursor.fetchone()['count']
    
    # Get all grievances assigned to this warden
    cursor.execute("""
        SELECT g.*, u.name as student_name, u.email as student_email 
        FROM grievances g 
        JOIN users u ON g.user_id = u.id 
        WHERE g.warden_id = %s 
        ORDER BY g.created_at DESC
    """, (warden_id,))
    grievances = cursor.fetchall()
    for g in grievances:
        if g.get('is_anonymous'):
            g['student_name'] = 'Anonymous Student'
            g['student_email'] = 'N/A'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'staff_dashboard.html',
        grievances=grievances,
        pending_count=pending_count,
        in_review_count=in_review_count,
        resolved_count=resolved_count
    )

# Warden Grievance Details
@app.route('/warden/grievance/<int:grievance_id>', methods=['GET', 'POST'])
@warden_required
def warden_grievance_details(grievance_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    warden_id = session['user_id']
    
    # Get grievance details
    cursor.execute("""
        SELECT g.*, 
               u.name as student_name, u.email as student_email, u.department as student_dept, u.profile_photo as student_photo
        FROM grievances g 
        JOIN users u ON g.user_id = u.id 
        WHERE g.id = %s AND g.warden_id = %s
    """, (grievance_id, warden_id))
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found or you do not have access.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('warden_dashboard'))
    
    if request.method == 'POST':
        action = request.form.get('action', '').strip()
        remarks = request.form.get('remarks', '').strip()
        
        if action == 'resolve' and remarks:
            # Update grievance status to in-progress (hidden from student view)
            cursor.execute("""
                UPDATE grievances 
                SET status = %s, remarks = %s, warden_resolved = TRUE, staff_approved = FALSE, updated_at = NOW()
                WHERE id = %s
            """, ('in-progress', remarks, grievance_id))
            conn.commit()
            
            # Create notification for authority
            cursor.execute("""
                INSERT INTO notifications (user_id, message, is_read, created_at)
                SELECT id, %s, FALSE, NOW() FROM users 
                WHERE role IN ('department', 'principal', 'admin')
            """, (f'Grievance #{grievance_id} has been resolved by warden and is waiting for your approval.',))
            conn.commit()
            
            flash('Grievance marked as resolved successfully!', 'success')
            cursor.close()
            conn.close()
            return redirect(url_for('warden_dashboard'))
        elif action == 'need_info':
            cursor.execute("""
                UPDATE grievances 
                SET status = %s, remarks = %s, updated_at = NOW()
                WHERE id = %s
            """, ('staff_review', remarks, grievance_id))
            conn.commit()
            flash('Note added. Waiting for more information.', 'info')
        else:
            flash('Please fill in all required fields.', 'danger')
    
    # Get replies
    cursor.execute("""
        SELECT gr.*, u.name as sender_name, u.role as sender_role, u.profile_photo as sender_photo 
        FROM grievance_replies gr 
        JOIN users u ON gr.sender_id = u.id 
        WHERE gr.grievance_id = %s 
        ORDER BY gr.created_at ASC
    """, (grievance_id,))
    replies = cursor.fetchall()
    
    # Mask anonymity if the grievance is anonymous
    if grievance and grievance.get('is_anonymous'):
        grievance['student_name'] = 'Anonymous Student'
        grievance['student_email'] = 'N/A (Anonymous)'
        grievance['student_dept'] = 'N/A'
        grievance['student_photo'] = 'default.png'
        
        for r in replies:
            if r.get('sender_role') == 'student':
                r['sender_name'] = 'Anonymous Student'
                r['sender_photo'] = 'default.png'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'staff_grievance_details.html',
        grievance=grievance,
        replies=replies
    )

# Warden Add Reply
@app.route('/warden/grievance/<int:grievance_id>/reply', methods=['POST'])
@warden_required
def warden_add_reply(grievance_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    warden_id = session['user_id']
    
    cursor.execute("SELECT id FROM grievances WHERE id = %s AND warden_id = %s", (grievance_id, warden_id))
    if not cursor.fetchone():
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('warden_dashboard'))
    
    message = request.form.get('message', '').strip()
    if message:
        cursor.execute("""
            INSERT INTO grievance_replies (grievance_id, sender_id, message, created_at)
            VALUES (%s, %s, %s, NOW())
        """, (grievance_id, warden_id, message))
        conn.commit()
        flash('Reply added successfully!', 'success')
    else:
        flash('Please enter a message.', 'danger')
    
    cursor.close()
    conn.close()
    return redirect(url_for('warden_grievance_details', grievance_id=grievance_id))

# Submit Grievance (Student)
@app.route('/submit-grievance', methods=['GET', 'POST'])
@login_required
def submit_grievance():
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        category = request.form.get('category', '').strip()  # 'Department' or 'Hostel'
        priority = request.form.get('priority', 'medium').strip()
        description = request.form.get('description', '').strip()
        target_department = request.form.get('target_department', '').strip()
        attachment = request.files.get('attachment')
        
        # Validation
        if not title or not category or not description:
            flash('Please fill in all required fields.', 'danger')
            return render_template('submit_grievance.html')
            
        if category == 'Department' and not target_department:
            flash('Please select a target department.', 'danger')
            return render_template('submit_grievance.html')
            
        if priority not in ['low', 'medium', 'high']:
            priority = 'medium'
            
        filename = None
        if attachment and attachment.filename != '':
            if allowed_file(attachment.filename):
                file_ext = attachment.filename.rsplit('.', 1)[1].lower()
                unique_filename = f"attachment_{secrets.token_hex(10)}.{file_ext}"
                attachment.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                filename = unique_filename
            else:
                flash('File type not allowed. Supported formats: PNG, JPG, JPEG, GIF, PDF, DOC, DOCX.', 'danger')
                return render_template('submit_grievance.html')
                
        is_anonymous = 1 if request.form.get('is_anonymous') == '1' else 0
        targets_staff = 1 if request.form.get('targets_staff') == '1' else 0

        # Automatic Routing Assignment
        assigned_to = None
        staff_id = None
        warden_id = None
        targets_authority = False
        
        conn = get_db()
        cursor = conn.cursor(dictionary=True)
        
        if targets_staff:
            # Grievances targeting staff go directly to Complaint Authority
            cursor.execute("SELECT id FROM users WHERE role = 'department' LIMIT 1")
            dept_auth = cursor.fetchone()
            if dept_auth:
                assigned_to = dept_auth['id']
            targets_authority = True
        else:
            if category == 'Department':
                # Route to first available Staff member
                cursor.execute("SELECT id FROM users WHERE role = 'staff' LIMIT 1")
                staff_member = cursor.fetchone()
                if staff_member:
                    staff_id = staff_member['id']
            elif category == 'Hostel':
                # Route to first available Hostel Warden
                cursor.execute("SELECT id FROM users WHERE role = 'warden' LIMIT 1")
                warden_member = cursor.fetchone()
                if warden_member:
                    warden_id = warden_member['id']

        # Save to DB
        cursor.execute(
            """INSERT INTO grievances (user_id, assigned_to, staff_id, warden_id, title, category, target_department, description, attachment, priority, is_anonymous, targets_staff, targets_authority, status) 
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (session['user_id'], assigned_to, staff_id, warden_id, title, category, target_department if category == 'Department' else None, description, filename, priority, is_anonymous, targets_staff, targets_authority, 'pending')
        )
        conn.commit()
        grievance_id = cursor.lastrowid
        
        # Notify student
        notification_msg = f"Your grievance #{grievance_id} '{title}' has been submitted successfully."
        cursor.execute(
            "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
            (session['user_id'], notification_msg)
        )
        
        # Notify assigned staff/warden/authority
        if staff_id:
            notif_msg = f"New Department grievance #{grievance_id} assigned to you: '{title}'."
            cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (staff_id, notif_msg))
        elif warden_id:
            notif_msg = f"New Hostel grievance #{grievance_id} assigned to you: '{title}'."
            cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (warden_id, notif_msg))
        elif assigned_to:
            notif_msg = f"New grievance #{grievance_id} targeting staff/warden assigned to you: '{title}'."
            cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (assigned_to, notif_msg))
            
        # Notify Principal and Admin
        notif_system_msg = f"New {category} grievance #{grievance_id} submitted: '{title}'."
        cursor.execute("SELECT id FROM users WHERE role IN ('admin', 'principal')")
        system_users = cursor.fetchall()
        for sys_user in system_users:
            cursor.execute(
                "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
                (sys_user['id'], notif_system_msg)
            )
            
        conn.commit()
        cursor.close()
        conn.close()
        
        flash(f"Grievance submitted successfully! Grievance ID: {grievance_id}", 'success')
        return redirect(url_for('my_grievances'))
        
    return render_template('submit_grievance.html')

# My Grievances (List for student)
@app.route('/my-grievances')
@login_required
def my_grievances():
    if session.get('role') != 'student':
        return redirect(url_for('dashboard'))
        
    user_id = session['user_id']
    status_filter = request.args.get('status', 'all').strip()
    priority_filter = request.args.get('priority', 'all').strip()
    search_query = request.args.get('search', '').strip()
    sort_by = request.args.get('sort', 'newest').strip()
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Students can view all of their grievances
    query = "SELECT * FROM grievances WHERE user_id = %s"
    params = [user_id]
    
    if status_filter != 'all':
        query += " AND status = %s"
        params.append(status_filter)
        
    if priority_filter != 'all':
        query += " AND priority = %s"
        params.append(priority_filter)
        
    if search_query:
        query += " AND (title LIKE %s OR description LIKE %s)"
        params.append(f"%{search_query}%")
        params.append(f"%{search_query}%")
        
    # Sorting logic
    if sort_by == 'oldest':
        query += " ORDER BY created_at ASC"
    elif sort_by == 'priority_high':
        query += " ORDER BY CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END ASC, created_at DESC"
    else: # newest
        query += " ORDER BY created_at DESC"
        
    cursor.execute(query, tuple(params))
    grievances = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'my_grievances.html',
        grievances=grievances,
        status_filter=status_filter,
        priority_filter=priority_filter,
        search_query=search_query,
        sort_by=sort_by
    )

# Grievance Details & Chat Timeline
@app.route('/grievance/<int:id>')
@login_required
def grievance_details(id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch grievance details
    cursor.execute(
        """SELECT g.*, 
                  u.name as student_name, u.email as student_email, u.department as student_dept, u.profile_photo as student_photo,
                  s.name as staff_name, s.department as staff_dept
           FROM grievances g 
           JOIN users u ON g.user_id = u.id 
           LEFT JOIN users s ON g.assigned_to = s.id
           WHERE g.id = %s""",
        (id,)
    )
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Check permissions
    role = session.get('role')
    is_admin = (role == 'admin')
    is_principal = (role == 'principal')
    is_student_owner = (grievance['user_id'] == session['user_id'])
    
    is_authorized_authority = False
    if role == 'department':
        # Department Authority can access grievances targeting staff/warden and targets_authority
        is_authorized_authority = True
    elif role == 'staff' and grievance['staff_id'] == session['user_id']:
        # Staff can access their assigned grievances
        is_authorized_authority = True
    elif role == 'warden' and grievance['warden_id'] == session['user_id']:
        # Warden can access their assigned grievances
        is_authorized_authority = True
    

    if not is_admin and not is_principal and not is_student_owner and not is_authorized_authority:
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Fetch replies
    cursor.execute(
        """SELECT r.*, u.name as sender_name, u.role as sender_role, u.profile_photo as sender_photo 
           FROM grievance_replies r 
           JOIN users u ON r.sender_id = u.id 
           WHERE r.grievance_id = %s 
           ORDER BY r.created_at ASC""",
        (id,)
    )
    replies = cursor.fetchall()
    
    # Mark notifications as read
    cursor.execute(
        "UPDATE notifications SET is_read = TRUE WHERE user_id = %s AND (message LIKE %s OR message LIKE %s)",
        (session['user_id'], f"%#{id}%", f"%Grievance #{id}%")
    )
    conn.commit()
    
    # Fetch staff list for Complaint Authority assignment dropdown
    staff_list = []
    if role == 'department':
        cursor.execute("SELECT id, name, department, role FROM users WHERE role IN ('department', 'warden') ORDER BY name ASC")
        staff_list = cursor.fetchall()
        
    cursor.close()
    conn.close()
    
    # Mask anonymity if the grievance is anonymous
    if grievance.get('is_anonymous'):
        grievance['student_name'] = 'Anonymous Student'
        grievance['student_email'] = 'N/A (Anonymous)'
        grievance['student_dept'] = 'N/A'
        grievance['student_photo'] = 'default.png'
        
        for r in replies:
            if r.get('sender_role') == 'student':
                r['sender_name'] = 'Anonymous Student'
                r['sender_photo'] = 'default.png'
                
    return render_template('grievance_details.html', grievance=grievance, replies=replies, staff_list=staff_list)

# Reply to Grievance
@app.route('/grievance/<int:id>/reply', methods=['POST'])
@login_required
def reply_grievance(id):
    message = request.form.get('message', '').strip()
    if not message:
        flash('Reply message cannot be empty.', 'danger')
        return redirect(url_for('grievance_details', id=id))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT user_id, assigned_to, title, category, target_department FROM grievances WHERE id = %s", (id,))
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Check permissions
    role = session.get('role')
    is_admin = (role == 'admin')
    is_principal = (role == 'principal')
    is_owner = (grievance['user_id'] == session['user_id'])
    
    is_authorized_authority = False
    if role == 'department':
        # Department Authority can reply to both Department and Hostel complaints
        is_authorized_authority = True
    elif role == 'warden' and grievance['category'] == 'Hostel':
        is_authorized_authority = True
        
    if not is_admin and not is_principal and not is_owner and not is_authorized_authority:
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Insert reply
    cursor.execute(
        "INSERT INTO grievance_replies (grievance_id, sender_id, message) VALUES (%s, %s, %s)",
        (id, session['user_id'], message)
    )
    conn.commit()
    
    # Notify recipient
    if role in ['admin', 'principal', 'department', 'warden']:
        # Notify student owner
        notif_msg = f"An update/reply was added to your grievance #{id} by authority: '{grievance['title']}'."
        cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (grievance['user_id'], notif_msg))
    else:
        # Student replied: notify assigned authority and all admins/principal
        notif_msg = f"Student added a reply to grievance #{id}: '{grievance['title']}'."
        if grievance['assigned_to']:
            cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (grievance['assigned_to'], notif_msg))
            
        cursor.execute("SELECT id FROM users WHERE role IN ('admin', 'principal')")
        admins = cursor.fetchall()
        for admin in admins:
            cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (admin['id'], notif_msg))
            
    conn.commit()
    cursor.close()
    conn.close()
    
    flash('Reply posted successfully.', 'success')
    return redirect(url_for('grievance_details', id=id))

# Profile details & update
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    if request.method == 'POST':
        action = request.form.get('action', '')
        
        if action == 'update_info':
            name = request.form.get('name', '').strip()
            department = request.form.get('department', '').strip()
            profile_photo = request.files.get('profile_photo')
            
            if not name:
                flash('Name is required.', 'danger')
                return redirect(url_for('profile'))
                
            photo_filename = session.get('profile_photo', 'default.png')
            if profile_photo and profile_photo.filename != '':
                if allowed_file(profile_photo.filename):
                    file_ext = profile_photo.filename.rsplit('.', 1)[1].lower()
                    photo_filename = f"user_{session['user_id']}_{secrets.token_hex(5)}.{file_ext}"
                    profile_photo.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_filename))
                    session['profile_photo'] = photo_filename
                else:
                    flash('Invalid image format.', 'danger')
                    return redirect(url_for('profile'))
                    
            cursor.execute(
                "UPDATE users SET name = %s, department = %s, profile_photo = %s WHERE id = %s",
                (name, department if department else None, photo_filename, session['user_id'])
            )
            conn.commit()
            session['name'] = name
            session['department'] = department
            flash('Profile updated successfully!', 'success')
            
        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_new_password = request.form.get('confirm_new_password', '')
            
            if not current_password or not new_password or not confirm_new_password:
                flash('All password fields are required.', 'danger')
                return redirect(url_for('profile'))
                
            if new_password != confirm_new_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for('profile'))
                
            if len(new_password) < 6:
                flash('Password must be at least 6 characters long.', 'danger')
                return redirect(url_for('profile'))
                
            # Verify current password
            cursor.execute("SELECT password FROM users WHERE id = %s", (session['user_id'],))
            user_pwd_hash = cursor.fetchone()['password']
            
            if check_password_hash(user_pwd_hash, current_password):
                hashed_pwd = generate_password_hash(new_password)
                cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pwd, session['user_id']))
                conn.commit()
                flash('Password changed successfully!', 'success')
            else:
                flash('Incorrect current password.', 'danger')
                
        cursor.close()
        conn.close()
        return redirect(url_for('profile'))
        
    cursor.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user_info = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template('profile.html', user=user_info)

# ----------------- ADMIN ROUTES -----------------

# Admin Dashboard
@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Stat tiles
    cursor.execute("SELECT COUNT(*) as total FROM users WHERE role = 'student'")
    total_students = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as total FROM grievances")
    total_grievances = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as pending FROM grievances WHERE status = 'pending'")
    pending_grievances = cursor.fetchone()['pending']
    
    cursor.execute("SELECT COUNT(*) as inprogress FROM grievances WHERE status = 'in-progress'")
    inprogress_grievances = cursor.fetchone()['inprogress']
    
    cursor.execute("SELECT COUNT(*) as resolved FROM grievances WHERE status = 'resolved'")
    resolved_grievances = cursor.fetchone()['resolved']
    
    # Recent pending grievances
    cursor.execute(
        """SELECT g.*, u.name as student_name 
           FROM grievances g 
           JOIN users u ON g.user_id = u.id 
           ORDER BY g.created_at DESC LIMIT 5"""
    )
    recent_grievances = cursor.fetchall()
    for g in recent_grievances:
        if g.get('is_anonymous'):
            g['student_name'] = 'Anonymous'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'admin_dashboard.html',
        total_students=total_students,
        total_grievances=total_grievances,
        pending=pending_grievances,
        inprogress=inprogress_grievances,
        resolved=resolved_grievances,
        recent_grievances=recent_grievances
    )

# Admin AJAX data endpoint for Chart.js (Also used by Principal)
@app.route('/admin/chart-data')
@login_required
def admin_chart_data():
    if session.get('role') not in ['admin', 'principal']:
        return jsonify({'success': False, 'message': 'Access denied.'}), 403
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Category Distribution
    cursor.execute("SELECT category, COUNT(*) as count FROM grievances GROUP BY category")
    categories = cursor.fetchall()
    
    # Department Distribution
    cursor.execute("SELECT target_department, COUNT(*) as count FROM grievances WHERE category='Department' GROUP BY target_department")
    dept_stats = cursor.fetchall()
    
    # Monthly Trends (last 6 months)
    cursor.execute(
        """SELECT DATE_FORMAT(created_at, '%b %Y') as month, COUNT(*) as count 
           FROM grievances 
           GROUP BY DATE_FORMAT(created_at, '%Y-%m'), DATE_FORMAT(created_at, '%b %Y')
           ORDER BY MIN(created_at) ASC 
           LIMIT 6"""
    )
    monthly = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'categories': {item['category']: item['count'] for item in categories},
        'departments': {item['target_department'] if item['target_department'] else 'Unspecified': item['count'] for item in dept_stats},
        'monthly': {item['month']: item['count'] for item in monthly}
    })

# Admin Grievance Management Center
@app.route('/admin/grievances')
@login_required
def admin_grievances():
    # Only Admin and Principal can access all grievances list
    if session.get('role') not in ['admin', 'principal']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    status_filter = request.args.get('status', 'all').strip()
    priority_filter = request.args.get('priority', 'all').strip()
    search_query = request.args.get('search', '').strip()
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    query = """SELECT g.*, u.name as student_name, u.email as student_email 
               FROM grievances g 
               JOIN users u ON g.user_id = u.id 
               WHERE 1=1"""
    params = []
    
    if status_filter != 'all':
        query += " AND g.status = %s"
        params.append(status_filter)
        
    if priority_filter != 'all':
        query += " AND g.priority = %s"
        params.append(priority_filter)
        
    if search_query:
        query += " AND (g.title LIKE %s OR g.description LIKE %s OR (g.is_anonymous = 0 AND (u.name LIKE %s OR u.email LIKE %s)))"
        like_expr = f"%{search_query}%"
        params.extend([like_expr, like_expr, like_expr, like_expr])
        
    query += " ORDER BY g.created_at DESC"
    
    cursor.execute(query, tuple(params))
    grievances = cursor.fetchall()
    for g in grievances:
        if g.get('is_anonymous'):
            g['student_name'] = 'Anonymous'
            g['student_email'] = 'N/A'
    
    cursor.close()
    conn.close()
    
    return render_template(
        'manage_grievances.html',
        grievances=grievances,
        status_filter=status_filter,
        priority_filter=priority_filter,
        search_query=search_query
    )

# Admin/Authority - Update Grievance Status and Add Remarks
@app.route('/admin/update-status/<int:id>', methods=['POST'])
@login_required
def update_status(id):
    status = request.form.get('status', '').strip()
    remarks = request.form.get('remarks', '').strip()
    
    if status not in ['pending', 'in-progress', 'resolved']:
        flash('Invalid status value.', 'danger')
        return redirect(url_for('grievance_details', id=id))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT user_id, assigned_to, title, category, target_department, targets_staff FROM grievances WHERE id = %s", (id,))
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Permission verification
    role = session.get('role')
    is_authorized = False
    
    if role == 'department':
        # Complaint Authority can update status of any Department or Hostel complaint
        is_authorized = True
    elif role == 'warden' and grievance['category'] == 'Hostel':
        # Warden can update status of Hostel complaints, unless it targets staff
        if not grievance['targets_staff']:
            is_authorized = True
            
    if not is_authorized:
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Update Status & Remarks based on role
    status_for_msg = status
    if role == 'warden' and status == 'resolved':
        # Warden resolves, goes to pending approval (stays in-progress for student)
        cursor.execute(
            "UPDATE grievances SET status = 'in-progress', warden_resolved = TRUE, staff_approved = FALSE, remarks = %s WHERE id = %s", 
            (remarks if remarks else None, id)
        )
        status_for_msg = "Warden Resolved (Pending Authority Review)"
        notif_msg = f"Your grievance #{id} has been reviewed and resolved by the Warden. It is now undergoing final review."
        system_reply = f"[STATUS UPDATE]: Warden has marked the complaint as resolved. Pending final review by Complaint Authority.\nRemarks: {remarks if remarks else 'None'}"
    elif role == 'department' and status == 'resolved':
        # Authority resolves, officially approved and set to resolved
        cursor.execute(
            "UPDATE grievances SET status = 'resolved', warden_resolved = FALSE, staff_approved = FALSE, remarks = %s WHERE id = %s", 
            (remarks if remarks else None, id)
        )
        status_for_msg = "resolved"
        notif_msg = f"Your grievance #{id} status was officially resolved by the Complaint Authority with remarks: '{remarks[:60]}...'."
        system_reply = f"[STATUS UPDATE]: Complaint Authority has approved and officially marked the grievance as RESOLVED.\nRemarks: {remarks if remarks else 'None'}"
    else:
        cursor.execute(
            "UPDATE grievances SET status = %s, remarks = %s WHERE id = %s", 
            (status, remarks if remarks else None, id)
        )
        if role in ['department', 'warden']:
            cursor.execute("UPDATE grievances SET warden_resolved = FALSE, staff_approved = FALSE WHERE id = %s", (id,))
        status_for_msg = status
        notif_msg = f"Your grievance #{id} status was updated to '{status}' with remarks: '{remarks[:60]}...'."
        system_reply = f"[STATUS UPDATE]: Status changed to {status.upper()}.\nRemarks: {remarks if remarks else 'None'}"
        
    conn.commit()
    
    # Notify Student
    cursor.execute(
        "INSERT INTO notifications (user_id, message) VALUES (%s, %s)",
        (grievance['user_id'], notif_msg)
    )
    
    # Auto-post a reply to the conversation for clarity
    cursor.execute(
        "INSERT INTO grievance_replies (grievance_id, sender_id, message) VALUES (%s, %s, %s)",
        (id, session['user_id'], system_reply)
    )
    
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Grievance status updated to '{status}' with remarks.", 'success')
    return redirect(url_for('grievance_details', id=id))

# Authority - Assign Grievance to Warden
@app.route('/authority/assign-grievance/<int:id>', methods=['POST'])
@login_required
def assign_grievance(id):
    if session.get('role') != 'department':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    staff_id_raw = request.form.get('staff_id', '').strip()
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT user_id, title, targets_staff FROM grievances WHERE id = %s", (id,))
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    if grievance['targets_staff']:
        flash('This complaint targets a staff member/warden. The Complaint Authority must handle this case directly in consultation with the Principal.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('grievance_details', id=id))
        
    staff_id = int(staff_id_raw) if staff_id_raw and staff_id_raw.isdigit() else None
    
    cursor.execute("UPDATE grievances SET assigned_to = %s WHERE id = %s", (staff_id, id))
    conn.commit()
    
    if staff_id:
        cursor.execute("SELECT name FROM users WHERE id = %s", (staff_id,))
        staff_name = cursor.fetchone()['name']
        
        student_msg = f"Your grievance #{id} '{grievance['title']}' has been reassigned to: {staff_name}."
        cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (grievance['user_id'], student_msg))
        
        staff_msg = f"Grievance #{id} '{grievance['title']}' has been assigned to you for action."
        cursor.execute("INSERT INTO notifications (user_id, message) VALUES (%s, %s)", (staff_id, staff_msg))
        
        conn.commit()
        flash(f"Grievance successfully assigned to {staff_name}.", 'success')
    else:
        flash("Grievance assignment cleared.", 'info')
        
    cursor.close()
    conn.close()
    return redirect(url_for('grievance_details', id=id))

# Authority - Update Grievance Priority
@app.route('/authority/update-priority/<int:id>', methods=['POST'])
@login_required
def update_priority(id):
    if session.get('role') != 'department':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
        
    priority = request.form.get('priority', '').strip()
    if priority not in ['low', 'medium', 'high']:
        flash('Invalid priority value.', 'danger')
        return redirect(url_for('grievance_details', id=id))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE grievances SET priority = %s WHERE id = %s", (priority, id))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Priority updated to '{priority}'.", 'success')
    return redirect(url_for('grievance_details', id=id))

# Admin - Delete Grievance
@app.route('/admin/delete-grievance/<int:id>', methods=['POST'])
@admin_required
def delete_grievance(id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("DELETE FROM grievances WHERE id = %s", (id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Grievance #{id} has been deleted.", 'success')
    return redirect(url_for('admin_grievances'))

# Admin - Manage Registered Users (List View)
@app.route('/admin/users')
@admin_required
def manage_users():
    search_query = request.args.get('search', '').strip()
    role_filter = request.args.get('role', 'all').strip()
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    query = "SELECT id, name, email, role, department, is_active, created_at, profile_photo FROM users WHERE 1=1"
    params = []
    
    if role_filter != 'all':
        query += " AND role = %s"
        params.append(role_filter)
        
    if search_query:
        query += " AND (name LIKE %s OR email LIKE %s OR department LIKE %s)"
        like_expr = f"%{search_query}%"
        params.extend([like_expr, like_expr, like_expr])
        
    query += " ORDER BY created_at DESC"
    
    cursor.execute(query, tuple(params))
    users = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'manage_users.html',
        users=users,
        search_query=search_query,
        role_filter=role_filter
    )

# Admin CRUD - Add User
@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    role = request.form.get('role', 'student').strip()
    department = request.form.get('department', '').strip()
    is_active = 1 if request.form.get('is_active') == '1' else 0
    
    if not name or not email or not password or not role:
        flash('Name, Email, Password and Role are required.', 'danger')
        return redirect(url_for('manage_users'))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Check if duplicate email
    cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
    if cursor.fetchone():
        flash('Email is already registered by another account.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('manage_users'))
        
    hashed_pwd = generate_password_hash(password)
    photo_map = {
        'student': 'student.png',
        'department': 'authority.png',
        'warden': 'warden.png',
        'principal': 'principal.png',
        'admin': 'admin.png'
    }
    profile_photo = photo_map.get(role, 'default.png')
    cursor.execute(
        "INSERT INTO users (name, email, password, role, department, is_active, profile_photo) VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (name, email, hashed_pwd, role, department if department else None, is_active, profile_photo)
    )
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Account for '{name}' was created successfully.", 'success')
    return redirect(url_for('manage_users'))

# Admin CRUD - Edit User
@app.route('/admin/users/edit/<int:user_id>', methods=['POST'])
@admin_required
def admin_edit_user(user_id):
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    role = request.form.get('role', '').strip()
    department = request.form.get('department', '').strip()
    is_active = 1 if request.form.get('is_active') == '1' else 0
    
    if not name or not email or not role:
        flash('Name, Email and Role are required.', 'danger')
        return redirect(url_for('manage_users'))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Prevent editing own role/status to avoid locking out
    if email == session['email'] and (role != 'admin' or is_active != 1):
        flash('You cannot change your own admin role or de-activate yourself.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('manage_users'))
        
    # Check duplicate email
    cursor.execute("SELECT id FROM users WHERE email = %s AND id != %s", (email, user_id))
    if cursor.fetchone():
        flash('Email is already in use by another user.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('manage_users'))
        
    cursor.execute(
        "UPDATE users SET name = %s, email = %s, role = %s, department = %s, is_active = %s WHERE id = %s",
        (name, email, role, department if department else None, is_active, user_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"User account '{name}' updated successfully.", 'success')
    return redirect(url_for('manage_users'))

# Admin CRUD - Delete User
@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch details
    cursor.execute("SELECT email, name FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        flash('User not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('manage_users'))
        
    if user['email'] == session['email']:
        flash('You cannot delete your own admin account.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('manage_users'))
        
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash(f"Account for {user['name']} was deleted permanently.", 'success')
    return redirect(url_for('manage_users'))

# Admin CRUD - Reset Password
@app.route('/admin/users/reset-password/<int:user_id>', methods=['POST'])
@admin_required
def admin_reset_password(user_id):
    new_password = request.form.get('password', '').strip()
    if not new_password or len(new_password) < 6:
        flash('Please enter a valid password (min 6 characters).', 'danger')
        return redirect(url_for('manage_users'))
        
    hashed_pwd = generate_password_hash(new_password)
    
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_pwd, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("User's password was reset successfully.", 'success')
    return redirect(url_for('manage_users'))

# Admin CRUD - Toggle Activation Status via Switch
@app.route('/admin/users/toggle-status/<int:user_id>', methods=['POST'])
@admin_required
def admin_toggle_status(user_id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT email, is_active, name FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'User not found.'})
        
    if user['email'] == session['email']:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'You cannot deactivate your own account.'})
        
    new_status = 0 if user['is_active'] else 1
    cursor.execute("UPDATE users SET is_active = %s WHERE id = %s", (new_status, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    
    status_label = 'activated' if new_status else 'deactivated'
    return jsonify({'success': True, 'message': f"Account for {user['name']} was {status_label} successfully.", 'new_status': new_status})


# ----------------- PRINCIPAL ROUTE -----------------

# Principal Dashboard (Visual charts & Department Reports)
@app.route('/principal')
@principal_required
def principal_dashboard():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    # General metrics
    cursor.execute("SELECT COUNT(*) as count FROM grievances")
    total_g = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE status = 'pending'")
    pending_g = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE status = 'in-progress'")
    inprogress_g = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM grievances WHERE status = 'resolved'")
    resolved_g = cursor.fetchone()['count']
    
    # Department Reports
    cursor.execute(
        """SELECT target_department as dept, 
                  COUNT(*) as total, 
                  SUM(CASE WHEN status='resolved' THEN 1 ELSE 0 END) as resolved,
                  SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) as pending,
                  SUM(CASE WHEN status='in-progress' THEN 1 ELSE 0 END) as inprogress
           FROM grievances 
           WHERE category='Department' 
           GROUP BY target_department"""
    )
    dept_reports = cursor.fetchall()
    
    # Hostel Reports
    cursor.execute("SELECT COUNT(*) as total FROM grievances WHERE category='Hostel'")
    hostel_total = cursor.fetchone()['total']
    
    cursor.execute("SELECT COUNT(*) as resolved FROM grievances WHERE category='Hostel' AND status='resolved'")
    hostel_resolved = cursor.fetchone()['resolved']
    
    # Resolution Rate Math
    res_rate = 0
    if total_g > 0:
        res_rate = round((resolved_g / total_g) * 100, 1)
        
    cursor.close()
    conn.close()
    
    return render_template(
        'principal_dashboard.html',
        total=total_g,
        pending=pending_g,
        inprogress=inprogress_g,
        resolved=resolved_g,
        dept_reports=dept_reports,
        hostel_total=hostel_total,
        hostel_resolved=hostel_resolved,
        resolution_rate=res_rate
    )


# ----------------- EXPORTING REPORTS -----------------

# Export Grievances to CSV
@app.route('/admin/export-csv')
@login_required
def export_csv():
    if session.get('role') not in ['admin', 'principal']:
        return redirect(url_for('dashboard'))
        
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT g.id, g.is_anonymous, u.name as student, u.email, g.title, g.category, g.priority, g.status, g.created_at 
           FROM grievances g 
           JOIN users u ON g.user_id = u.id 
           ORDER BY g.created_at DESC"""
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    writer.writerow(['ID', 'Student Name', 'Email', 'Grievance Title', 'Category', 'Priority', 'Status', 'Date Created'])
    
    for row in rows:
        is_anon = row.get('is_anonymous')
        writer.writerow([
            row['id'],
            'Anonymous Student' if is_anon else row['student'],
            'N/A' if is_anon else row['email'],
            row['title'],
            row['category'],
            row['priority'],
            row['status'],
            row['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        ])
        
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=grievances_report.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# Export Single Grievance to PDF
@app.route('/grievance/<int:id>/pdf')
@login_required
def export_pdf(id):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute(
        """SELECT g.*, u.name as student_name, u.email as student_email, u.department as student_dept 
           FROM grievances g 
           JOIN users u ON g.user_id = u.id 
           WHERE g.id = %s""",
        (id,)
    )
    grievance = cursor.fetchone()
    
    if not grievance:
        flash('Grievance not found.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    role = session.get('role')
    is_admin = (role == 'admin')
    is_principal = (role == 'principal')
    is_student_owner = (grievance['user_id'] == session['user_id'])
    
    is_authorized_authority = False
    if role == 'department':
        # Department Authority can access both Department and Hostel complaints
        is_authorized_authority = True
    elif role == 'warden' and grievance['category'] == 'Hostel':
        is_authorized_authority = True
        
    if not is_admin and not is_principal and not is_student_owner and not is_authorized_authority:
        flash('Access denied.', 'danger')
        cursor.close()
        conn.close()
        return redirect(url_for('dashboard'))
        
    # Fetch replies
    cursor.execute(
        """SELECT r.*, u.name as sender_name, u.role as sender_role 
           FROM grievance_replies r 
           JOIN users u ON r.sender_id = u.id 
           WHERE r.grievance_id = %s 
           ORDER BY r.created_at ASC""",
        (id,)
    )
    replies = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    # Mask anonymity in PDF
    if grievance.get('is_anonymous') and not is_student_owner:
        grievance['student_name'] = 'Anonymous Student'
        grievance['student_email'] = 'N/A (Anonymous)'
        grievance['student_dept'] = 'N/A'
        
        for r in replies:
            if r.get('sender_role') == 'student':
                r['sender_name'] = 'Anonymous Student'
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#4f46e5'),
        spaceAfter=15
    )
    
    h2_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=15,
        spaceAfter=8
    )
    
    body_style = ParagraphStyle(
        'DocBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#475569')
    )
    
    meta_label = ParagraphStyle(
        'MetaLabel',
        parent=body_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0f172a')
    )
    
    story = []
    
    story.append(Paragraph(f"Student Grievance Report - #{grievance['id']}", title_style))
    story.append(Spacer(1, 10))
    
    data = [
        [Paragraph("Grievance ID:", meta_label), Paragraph(str(grievance['id']), body_style),
         Paragraph("Date Submitted:", meta_label), Paragraph(grievance['created_at'].strftime('%Y-%m-%d %H:%M'), body_style)],
        [Paragraph("Student Name:", meta_label), Paragraph(grievance['student_name'], body_style),
         Paragraph("Student Email:", meta_label), Paragraph(grievance['student_email'], body_style)],
        [Paragraph("Category:", meta_label), Paragraph(grievance['category'], body_style),
         Paragraph("Target/Dept:", meta_label), Paragraph(grievance['target_department'] or 'N/A', body_style)],
        [Paragraph("Priority:", meta_label), Paragraph(grievance['priority'].upper(), body_style),
         Paragraph("Current Status:", meta_label), Paragraph(grievance['status'].upper(), body_style)]
    ]
    
    table = Table(data, colWidths=[110, 150, 110, 150])
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#f8fafc')),
        ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#f8fafc')),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    
    story.append(table)
    story.append(Spacer(1, 15))
    
    story.append(Paragraph("Subject / Title", h2_style))
    story.append(Paragraph(grievance['title'], body_style))
    story.append(Spacer(1, 10))
    
    story.append(Paragraph("Description", h2_style))
    story.append(Paragraph(grievance['description'].replace('\n', '<br/>'), body_style))
    story.append(Spacer(1, 10))

    if grievance.get('remarks'):
        story.append(Paragraph("Official Action Remarks", h2_style))
        story.append(Paragraph(grievance['remarks'].replace('\n', '<br/>'), body_style))
        story.append(Spacer(1, 15))
    
    story.append(Paragraph("Conversation & Status Updates Timeline", h2_style))
    if not replies:
        story.append(Paragraph("No updates or replies recorded.", body_style))
    else:
        reply_data = []
        for r in replies:
            date_str = r['created_at'].strftime('%Y-%m-%d %H:%M')
            sender = f"{r['sender_name']} ({r['sender_role'].upper()})"
            msg_p = Paragraph(f"<b>{sender}</b> at {date_str}<br/>{r['message'].replace(chr(10), '<br/>')}", body_style)
            reply_data.append([msg_p])
            
        reply_table = Table(reply_data, colWidths=[520])
        reply_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('PADDING', (0,0), (-1,-1), 10),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#fcfcfc')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(reply_table)
        
    doc.build(story)
    
    buffer.seek(0)
    response = make_response(buffer.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=grievance_{id}_report.pdf"
    response.headers["Content-type"] = "application/pdf"
    return response

# Notifications - AJAX Endpoint to mark notification as read
@app.route('/notifications/read/<int:id>', methods=['POST'])
@login_required
def mark_notification_read(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s", (id, session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

# ----------------- UPLOADS ROUTE -----------------
@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# Main Entry
if __name__ == '__main__':
    init_pool()
    app.run(debug=True, host='0.0.0.0', port=5000)
