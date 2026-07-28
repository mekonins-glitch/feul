"""
Fuel Management System - Complete Application
A Streamlit-based fuel management system for multiple stations with supervisor and admin roles.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
import hashlib
import sqlite3
import os
from contextlib import contextmanager

# Try to import plotly, but provide fallback if not available
try:
    import plotly.express as px
    import plotly.graph_objects as go
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

def get_filtered_history(station=None, supervisor=None, start_date=None, end_date=None):
    """Get filtered fuel history with multiple filters"""
    query = """
        SELECT * FROM fuel_history 
        WHERE 1=1
    """
    params = []
    
    if station:
        query += " AND station = ?"
        params.append(station)
    
    if supervisor:
        query += " AND requested_by = ?"
        params.append(supervisor)
    
    if start_date:
        query += " AND date >= ?"
        params.append(start_date.isoformat())
    
    if end_date:
        query += " AND date <= ?"
        params.append(end_date.isoformat())
    
    query += " ORDER BY date DESC, acceptance_time DESC"
    
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn, params=params)

def get_all_supervisors():
    """Get all supervisors with their station assignments"""
    query = """
        SELECT DISTINCT u.username, u.name, u.station 
        FROM users u
        JOIN station_supervisors ss ON u.username = ss.username
        WHERE u.role = 'supervisor' AND u.is_active = 1
        ORDER BY u.name
    """
    with get_db_connection() as conn:
        return pd.read_sql_query(query, conn)

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

# ==================== REPORT FUNCTIONS ====================

def create_summary_table(df, title="Summary"):
    """Create a summary table from dataframe"""
    if df.empty:
        return None
    
    summary = {
        'Metric': ['Total Records', 'Total Fuel (L)', 'Average Fuel (L)', 'Max Fuel (L)', 'Min Fuel (L)'],
        'Value': [
            len(df),
            f"{df['total_fuel'].sum():.1f}",
            f"{df['total_fuel'].mean():.1f}",
            f"{df['total_fuel'].max():.1f}",
            f"{df['total_fuel'].min():.1f}"
        ]
    }
    return pd.DataFrame(summary)

def create_station_summary(df):
    """Create station-wise summary"""
    if df.empty:
        return None
    
    station_summary = df.groupby('station').agg({
        'total_fuel': ['sum', 'mean', 'count'],
        'generator_fuel': 'sum',
        'vehicle_fuel': 'sum'
    }).round(2)
    
    station_summary.columns = ['Total Fuel', 'Average Fuel', 'Number of Deliveries', 'Generator Total', 'Vehicle Total']
    return station_summary

def create_supervisor_summary(df):
    """Create supervisor-wise summary"""
    if df.empty:
        return None
    
    supervisor_summary = df.groupby('requested_by').agg({
        'total_fuel': ['sum', 'mean', 'count'],
        'generator_fuel': 'sum',
        'vehicle_fuel': 'sum'
    }).round(2)
    
    supervisor_summary.columns = ['Total Fuel', 'Average Fuel', 'Number of Deliveries', 'Generator Total', 'Vehicle Total']
    return supervisor_summary

def create_daily_trend(df):
    """Create daily trend data"""
    if df.empty:
        return None
    
    daily_trend = df.groupby('date').agg({
        'total_fuel': 'sum',
        'generator_fuel': 'sum',
        'vehicle_fuel': 'sum'
    }).reset_index()
    
    daily_trend.columns = ['Date', 'Total Fuel', 'Generator Fuel', 'Vehicle Fuel']
    return daily_trend

def export_to_csv(df, filename):
    """Export dataframe to CSV"""
    csv = df.to_csv(index=False)
    return st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name=filename,
        mime="text/csv"
    )

# ==================== STREAMLIT UI FUNCTIONS ====================

def login_page():
    """Display login page"""
    st.title("⛽ Fuel Management System")
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
        st.caption("Default Admin: admin / admin123")

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

# ==================== ADMIN REPORTS ====================

def admin_reports():
    """Admin reports with advanced filtering"""
    st.header("📈 Reports & Analytics")
    
    # Get all history data
    history_df = get_fuel_history()
    
    if history_df.empty:
        st.info("No data available for reports. Please add fuel records first.")
        return
    
    # Convert date column
    history_df['date'] = pd.to_datetime(history_df['date']).dt.date
    
    # Get available supervisors
    supervisors_df = get_all_supervisors()
    supervisor_list = ['All'] + supervisors_df['username'].tolist()
    
    # Get available stations
    stations = ['All', 'Modjo', 'Koka', 'Bote', 'Meki', 'Batu']
    
    # Filter section
    st.subheader("🔍 Filter Reports")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        # Date range
        min_date = history_df['date'].min()
        max_date = history_df['date'].max()
        
        start_date = st.date_input(
            "Start Date",
            value=min_date,
            min_value=min_date,
            max_value=max_date
        )
    
    with col2:
        end_date = st.date_input(
            "End Date",
            value=max_date,
            min_value=min_date,
            max_value=max_date
        )
    
    with col3:
        # Station filter
        station_filter = st.selectbox(
            "Station",
            stations
        )
    
    with col4:
        # Supervisor filter
        supervisor_filter = st.selectbox(
            "Supervisor",
            supervisor_list
        )
    
    # Fuel type filter
    fuel_type = st.radio(
        "Fuel Type",
        ['All', 'Generator Only', 'Vehicle Only', 'Both'],
        horizontal=True
    )
    
    # Apply filters
    filtered_df = history_df.copy()
    
    # Date filter
    filtered_df = filtered_df[
        (filtered_df['date'] >= start_date) & 
        (filtered_df['date'] <= end_date)
    ]
    
    # Station filter
    if station_filter != 'All':
        filtered_df = filtered_df[filtered_df['station'] == station_filter]
    
    # Supervisor filter
    if supervisor_filter != 'All':
        filtered_df = filtered_df[filtered_df['requested_by'] == supervisor_filter]
    
    # Fuel type filter
    if fuel_type == 'Generator Only':
        filtered_df = filtered_df[filtered_df['vehicle_fuel'] == 0]
    elif fuel_type == 'Vehicle Only':
        filtered_df = filtered_df[filtered_df['generator_fuel'] == 0]
    elif fuel_type == 'Both':
        filtered_df = filtered_df[(filtered_df['generator_fuel'] > 0) & (filtered_df['vehicle_fuel'] > 0)]
    
    # Display results
    st.subheader(f"📊 Report Results ({len(filtered_df)} records)")
    
    # Summary metrics
    if not filtered_df.empty:
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1:
            st.metric("Total Fuel", f"{filtered_df['total_fuel'].sum():.1f} L")
        with col2:
            st.metric("Generator Fuel", f"{filtered_df['generator_fuel'].sum():.1f} L")
        with col3:
            st.metric("Vehicle Fuel", f"{filtered_df['vehicle_fuel'].sum():.1f} L")
        with col4:
            st.metric("Avg per Delivery", f"{filtered_df['total_fuel'].mean():.1f} L")
        with col5:
            st.metric("Total Deliveries", len(filtered_df))
    
    # Create tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Detailed Data", "📊 Station Summary", "👤 Supervisor Summary", "📈 Charts"])
    
    with tab1:
        # Detailed data table
        if not filtered_df.empty:
            display_df = filtered_df[['date', 'station', 'generator_fuel', 'vehicle_fuel', 
                                     'total_fuel', 'provider_name', 'requested_by', 'accepted_by']]
            display_df.columns = ['Date', 'Station', 'Generator (L)', 'Vehicle (L)', 
                                 'Total (L)', 'Provider', 'Supervisor', 'Approved By']
            st.dataframe(display_df, use_container_width=True)
            
            # Export option
            col1, col2 = st.columns(2)
            with col1:
                export_to_csv(filtered_df, f"fuel_report_{datetime.now().strftime('%Y%m%d')}.csv")
            with col2:
                # Summary statistics
                summary_df = create_summary_table(filtered_df)
                if summary_df is not None:
                    st.dataframe(summary_df, use_container_width=True)
        else:
            st.info("No data matches the selected filters")
    
    with tab2:
        # Station summary
        station_summary = create_station_summary(filtered_df)
        if station_summary is not None and not station_summary.empty:
            st.dataframe(station_summary, use_container_width=True)
            
            # Chart - only if plotly is available
            if PLOTLY_AVAILABLE:
                try:
                    fig = px.bar(
                        station_summary, 
                        x=station_summary.index, 
                        y='Total Fuel',
                        title='Fuel Distribution by Station',
                        color=station_summary.index,
                        text=station_summary['Total Fuel']
                    )
                    fig.update_traces(texttemplate='%{text:.1f}L', textposition='outside')
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.info("Chart rendering error")
        else:
            st.info("No data available for station summary")
    
    with tab3:
        # Supervisor summary
        supervisor_summary = create_supervisor_summary(filtered_df)
        if supervisor_summary is not None and not supervisor_summary.empty:
            st.dataframe(supervisor_summary, use_container_width=True)
            
            # Chart - only if plotly is available
            if PLOTLY_AVAILABLE:
                try:
                    fig = px.bar(
                        supervisor_summary, 
                        x=supervisor_summary.index, 
                        y='Total Fuel',
                        title='Fuel Distribution by Supervisor',
                        color=supervisor_summary.index,
                        text=supervisor_summary['Total Fuel']
                    )
                    fig.update_traces(texttemplate='%{text:.1f}L', textposition='outside')
                    fig.update_layout(showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)
                except Exception as e:
                    st.info("Chart rendering error")
        else:
            st.info("No data available for supervisor summary")
    
    with tab4:
        # Charts section
        if PLOTLY_AVAILABLE and not filtered_df.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                # Daily trend
                daily_trend = create_daily_trend(filtered_df)
                if daily_trend is not None:
                    fig = px.line(
                        daily_trend, 
                        x='Date', 
                        y=['Generator Fuel', 'Vehicle Fuel', 'Total Fuel'],
                        title='Daily Fuel Trend',
                        markers=True
                    )
                    fig.update_layout(legend_title_text='Fuel Type')
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Fuel type breakdown
                if not filtered_df.empty:
                    fuel_breakdown = pd.DataFrame({
                        'Type': ['Generator', 'Vehicle'],
                        'Total': [
                            filtered_df['generator_fuel'].sum(),
                            filtered_df['vehicle_fuel'].sum()
                        ]
                    })
                    fig = px.pie(
                        fuel_breakdown, 
                        values='Total', 
                        names='Type',
                        title='Fuel Type Distribution',
                        hole=0.3
                    )
                    st.plotly_chart(fig, use_container_width=True)
            
            # Provider analysis
            if not filtered_df.empty and filtered_df['provider_name'].notna().any():
                st.subheader("Top Fuel Providers")
                provider_summary = filtered_df.groupby('provider_name')['total_fuel'].sum().sort_values(ascending=False).head(10)
                if not provider_summary.empty:
                    fig = px.bar(
                        x=provider_summary.values,
                        y=provider_summary.index,
                        orientation='h',
                        title='Top 10 Fuel Providers',
                        text=provider_summary.values
                    )
                    fig.update_traces(texttemplate='%{text:.1f}L', textposition='outside')
                    fig.update_layout(xaxis_title='Total Fuel (L)')
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Charts require plotly library. Install with: pip install plotly")

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
        supervisor_reports(station, current_user)

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

# ==================== SUPERVISOR REPORTS ====================

def supervisor_reports(station, current_user):
    """Supervisor reports with filtering"""
    st.subheader(f"📈 {station} Station Reports")
    
    # Get history for this station
    station_history = get_fuel_history(station=station)
    
    if station_history.empty:
        st.info(f"No data available for {station} station")
        return
    
    # Convert date column
    station_history['date'] = pd.to_datetime(station_history['date']).dt.date
    
    # Filter section
    st.subheader("🔍 Filter Reports")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Date range
        min_date = station_history['date'].min()
        max_date = station_history['date'].max()
        
        start_date = st.date_input(
            "Start Date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
            key="supervisor_start_date"
        )
    
    with col2:
        end_date = st.date_input(
            "End Date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
            key="supervisor_end_date"
        )
    
    with col3:
        # Fuel type filter
        fuel_type = st.selectbox(
            "Fuel Type",
            ['All', 'Generator Only', 'Vehicle Only', 'Both']
        )
    
    # Apply filters
    filtered_df = station_history.copy()
    
    # Date filter
    filtered_df = filtered_df[
        (filtered_df['date'] >= start_date) & 
        (filtered_df['date'] <= end_date)
    ]
    
    # Fuel type filter
    if fuel_type == 'Generator Only':
        filtered_df = filtered_df[filtered_df['vehicle_fuel'] == 0]
    elif fuel_type == 'Vehicle Only':
        filtered_df = filtered_df[filtered_df['generator_fuel'] == 0]
    elif fuel_type == 'Both':
        filtered_df = filtered_df[(filtered_df['generator_fuel'] > 0) & (filtered_df['vehicle_fuel'] > 0)]
    
    # Display results
    st.subheader(f"📊 Report Results ({len(filtered_df)} records)")
    
    # Summary metrics
    if not filtered_df.empty:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Fuel", f"{filtered_df['total_fuel'].sum():.1f} L")
        with col2:
            st.metric("Generator Fuel", f"{filtered_df['generator_fuel'].sum():.1f} L")
        with col3:
            st.metric("Vehicle Fuel", f"{filtered_df['vehicle_fuel'].sum():.1f} L")
        with col4:
            st.metric("Total Deliveries", len(filtered_df))
    
    # Create tabs for different views
    tab1, tab2, tab3 = st.tabs(["📋 Detailed Data", "📊 Summary", "📈 Charts"])
    
    with tab1:
        if not filtered_df.empty:
            display_df = filtered_df[['date', 'generator_fuel', 'vehicle_fuel', 
                                     'total_fuel', 'provider_name', 'accepted_by']]
            display_df.columns = ['Date', 'Generator (L)', 'Vehicle (L)', 
                                 'Total (L)', 'Provider', 'Approved By']
            st.dataframe(display_df, use_container_width=True)
            
            # Export option
            export_to_csv(filtered_df, f"station_report_{station}_{datetime.now().strftime('%Y%m%d')}.csv")
        else:
            st.info("No data matches the selected filters")
    
    with tab2:
        if not filtered_df.empty:
            # Summary table
            summary_df = create_summary_table(filtered_df)
            if summary_df is not None:
                st.dataframe(summary_df, use_container_width=True)
            
            # Daily summary
            st.subheader("Daily Summary")
            daily_summary = filtered_df.groupby('date').agg({
                'total_fuel': 'sum',
                'generator_fuel': 'sum',
                'vehicle_fuel': 'sum',
                'request_id': 'count'
            }).reset_index()
            daily_summary.columns = ['Date', 'Total Fuel', 'Generator Fuel', 'Vehicle Fuel', 'Deliveries']
            st.dataframe(daily_summary, use_container_width=True)
            
            # Provider summary
            if filtered_df['provider_name'].notna().any():
                st.subheader("Provider Summary")
                provider_summary = filtered_df.groupby('provider_name').agg({
                    'total_fuel': 'sum',
                    'request_id': 'count'
                }).reset_index()
                provider_summary.columns = ['Provider', 'Total Fuel', 'Deliveries']
                provider_summary = provider_summary.sort_values('Total Fuel', ascending=False)
                st.dataframe(provider_summary, use_container_width=True)
        else:
            st.info("No data available for summary")
    
    with tab3:
        # Charts - only if plotly is available
        if PLOTLY_AVAILABLE and not filtered_df.empty:
            col1, col2 = st.columns(2)
            
            with col1:
                # Daily trend
                daily_trend = create_daily_trend(filtered_df)
                if daily_trend is not None:
                    fig = px.line(
                        daily_trend, 
                        x='Date', 
                        y=['Generator Fuel', 'Vehicle Fuel', 'Total Fuel'],
                        title=f'Daily Fuel Trend - {station} Station',
                        markers=True
                    )
                    fig.update_layout(legend_title_text='Fuel Type')
                    st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Fuel type breakdown
                fuel_breakdown = pd.DataFrame({
                    'Type': ['Generator', 'Vehicle'],
                    'Total': [
                        filtered_df['generator_fuel'].sum(),
                        filtered_df['vehicle_fuel'].sum()
                    ]
                })
                fig = px.pie(
                    fuel_breakdown, 
                    values='Total', 
                    names='Type',
                    title='Fuel Type Distribution',
                    hole=0.3
                )
                st.plotly_chart(fig, use_container_width=True)
            
            # Provider analysis
            if not filtered_df.empty and filtered_df['provider_name'].notna().any():
                st.subheader("Fuel Providers")
                provider_summary = filtered_df.groupby('provider_name')['total_fuel'].sum().sort_values(ascending=False)
                if not provider_summary.empty:
                    fig = px.bar(
                        x=provider_summary.values,
                        y=provider_summary.index,
                        orientation='h',
                        title='Fuel Distribution by Provider',
                        text=provider_summary.values
                    )
                    fig.update_traces(texttemplate='%{text:.1f}L', textposition='outside')
                    fig.update_layout(xaxis_title='Total Fuel (L)')
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📊 Charts require plotly library. Install with: pip install plotly")

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
    st.sidebar.caption("© 2024 Fuel Management System")
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
