"""
Fuel Management System - Complete Application
A Streamlit-based fuel management system for multiple stations with supervisor and admin roles.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import hashlib
import sqlite3
import os
from contextlib import contextmanager

# Try to import plotly, but provide fallback if not available
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# ==================== DATABASE MANAGER ====================

DB_PATH = 'fuel_management.db'

def init_database():
    """Initialize SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Users table with active status
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            name TEXT NOT NULL,
            station TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            password_changed_at TIMESTAMP
        )
    ''')
    
    # Check if columns exist and add them if needed
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'is_active' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
    
    if 'password_changed_at' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP")
        cursor.execute("UPDATE users SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL")
    
    # Fuel requests table with provider_name field
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fuel_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT UNIQUE NOT NULL,
            date DATE NOT NULL,
            station TEXT NOT NULL,
            generator_fuel REAL DEFAULT 0,
            vehicle_fuel REAL DEFAULT 0,
            total_fuel REAL DEFAULT 0,
            provider_name TEXT,
            status TEXT DEFAULT 'Pending',
            requested_by TEXT NOT NULL,
            accepted_by TEXT,
            acceptance_time TIMESTAMP,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (requested_by) REFERENCES users(username)
        )
    ''')
    
    # Check if provider_name exists in fuel_requests
    cursor.execute("PRAGMA table_info(fuel_requests)")
    request_columns = [col[1] for col in cursor.fetchall()]
    if 'provider_name' not in request_columns:
        cursor.execute("ALTER TABLE fuel_requests ADD COLUMN provider_name TEXT")
    
    # Fuel history table with provider_name field
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fuel_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            date DATE NOT NULL,
            station TEXT NOT NULL,
            generator_fuel REAL DEFAULT 0,
            vehicle_fuel REAL DEFAULT 0,
            total_fuel REAL DEFAULT 0,
            provider_name TEXT,
            requested_by TEXT,
            accepted_by TEXT NOT NULL,
            acceptance_time TIMESTAMP NOT NULL,
            remarks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (accepted_by) REFERENCES users(username)
        )
    ''')
    
    # Check if requested_by exists in fuel_history
    cursor.execute("PRAGMA table_info(fuel_history)")
    history_columns = [col[1] for col in cursor.fetchall()]
    if 'provider_name' not in history_columns:
        cursor.execute("ALTER TABLE fuel_history ADD COLUMN provider_name TEXT")
    if 'requested_by' not in history_columns:
        cursor.execute("ALTER TABLE fuel_history ADD COLUMN requested_by TEXT")
    
    # Station supervisors mapping
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS station_supervisors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            station TEXT NOT NULL,
            username TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (username) REFERENCES users(username),
            UNIQUE(station, username)
        )
    ''')
    
    conn.commit()
    conn.close()
    
    # Create default admin if not exists
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = 'admin'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO users (username, password, role, name, is_active, password_changed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ('admin', hash_password('admin123'), 'admin', 'System Administrator', 1, datetime.now().isoformat()))
            conn.commit()
    
    # Ensure all existing users have is_active = 1 and password_changed_at set
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET is_active = 1 WHERE is_active IS NULL")
        cursor.execute("UPDATE users SET password_changed_at = CURRENT_TIMESTAMP WHERE password_changed_at IS NULL")
        conn.commit()

@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def execute_query(query, params=None, fetch_all=False, fetch_one=False):
    """Execute a query and return results"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if fetch_all:
            return cursor.fetchall()
        elif fetch_one:
            return cursor.fetchone()
        else:
            conn.commit()
            return cursor.lastrowid

# ==================== AUTHENTICATION SYSTEM ====================

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def init_auth_system():
    """Initialize authentication system"""
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if 'current_user' not in st.session_state:
        st.session_state.current_user = None
    
    if 'user_role' not in st.session_state:
        st.session_state.user_role = None

def login_user(username, password):
    """Authenticate user from database"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get user by username and password
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND password = ?",
                (username, hash_password(password))
            )
            user = cursor.fetchone()
            
            if user:
                # Check if user is active
                if user['is_active'] == 1:
                    st.session_state.logged_in = True
                    st.session_state.current_user = username
                    st.session_state.user_role = user['role']
                    return True, "Login successful"
                else:
                    return False, "Your account has been deactivated. Please contact administrator."
            else:
                return False, "Invalid username or password!"
    except Exception as e:
        return False, f"Login error: {str(e)}"

def logout_user():
    """Logout current user and clear session"""
    st.session_state.logged_in = False
    st.session_state.current_user = None
    st.session_state.user_role = None
    # Force session to clear
    for key in list(st.session_state.keys()):
        if key not in ['logged_in', 'current_user', 'user_role']:
            try:
                del st.session_state[key]
            except:
                pass

def get_user_info(username):
    """Get user information from database"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        return cursor.fetchone()

def check_user_active(username):
    """Check if user is active"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            return result[0] == 1 if result else False
    except:
        return False

def change_user_password(username, current_password, new_password, confirm_password, require_current=True):
    """Change user password"""
    try:
        # Validate passwords
        if not new_password or not confirm_password:
            return False, "New password and confirmation are required!"
        
        if new_password != confirm_password:
            return False, "New password and confirmation do not match!"
        
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters long!"
        
        # Verify current password if required
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password FROM users WHERE username = ?",
                (username,)
            )
            result = cursor.fetchone()
            
            if not result:
                return False, "User not found!"
            
            stored_password = result[0]
            
            # Check if current password matches (if required)
            if require_current:
                if not current_password:
                    return False, "Current password is required!"
                if stored_password != hash_password(current_password):
                    return False, "Current password is incorrect!"
            
            # Update password
            cursor.execute(
                "UPDATE users SET password = ?, password_changed_at = CURRENT_TIMESTAMP WHERE username = ?",
                (hash_password(new_password), username)
            )
            conn.commit()
            
            return True, "Password changed successfully!"
            
    except Exception as e:
        return False, f"Error changing password: {str(e)}"

# ==================== USER MANAGEMENT FUNCTIONS ====================

def toggle_user_status(username):
    """Toggle user active status"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get current status
            cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            
            if not result:
                return False, "User not found"
            
            current_status = result[0]
            new_status = 1 if current_status == 0 else 0
            
            # Update status
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE username = ?",
                (new_status, username)
            )
            conn.commit()
            
            # Verify the update
            cursor.execute("SELECT is_active FROM users WHERE username = ?", (username,))
            updated_result = cursor.fetchone()
            
            if updated_result and updated_result[0] == new_status:
                status_text = "activated" if new_status == 1 else "deactivated"
                return True, f"User {username} {status_text} successfully!"
            else:
                return False, "Failed to update user status"
                
    except Exception as e:
        return False, f"Error toggling user status: {str(e)}"

def reset_user_password(username):
    """Reset user password to default '123456'"""
    default_password = '123456'
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET password = ?, password_changed_at = CURRENT_TIMESTAMP WHERE username = ?",
                (hash_password(default_password), username)
            )
            conn.commit()
            return True, f"Password for {username} reset to default (123456)!"
    except Exception as e:
        return False, f"Error resetting password: {str(e)}"

def create_supervisor(username, password, name, station):
    """Create a new supervisor user"""
    try:
        # Create user
        user_query = """
            INSERT INTO users (username, password, role, name, station, is_active, password_changed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        execute_query(user_query, (username, hash_password(password), 'supervisor', name, station, 1, datetime.now().isoformat()))
        
        # Assign to station
        assign_supervisor(username, station)
        
        return True, "Supervisor created successfully!"
    except Exception as e:
        return False, f"Error creating supervisor: {str(e)}"

def get_all_users(role=None, active_only=None):
    """Get all users with optional filters"""
    query = "SELECT * FROM users WHERE 1=1"
    params = []
    
    if role:
        query += " AND role = ?"
        params.append(role)
    
    if active_only is not None:
        query += " AND is_active = ?"
        params.append(1 if active_only else 0)
    
    query += " ORDER BY created_at DESC"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

# ==================== DATA MANAGEMENT FUNCTIONS ====================

def generate_request_id():
    """Generate unique request ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"REQ-{timestamp}"

def save_fuel_request(station, generator_fuel, vehicle_fuel, provider_name, requested_by, remarks=""):
    """Save a new fuel request to database"""
    request_id = generate_request_id()
    total_fuel = generator_fuel + vehicle_fuel
    
    query = """
        INSERT INTO fuel_requests 
        (request_id, date, station, generator_fuel, vehicle_fuel, total_fuel, 
         provider_name, requested_by, remarks, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    params = (
        request_id,
        date.today().isoformat(),
        station,
        generator_fuel,
        vehicle_fuel,
        total_fuel,
        provider_name,
        requested_by,
        remarks,
        'Pending'
    )
    
    execute_query(query, params)
    return request_id

def get_pending_requests(station=None):
    """Get all pending requests, optionally filtered by station"""
    query = """
        SELECT * FROM fuel_requests 
        WHERE status = 'Pending'
    """
    params = []
    
    if station:
        query += " AND station = ?"
        params.append(station)
    
    query += " ORDER BY created_at DESC"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def get_all_requests(status_filter=None, station=None):
    """Get all requests with optional filters"""
    query = "SELECT * FROM fuel_requests WHERE 1=1"
    params = []
    
    if status_filter and status_filter != 'All':
        query += " AND status = ?"
        params.append(status_filter)
    
    if station:
        query += " AND station = ?"
        params.append(station)
    
    query += " ORDER BY created_at DESC"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def approve_fuel_request(request_id, accepted_by):
    """Approve a fuel request and move to history"""
    # Get the request
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fuel_requests WHERE request_id = ?", (request_id,))
        request = cursor.fetchone()
        
        if not request:
            return False, "Request not found"
        
        # Insert into history with requested_by
        cursor.execute("""
            INSERT INTO fuel_history 
            (request_id, date, station, generator_fuel, vehicle_fuel, total_fuel, 
             provider_name, requested_by, accepted_by, acceptance_time, remarks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request['request_id'],
            request['date'],
            request['station'],
            request['generator_fuel'],
            request['vehicle_fuel'],
            request['total_fuel'],
            request['provider_name'],
            request['requested_by'],
            accepted_by,
            datetime.now().isoformat(),
            request['remarks']
        ))
        
        # Delete from requests
        cursor.execute("DELETE FROM fuel_requests WHERE request_id = ?", (request_id,))
        conn.commit()
        
        return True, "Request approved successfully"

def reject_fuel_request(request_id):
    """Reject a fuel request"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM fuel_requests WHERE request_id = ?", (request_id,))
        conn.commit()
        return True, "Request rejected"

def get_fuel_history(station=None, start_date=None, end_date=None):
    """Get fuel history with optional filters"""
    query = "SELECT * FROM fuel_history WHERE 1=1"
    params = []
    
    if station:
        query += " AND station = ?"
        params.append(station)
    
    if start_date:
        query += " AND date >= ?"
        params.append(start_date.isoformat())
    
    if end_date:
        query += " AND date <= ?"
        params.append(end_date.isoformat())
    
    query += " ORDER BY date DESC, acceptance_time DESC"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def get_station_supervisors(station=None):
    """Get supervisors for a station or all stations"""
    query = """
        SELECT ss.station, ss.username, u.name, u.is_active 
        FROM station_supervisors ss
        JOIN users u ON ss.username = u.username
    """
    params = []
    
    if station:
        query += " WHERE ss.station = ?"
        params.append(station)
    
    query += " ORDER BY ss.station, u.name"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def assign_supervisor(username, station):
    """Assign a supervisor to a station"""
    query = """
        INSERT OR IGNORE INTO station_supervisors (station, username)
        VALUES (?, ?)
    """
    execute_query(query, (station, username))

def get_dashboard_stats():
    """Get dashboard statistics"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Pending requests count
        cursor.execute("SELECT COUNT(*) FROM fuel_requests WHERE status = 'Pending'")
        pending = cursor.fetchone()[0]
        
        # Today's fuel
        today = date.today().isoformat()
        cursor.execute("""
            SELECT COALESCE(SUM(total_fuel), 0) 
            FROM fuel_history 
            WHERE date = ?
        """, (today,))
        today_fuel = cursor.fetchone()[0]
        
        # Total active supervisors
        cursor.execute("""
            SELECT COUNT(DISTINCT ss.username) 
            FROM station_supervisors ss
            JOIN users u ON ss.username = u.username
            WHERE u.is_active = 1
        """)
        supervisors = cursor.fetchone()[0]
        
        # Monthly fuel
        current_month = date.today().replace(day=1).isoformat()
        cursor.execute("""
            SELECT COALESCE(SUM(total_fuel), 0) 
            FROM fuel_history 
            WHERE date >= ?
        """, (current_month,))
        monthly_fuel = cursor.fetchone()[0]
        
        return {
            'pending': pending,
            'today_fuel': today_fuel,
            'supervisors': supervisors,
            'monthly_fuel': monthly_fuel
        }

# ==================== STREAMLIT UI FUNCTIONS ====================

def login_page():
    """Display login page"""
    st.title("⛽Modjo Hawasa Fuel Management System")
    st.markdown(
    "<h1 style='text-align: center;'>⛽ Modjo Hawasa Fuel Management System</h1>",
    unsafe_allow_html=True
)
    st.markdown("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("https://img.icons8.com/color/96/000000/gas-station.png", width=100)
        st.subheader("Login to System")
        
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login")
            
            if submit:
                success, message = login_user(username, password)
                if success:
                    user_info = get_user_info(username)
                    st.success(f"Welcome {user_info['name']}!")
                    st.rerun()
                else:
                    st.error(f"❌ {message}")
        
        st.markdown("---")
        st.caption("Prepared by: Sintayehu Mekonin")

# ==================== PASSWORD CHANGE FUNCTION ====================

def change_password_ui():
    """UI for changing password"""
    with st.expander("🔑 Change Password", expanded=False):
        st.subheader("Change Your Password")
        st.info("Password must be at least 6 characters long.")
        
        with st.form("change_password_form"):
            current_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            submit = st.form_submit_button("Change Password")
            
            if submit:
                if current_password and new_password and confirm_password:
                    success, message = change_user_password(
                        st.session_state.current_user,
                        current_password,
                        new_password,
                        confirm_password,
                        require_current=True
                    )
                    if success:
                        st.success(f"✅ {message}")
                        st.info("Please login again with your new password.")
                        # Logout user after password change
                        logout_user()
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
                else:
                    st.error("❌ Please fill all password fields!")

# ==================== ADMIN DASHBOARD ====================

def admin_dashboard():
    """Admin dashboard with user management"""
    # Check if admin is still active
    if not check_user_active(st.session_state.current_user):
        logout_user()
        st.error("❌ Your account has been deactivated. Please contact administrator.")
        st.rerun()
        return
    
    st.header("👑 Administrator Dashboard")
    
    # Password change option for admin
    change_password_ui()
    
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview", "👤 Manage Supervisors", "📝 Fuel Requests", "📈 Reports"])
    
    with tab1:
        admin_overview()
    
    with tab2:
        manage_supervisors()
    
    with tab3:
        manage_fuel_requests()
    
    with tab4:
        admin_reports()

def admin_overview():
    """Admin overview statistics"""
    stats = get_dashboard_stats()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Pending Requests", stats['pending'])
    with col2:
        st.metric("Today's Fuel Distributed", f"{stats['today_fuel']:.1f} L")
    with col3:
        st.metric("Active Supervisors", stats['supervisors'])
    with col4:
        st.metric("Monthly Fuel Total", f"{stats['monthly_fuel']:.1f} L")
    
    if stats['pending'] > 0:
        st.warning(f"⚠️ You have {stats['pending']} pending fuel request(s) waiting for approval!")
    
    # Recent activity with supervisor column
    st.subheader("📋 Recent Activity")
    history = get_fuel_history()
    if not history.empty:
        # Get supervisor names for requested_by
        history_display = history.head(10).copy()
        
        # Rename columns for better display
        history_display = history_display[['date', 'station', 'generator_fuel', 'vehicle_fuel', 
                                          'total_fuel', 'provider_name', 'requested_by', 'accepted_by']]
        history_display.columns = ['Date', 'Station', 'Generator (L)', 'Vehicle (L)', 
                                   'Total (L)', 'Provider', 'Supervisor', 'Approved By']
        
        st.dataframe(history_display, use_container_width=True)
    else:
        st.info("No fuel history available")

def manage_supervisors():
    """Manage station supervisors"""
    st.subheader("👤 Manage Station Supervisors")
    
    # Create new supervisor
    with st.expander("➕ Create New Supervisor", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            new_username = st.text_input("Username")
            new_name = st.text_input("Full Name")
        
        with col2:
            new_password = st.text_input("Password", type="password")
            new_station = st.selectbox(
                "Assign Station",
                ['Modjo', 'Koka', 'Bote', 'Meki', 'Batu']
            )
        
        if st.button("Create Supervisor"):
            if new_username and new_password and new_name:
                # Check if username exists
                existing_user = get_user_info(new_username)
                if existing_user:
                    st.error("Username already exists!")
                else:
                    success, message = create_supervisor(new_username, new_password, new_name, new_station)
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
            else:
                st.error("Please fill all required fields!")
    
    # Display existing supervisors
    st.subheader("📋 Current Supervisors")
    
    # Show all users with role 'supervisor'
    supervisors_df = get_all_users(role='supervisor')
    
    if supervisors_df.empty:
        st.info("No supervisors created yet.")
    else:
        for _, supervisor in supervisors_df.iterrows():
            with st.container():
                col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1, 1, 1, 1])
                
                with col1:
                    st.write(f"**{supervisor['name']}**")
                
                with col2:
                    st.write(f"@{supervisor['username']}")
                    st.caption(f"Station: {supervisor['station']}")
                
                with col3:
                    status = "🟢 Active" if supervisor['is_active'] == 1 else "🔴 Inactive"
                    st.write(status)
                
                with col4:
                    # Toggle Active/Inactive
                    action = "🔴 Deactivate" if supervisor['is_active'] == 1 else "🟢 Activate"
                    if st.button(action, key=f"toggle_{supervisor['username']}"):
                        success, message = toggle_user_status(supervisor['username'])
                        if success:
                            st.success(f"✅ {message}")
                            # Check if deactivated user is current user
                            if supervisor['username'] == st.session_state.current_user:
                                st.warning("⚠️ You have deactivated your own account. Logging out...")
                                st.rerun()
                            else:
                                st.rerun()
                        else:
                            st.error(f"❌ {message}")
                
                with col5:
                    # Reset Password
                    if st.button("🔑 Reset", key=f"reset_{supervisor['username']}"):
                        success, message = reset_user_password(supervisor['username'])
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                
                with col6:
                    # Change password option for this user
                    if st.button("🔐 Change", key=f"change_{supervisor['username']}"):
                        st.session_state.change_password_target = supervisor['username']
                        st.rerun()
                
                st.divider()
        
        # Show change password modal if target is set
        if 'change_password_target' in st.session_state:
            with st.expander(f"🔑 Change Password for {st.session_state.change_password_target}", expanded=True):
                st.warning("This will change the password without requiring current password.")
                
                with st.form("admin_change_password_form"):
                    new_password = st.text_input("New Password", type="password")
                    confirm_password = st.text_input("Confirm New Password", type="password")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("Change Password"):
                            if new_password and confirm_password:
                                if new_password == confirm_password:
                                    if len(new_password) >= 6:
                                        success, message = change_user_password(
                                            st.session_state.change_password_target,
                                            "",  # No current password required for admin
                                            new_password,
                                            confirm_password,
                                            require_current=False
                                        )
                                        if success:
                                            st.success(f"✅ {message}")
                                            del st.session_state.change_password_target
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {message}")
                                    else:
                                        st.error("❌ Password must be at least 6 characters long!")
                                else:
                                    st.error("❌ Passwords do not match!")
                            else:
                                st.error("❌ Please fill all password fields!")
                    
                    with col2:
                        if st.form_submit_button("Cancel"):
                            del st.session_state.change_password_target
                            st.rerun()

def manage_fuel_requests():
    """Admin view and approve fuel requests"""
    st.subheader("📝 Fuel Requests Management")
    
    # Get all requests
    requests_df = get_all_requests()
    
    if requests_df.empty:
        st.info("📭 No fuel requests available")
        return
    
    # Filter requests
    status_filter = st.selectbox(
        "Filter by Status",
        ['All', 'Pending', 'Accepted', 'Rejected']
    )
    
    if status_filter != 'All':
        filtered_df = requests_df[requests_df['status'] == status_filter]
    else:
        filtered_df = requests_df
    
    if filtered_df.empty:
        st.info(f"No {status_filter.lower()} requests available")
        return
    
    # Display count
    st.write(f"**Total {status_filter.lower()} requests: {len(filtered_df)}**")
    st.markdown("---")
    
    # Display each request
    for _, request in filtered_df.iterrows():
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
            
            with col1:
                st.markdown(f"**📍 {request['station']} Station**")
                st.caption(f"🆔 ID: {request['request_id']}")
                st.caption(f"👤 Supervisor: {request['requested_by']}")
                if request.get('provider_name'):
                    st.caption(f"👤 Provider: {request['provider_name']}")
            
            with col2:
                st.write("**Fuel Details:**")
                st.write(f"⛽ Generator: {request['generator_fuel']:.1f} L")
                st.write(f"🚗 Vehicle: {request['vehicle_fuel']:.1f} L")
                st.write(f"📊 **Total: {request['total_fuel']:.1f} L**")
            
            with col3:
                st.write("**Request Info:**")
                st.write(f"📅 Date: {request['date']}")
                status = request['status']
                if status == 'Pending':
                    st.warning("⏳ Pending Approval")
                elif status == 'Accepted':
                    st.success("✅ Accepted")
                else:
                    st.error("❌ Rejected")
                if request.get('remarks'):
                    st.caption(f"📝 Notes: {request['remarks']}")
            
            with col4:
                if request['status'] == 'Pending':
                    st.write("**Actions:**")
                    
                    if st.button("✅ Approve", key=f"approve_{request['request_id']}", 
                               use_container_width=True):
                        success, message = approve_fuel_request(request['request_id'], 'admin')
                        if success:
                            st.success(f"✅ {message}")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                    
                    if st.button("❌ Reject", key=f"reject_{request['request_id']}", 
                               use_container_width=True):
                        success, message = reject_fuel_request(request['request_id'])
                        if success:
                            st.error(f"❌ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                else:
                    st.info("✓ Already processed")
            
            st.divider()

def admin_reports():
    """Admin reports"""
    st.subheader("📈 Comprehensive Reports")
    
    history_df = get_fuel_history()
    
    if history_df.empty:
        st.info("No historical data available")
        return
    
    # Date filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", pd.to_datetime(history_df['date']).min())
    with col2:
        end_date = st.date_input("End Date", pd.to_datetime(history_df['date']).max())
    
    filtered_df = history_df[
        (pd.to_datetime(history_df['date']).dt.date >= start_date) & 
        (pd.to_datetime(history_df['date']).dt.date <= end_date)
    ]
    
    if filtered_df.empty:
        st.warning("No data for selected date range")
        return
    
    # Station summary
    station_summary = filtered_df.groupby('station').agg({
        'total_fuel': ['sum', 'mean', 'count']
    }).round(2)
    station_summary.columns = ['Total Fuel', 'Average Fuel', 'Number of Requests']
    
    st.subheader("📊 Station Summary")
    st.dataframe(station_summary, use_container_width=True)
    
    # Visualization - only if plotly is available
    if PLOTLY_AVAILABLE:
        try:
            col1, col2 = st.columns(2)
            
            with col1:
                fig = px.bar(station_summary, x=station_summary.index, y='Total Fuel',
                             title='Total Fuel by Station',
                             color=station_summary.index)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                daily_trend = filtered_df.groupby('date')['total_fuel'].sum().reset_index()
                fig = px.line(daily_trend, x='date', y='total_fuel',
                              title='Daily Fuel Trend')
                st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.info(f"📊 Chart error: {str(e)}")
    else:
        st.info("📊 Charts are disabled. Install plotly to enable visualizations")

# ==================== SUPERVISOR DASHBOARD ====================

def supervisor_dashboard():
    """Supervisor dashboard"""
    # Check if supervisor is still active
    if not check_user_active(st.session_state.current_user):
        logout_user()
        st.error("❌ Your account has been deactivated. Please contact administrator.")
        st.rerun()
        return
    
    current_user = st.session_state.current_user
    user_info = get_user_info(current_user)
    station = user_info['station']
    
    st.header(f"📍 {station} Station - Supervisor Dashboard")
    st.info(f"Welcome, {user_info['name']}!")
    
    # Password change option for supervisor
    change_password_ui()
    
    # Renamed tab to "Accept Fuel"
    tab1, tab2, tab3 = st.tabs(["⛽ Accept Fuel", "📊 Station Overview", "📈 Reports"])
    
    with tab1:
        accept_fuel_ui(station)
    
    with tab2:
        station_overview(station)
    
    with tab3:
        supervisor_reports(station)

def accept_fuel_ui(station):
    """Supervisor accepts fuel - UI function"""
    st.subheader("⛽ Accept Fuel Delivery")
    st.info("Please fill in the details below to record fuel acceptance.")
    
    # Show existing pending requests
    pending_df = get_pending_requests(station)
    
    if not pending_df.empty:
        st.warning(f"⚠️ You have {len(pending_df)} pending request(s) waiting for admin approval")
        with st.expander("View Pending Requests"):
            st.dataframe(pending_df[['request_id', 'date', 'generator_fuel', 
                                   'vehicle_fuel', 'total_fuel', 'provider_name']])
    
    st.markdown("---")
    
    # New request form
    with st.form("accept_fuel_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            request_date = st.date_input(
                "Date", 
                date.today(),
                max_value=date.today(),
                help="Only today's date is allowed"
            )
            
            # Fuel Provider Name field
            provider_name = st.text_input(
                "Fuel Provider Name *",
                placeholder="Enter the name of the fuel provider",
                help="Who is supplying the fuel?"
            )
            
            generator_fuel = st.number_input(
                "Generator Fuel (Liters)", 
                min_value=0.0, 
                max_value=500.0, 
                step=1.0,
                value=0.0,
                help="Enter the amount of fuel for generators"
            )
        
        with col2:
            vehicle_fuel = st.number_input(
                "Vehicle Fuel (Liters)", 
                min_value=0.0, 
                max_value=500.0, 
                step=1.0,
                value=0.0,
                help="Enter the amount of fuel for vehicles"
            )
            remarks = st.text_area(
                "Remarks (Optional)", 
                placeholder="Any additional notes..."
            )
        
        submitted = st.form_submit_button("Submit Fuel Acceptance", use_container_width=True)
        
        if submitted:
            # Validate required fields
            if not provider_name:
                st.error("❌ Please enter the fuel provider name!")
            elif generator_fuel == 0 and vehicle_fuel == 0:
                st.error("❌ Please enter fuel amounts for at least one category!")
            else:
                # Save the request
                request_id = save_fuel_request(
                    station, 
                    generator_fuel, 
                    vehicle_fuel, 
                    provider_name,
                    st.session_state.current_user, 
                    remarks
                )
                st.success(f"✅ Fuel acceptance submitted for admin approval!")
                st.info(f"📋 Request ID: {request_id}")
                st.info(f"👤 Supervisor: {st.session_state.current_user}")
                st.info(f"👤 Fuel Provider: {provider_name}")
                st.info("⏳ Admin will review and approve your request shortly.")
                st.balloons()
                st.rerun()

def station_overview(station):
    """Station overview for supervisor"""
    st.subheader(f"📊 {station} Station Overview")
    
    # Get history for this station
    station_history = get_fuel_history(station=station)
    
    # Get pending requests count
    pending_df = get_pending_requests(station)
    pending_count = len(pending_df)
    
    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if not station_history.empty:
            total_fuel = station_history['total_fuel'].sum()
            st.metric("Total Fuel Received", f"{total_fuel:.1f} L")
        else:
            st.metric("Total Fuel Received", "0 L")
    
    with col2:
        if not station_history.empty:
            avg_fuel = station_history['total_fuel'].mean()
            st.metric("Average Daily Fuel", f"{avg_fuel:.1f} L")
        else:
            st.metric("Average Daily Fuel", "0 L")
    
    with col3:
        total_requests = len(station_history)
        st.metric("Total Deliveries", total_requests)
    
    with col4:
        st.metric("Pending Approval", pending_count)
    
    # Recent deliveries with supervisor column
    st.subheader("📋 Recent Deliveries")
    if not station_history.empty:
        display_df = station_history.head(10)[['date', 'generator_fuel', 'vehicle_fuel', 
                                              'total_fuel', 'provider_name', 'requested_by', 
                                              'accepted_by', 'acceptance_time']]
        display_df.columns = ['Date', 'Generator (L)', 'Vehicle (L)', 'Total (L)', 
                             'Provider', 'Supervisor', 'Approved By', 'Time']
        st.dataframe(display_df, use_container_width=True)
    else:
        st.info(f"No history available for {station} station")
    
    # Chart - only if plotly is available
    if PLOTLY_AVAILABLE and len(station_history) > 1:
        try:
            daily_fuel = station_history.groupby('date')['total_fuel'].sum().reset_index()
            fig = px.line(daily_fuel, x='date', y='total_fuel',
                          title=f'Daily Fuel Trend - {station} Station')
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            pass

def supervisor_reports(station):
    """Reports for supervisor"""
    st.subheader(f"📈 {station} Station Reports")
    
    station_history = get_fuel_history(station=station)
    
    if station_history.empty:
        st.info(f"No data available for {station} station")
        return
    
    # Monthly summary
    current_month = date.today().replace(day=1).isoformat()
    monthly_data = station_history[station_history['date'] >= current_month]
    
    if not monthly_data.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Monthly Summary**")
            st.write(f"Total Fuel: {monthly_data['total_fuel'].sum():.1f}L")
            st.write(f"Average: {monthly_data['total_fuel'].mean():.1f}L")
            st.write(f"Deliveries: {len(monthly_data)}")
            
            # Show supervisor info - handle None values
            supervisors = monthly_data['requested_by'].dropna().unique()
            if len(supervisors) > 0:
                st.write(f"**Supervisors:** {', '.join([str(s) for s in supervisors if s])}")
            else:
                st.write("**Supervisors:** No data available")
        
        with col2:
            # Fuel type breakdown - only if plotly is available
            if PLOTLY_AVAILABLE:
                try:
                    fuel_breakdown = pd.DataFrame({
                        'Type': ['Generator', 'Vehicle'],
                        'Total': [
                            monthly_data['generator_fuel'].sum(),
                            monthly_data['vehicle_fuel'].sum()
                        ]
                    })
                    fig = px.pie(fuel_breakdown, values='Total', names='Type',
                                 title='Fuel Type Distribution')
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.write("**Fuel Type Breakdown:**")
                    st.write(f"Generator: {monthly_data['generator_fuel'].sum():.1f}L")
                    st.write(f"Vehicle: {monthly_data['vehicle_fuel'].sum():.1f}L")
            else:
                st.write("**Fuel Type Breakdown:**")
                st.write(f"Generator: {monthly_data['generator_fuel'].sum():.1f}L")
                st.write(f"Vehicle: {monthly_data['vehicle_fuel'].sum():.1f}L")

# ==================== MAIN APPLICATION ====================

def main():
    """Main application entry point"""
    # Page config
    st.set_page_config(
        page_title="Fuel Management System",
        page_icon="⛽",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Initialize database
    init_database()
    
    # Initialize auth system
    init_auth_system()
    
    # Check login status
    if not st.session_state.logged_in:
        login_page()
        return
    
    # Verify session user is still active
    if not check_user_active(st.session_state.current_user):
        logout_user()
        st.error("❌ Your account has been deactivated. Please contact administrator.")
        st.rerun()
        return
    
    # Sidebar
    st.sidebar.markdown("### ⛽ Fuel Management System")
    st.sidebar.markdown("---")
    st.sidebar.write(f"**User:** {st.session_state.current_user}")
    st.sidebar.write(f"**Role:** {st.session_state.user_role}")
    
    # Show active status in sidebar
    if check_user_active(st.session_state.current_user):
        st.sidebar.success("🟢 Active")
    else:
        st.sidebar.error("🔴 Inactive")
    
    st.sidebar.markdown("---")
    
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        logout_user()
        st.rerun()
    
    st.sidebar.markdown("---")
    st.sidebar.caption("© 2018 E.C Modjo Hawasa Fuel Management System")
    st.sidebar.caption(f"Version: 1.0.0")
    
    # Route to appropriate dashboard
    if st.session_state.user_role == 'admin':
        admin_dashboard()
    elif st.session_state.user_role == 'supervisor':
        supervisor_dashboard()
    else:
        st.error("Unknown role. Please contact administrator.")

if __name__ == "__main__":
    main()
