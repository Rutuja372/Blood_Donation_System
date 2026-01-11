from flask import Flask, render_template, request, redirect, url_for, session, flash, g
# Try to load flask_mysqldb dynamically (avoids static analyzer unresolved-import errors);
# if not available, fall back to a PyMySQL-based compatibility wrapper.
import importlib
import importlib.util     




_flask_mysqldb_spec = importlib.util.find_spec('flask_mysqldb')
if _flask_mysqldb_spec is not None:
    _flask_mysqldb = importlib.import_module('flask_mysqldb')
    MySQL = _flask_mysqldb.MySQL
else:
    # Fallback: provide a lightweight compatibility wrapper using PyMySQL
    # This allows the rest of the code to use mysql.connection and conn.cursor() as expected.
    import pymysql
    import pymysql.cursors

    class MySQL:
        def __init__(self, app=None):
            if app:
                self.init_app(app)

        def init_app(self, app):
            self.app = app

        @property
        def connection(self):
            cfg = getattr(self, 'app', None).config if getattr(self, 'app', None) else {}
            conn = pymysql.connect(
                host=cfg.get('MYSQL_HOST', '127.0.0.1'),
                user=cfg.get('MYSQL_USER', None),
                password=cfg.get('MYSQL_PASSWORD', None),
                db=cfg.get('MYSQL_DB', None),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=cfg.get('MYSQL_AUTOCOMMIT', False)
            )
            return conn

from datetime import datetime, timedelta
from functools import wraps

# --- Configuration ---
app = Flask(__name__)
# IMPORTANT: Use a complex key in production!
app.config['SECRET_KEY'] = 'a_very_secure_secret_for_flask_sessions' 

# MySQL Database Configuration (!!! REPLACE WITH YOUR CREDENTIALS !!!)
app.config['MYSQL_HOST'] = '127.0.0.1' 
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '2468@Sneha' 
app.config['MYSQL_DB'] = 'blood_donation_db' 
app.config['MYSQL_CURSORCLASS'] = 'DictCursor' 

app.config['MYSQL_AUTOCOMMIT'] = False 

mysql = MySQL(app)

# --- Decorators and Utility Functions ---

def login_required(role):
    """A decorator to restrict access to certain roles."""
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not g.user or g.role != role:
                flash(f"Access Denied. Please log in as a {role.capitalize()}.", 'danger')
                return redirect(url_for(role + '_page', view='login'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def get_db_cursor():
    """Initializes and returns a database cursor, handling connection errors."""
    if 'cursor' not in g:
        try:
            g.conn = mysql.connection
            g.cursor = g.conn.cursor()
        except Exception as e:
            flash(f"Database connection failed. Check your MySQL settings. Error: {e}", 'danger')
            return None
    return g.cursor

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    g.pop('cursor', None)
    g.pop('conn', None)

def update_blood_stock(blood_group, units_change, cursor, conn):
    """Adds/removes units from BloodStock table."""
    try:
        # Check if the BloodGroup exists
        cursor.execute("SELECT BloodGroup FROM BloodStock WHERE BloodGroup = %s", [blood_group])
        if cursor.fetchone() is None:
            # If group doesn't exist, insert it (shouldn't happen with the provided schema)
            cursor.execute("INSERT INTO BloodStock (BloodGroup, AvailableUnits) VALUES (%s, %s)", (blood_group, units_change))
            return True
            
        cursor.execute("UPDATE BloodStock SET AvailableUnits = AvailableUnits + %s WHERE BloodGroup = %s", (units_change, blood_group))
        return True
    except Exception as e:
        flash(f"Stock update failed: {e}", 'danger')
        return False

def check_donor_eligibility(donor_data):
    """Implements the eligibility logic (age, weight, last donation, medical)."""
    age = donor_data.get('Age')
    weight = donor_data.get('Weight')
    last_donation_date = donor_data.get('LastDonationDate')
    chronic_diseases = donor_data.get('ChronicDiseases', 'None')
    
    # 1. Age check
    try:
        age = int(age)
        if not (18 <= age <= 65):
            return False, "Age must be between 18 and 65."
    except:
        return False, "Invalid age provided."
    
    # 2. Weight check
    try:
        weight = float(weight)
        if weight < 50:
            return False, "Weight must be over 50 kg."
    except:
        # If weight is None/missing in DB, allow them to proceed to fill the form.
        if weight is None or weight == 0:
            return True, "Eligible to donate, but please update weight/details."
        return False, "Invalid weight provided."

    # 3. Last Donation Date check (90 days wait)
    if last_donation_date:
        try:
            last_date = last_donation_date # Assumes it's a date object from DB query
            if isinstance(last_donation_date, str):
                 last_date = datetime.strptime(last_donation_date, '%Y-%m-%d').date()
            elif isinstance(last_donation_date, datetime):
                last_date = last_donation_date.date()
            
            today = datetime.now().date()
            if today < (last_date + timedelta(days=90)):
                wait_days = 90 - (today - last_date).days
                return False, f"Must wait {wait_days} more days since last donation."
        except Exception:
            # If the date format is wrong, we treat it as ineligible for safety
            return False, "Error processing last donation date format."

    # 4. Chronic Diseases (simplified check)
    if chronic_diseases and str(chronic_diseases).lower() not in ['none', 'n/a', '']:
        return False, "Medical condition recorded. Please consult a doctor."

    return True, "Eligible to donate."

# --- Before Request Middleware ---
@app.before_request
def load_logged_in_user():
    """Load user data into Flask's global context (g)."""
    g.user = None
    g.role = session.get('user_role')
    user_id = session.get('user_id')

    if user_id and g.role:
        cursor = get_db_cursor()
        if cursor is None: return 

        table = g.role.capitalize()
        
        # Adjust table name for AdminLogin
        if g.role == 'admin':
            table = 'AdminLogin'
            cursor.execute(f"SELECT * FROM {table} WHERE AdminID = %s", [user_id])
        else:
            # Note: We use string formatting here for table name as it's not user input
            cursor.execute(f"SELECT * FROM {table} WHERE {table}ID = %s", [user_id])
        
        g.user = cursor.fetchone()

# --- 1. Homepage Route ---
@app.route('/')
def homepage():
    """Entry point: shows roles and blood stock summary."""
    cursor = get_db_cursor()
    if cursor is None: 
        return render_template('homepage.html', stock_levels=[], db_error=True)
    
    try:
        cursor.execute("SELECT BloodGroup, AvailableUnits FROM BloodStock")
        stock_levels = cursor.fetchall()
    except Exception:
        flash("Database query failed. Please ensure the MySQL server is running.", 'danger')
        stock_levels = []
        
    return render_template('homepage.html', stock_levels=stock_levels, db_error=False)

# --- 2. Donor Workflow ---
@app.route('/donor', methods=['GET', 'POST'])
def donor_page():
    view = request.args.get('view', 'login') 
    cursor = get_db_cursor()
    if cursor is None: return redirect(url_for('homepage'))
    conn = g.conn
    today = datetime.now().date().strftime('%Y-%m-%d')

    if g.user and g.role == 'donor':
        # LOGGED IN: Dashboard & Donation Submission Logic
        
        # POST: Donation Recording and Profile Update
        if request.method == 'POST' and 'donation_form' in request.form:
            try:
                # 1. Gather & Check Eligibility based on new/updated form data
                updated_age = request.form['age']
                updated_weight = request.form['weight']
                updated_gender = request.form['gender']
                updated_blood_group = request.form['blood_group']
                updated_contact = request.form['contact']
                updated_address = request.form['address']
                updated_diseases = request.form.get('diseases', 'None')
                
                current_eligibility_check = {
                    'Age': updated_age,
                    'Weight': updated_weight,
                    'LastDonationDate': g.user.get('LastDonationDate'),
                    'ChronicDiseases': updated_diseases
                }
                is_eligible, eligibility_reason = check_donor_eligibility(current_eligibility_check)
                
                if not is_eligible:
                    flash(f'Donation failed. You are currently ineligible: {eligibility_reason}', 'danger')
                    return redirect(url_for('donor_page', view='dashboard'))

                # 2. Update Donor Profile (with placeholder 'Password' and the new health details)
                # Assumes Donor table has Password, Weight, ChronicDiseases, ContactNumber, Address
                cursor.execute("""
                    UPDATE Donor 
                    SET Age = %s, Weight = %s, Gender = %s, BloodGroup = %s, ChronicDiseases = %s, ContactNumber = %s, Address = %s
                    WHERE DonorID = %s
                """, (updated_age, updated_weight, updated_gender, updated_blood_group, updated_diseases, updated_contact, updated_address, g.user['DonorID']))

                # 3. Record Donation
                date_str = request.form['date']
                units = int(request.form['units'])
                hospital = request.form['hospital']

                cursor.execute("INSERT INTO Donation (DonorID, DonationDate, UnitsDonated, DonationCenter) VALUES (%s, %s, %s, %s)", 
                                 (g.user['DonorID'], date_str, units, hospital))
                
                # 4. Update Donor's LastDonationDate
                cursor.execute("UPDATE Donor SET LastDonationDate = %s WHERE DonorID = %s", (date_str, g.user['DonorID']))
                
                # 5. Update Blood Stock
                if not update_blood_stock(updated_blood_group, units, cursor, conn):
                    raise Exception("Failed to update blood stock.")

                conn.commit()
                flash('Donation recorded and stock updated! Thank you.', 'success')
                return redirect(url_for('donor_page', view='dashboard'))
            except Exception as e:
                conn.rollback()
                flash(f'Error recording donation: {e}', 'danger')
                return redirect(url_for('donor_page', view='dashboard'))
        
        # GET: Dashboard View
        donor = g.user
        
        # Recalculate eligibility with the currently loaded data for the display
        donor_data_for_display = {
            **donor, 
            'Weight': donor.get('Weight') or 70, 
            'ChronicDiseases': donor.get('ChronicDiseases') or 'None'
        }
        eligible_for_display, reason_for_display = check_donor_eligibility(donor_data_for_display)

        # Fetch History
        cursor.execute("SELECT DonationDate, UnitsDonated, DonationCenter FROM Donation WHERE DonorID = %s ORDER BY DonationDate DESC", [donor['DonorID']])
        donation_history = cursor.fetchall()
        
        return render_template('donor_page.html', view='dashboard', donor=donor, today=today, eligibility_status=f"Status: {'Eligible' if eligible_for_display else 'Ineligible'}. Reason: {reason_for_display}", donation_history=donation_history)

    # --- Login/Register Logic ---
    if request.method == 'POST':
        conn = g.conn
        try:
            email = request.form['email']
            password = request.form['password'] # Must match HTML form input name
            
            # 1. Attempt Login
            cursor.execute("SELECT * FROM Donor WHERE Email = %s AND Password = %s", [email, password])
            donor = cursor.fetchone()

            if donor:
                # SUCCESS: Existing user found and logged in
                session['user_id'] = donor['DonorID']
                session['user_role'] = 'donor'
                flash('Login successful! Welcome back.', 'success')
                return redirect(url_for('donor_page', view='dashboard'))

            # 2. If Login failed, check if email is registered (for feedback)
            cursor.execute("SELECT DonorID FROM Donor WHERE Email = %s", [email])
            existing_email_record = cursor.fetchone()

            if existing_email_record:
                # Email found, but password was wrong.
                flash('Invalid Password for the registered email. Please try again.', 'danger')
                return redirect(url_for('donor_page', view='login'))

            # 3. Automatic Registration (Email not found in DB)
            if view == 'login' or view == 'register':
                # Provide default required data for instant registration
                name = request.form.get('name') or email.split('@')[0].capitalize()
                
                # Assumes Donor table has Password, Weight, ChronicDiseases columns
                cursor.execute("""
                    INSERT INTO Donor (Name, Age, Gender, BloodGroup, ContactNumber, Email, Address, Password, Weight, LastDonationDate, ChronicDiseases)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    name, 25, 'Other', 'O+', 'N/A', email, 'Unknown', password, 70, None, 'None'
                ))
                
                conn.commit()
                
                # Fetch the newly created user ID
                cursor.execute("SELECT DonorID FROM Donor WHERE Email = %s", [email])
                new_donor = cursor.fetchone()
                
                session['user_id'] = new_donor['DonorID']
                session['user_role'] = 'donor'
                
                flash('Account created automatically! Please fill in all details during your first donation.', 'success')
                return redirect(url_for('donor_page', view='dashboard'))

        except Exception as e:
            conn.rollback()
            flash(f'An error occurred during login/registration: {e}', 'danger')
            return redirect(url_for('donor_page', view='login'))

    # GET: Login/Register Forms
    return render_template('donor_page.html', view=view)

# --- 3. Recipient Workflow ---
@app.route('/recipient', methods=['GET', 'POST'])
def recipient_page():
    view = request.args.get('view', 'login') 
    cursor = get_db_cursor()
    if cursor is None: return redirect(url_for('homepage'))
    conn = g.conn
    
    if g.user and g.role == 'recipient':
        # LOGGED IN: Dashboard & Request Submission Logic
        # ... (Dashboard logic remains unchanged)
        recipient = g.user
        
        # POST: Blood Request Submission
        if request.method == 'POST' and 'request_form' in request.form:
            try:
                # ... (Blood request submission logic remains unchanged)
                blood_group = request.form['blood_group']
                units = int(request.form['units'])
                hospital = request.form['hospital']
                reason = request.form['reason']

                cursor.execute("""
                    INSERT INTO BloodRequest (RecipientID, BloodGroup, RequiredUnits, RequestStatus, Hospital, Reason)
                    VALUES (%s, %s, %s, 'Pending', %s, %s)
                """, (recipient['RecipientID'], blood_group, units, hospital, reason))
                
                conn.commit()
                flash('Blood request submitted successfully and sent to Admin for review!', 'success')
                return redirect(url_for('recipient_page', view='dashboard'))
            except Exception as e:
                conn.rollback()
                flash(f'Error submitting request: {e}', 'danger')
                return redirect(url_for('recipient_page', view='dashboard'))

        # GET: Dashboard View
        # ... (Dashboard view logic remains unchanged)
        cursor.execute("""
            SELECT RequestID, BloodGroup, RequiredUnits, RequestDate, RequestStatus 
            FROM BloodRequest 
            WHERE RecipientID = %s 
            ORDER BY RequestDate DESC
        """, [recipient['RecipientID']])
        request_history = cursor.fetchall()
        
        # Fetch current stock for reference
        cursor.execute("SELECT BloodGroup, AvailableUnits FROM BloodStock")
        blood_stock = cursor.fetchall()

        return render_template('recipient_page.html', view='dashboard', recipient=recipient, request_history=request_history, blood_stock=blood_stock)

    # --- Login/Register Logic (MODIFIED) ---
    if request.method == 'POST':
        try:
            # The initial credentials submitted by the user
            initial_email = request.form.get('email')
            initial_password = request.form.get('password')
            
            # 1. Registration Submission (Happens when view='register' and the full form is posted)
            if view == 'register':
                # Full Registration details from the form
                name = request.form['name']
                age = request.form['age']
                gender = request.form['gender']
                blood_group = request.form['blood_group_needed']
                contact = request.form['contact']
                address = request.form['address']
                
                # Retrieve the original login credentials from the hidden fields/URL parameters
                # In this implementation, we will use the URL parameters to get the credentials
                # The HTML modification below ensures these are passed in the POST request (via hidden fields)
                registration_email = request.form['registration_email']
                registration_password = request.form['registration_password']
                
                # Insert new recipient
                cursor.execute("""
                    INSERT INTO Recipient (Name, Age, Gender, BloodGroup, ContactNumber, Email, Address, Password)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (name, age, gender, blood_group, contact, registration_email, address, registration_password))
                
                conn.commit()
                
                # Fetch the newly created user ID
                cursor.execute("SELECT RecipientID FROM Recipient WHERE Email = %s", [registration_email])
                new_recipient = cursor.fetchone()
                
                session['user_id'] = new_recipient['RecipientID']
                session['user_role'] = 'recipient'
                flash('Registration successful! You are now logged in.', 'success')
                return redirect(url_for('recipient_page', view='dashboard'))
            
            # 2. Attempt Login (Happens when view='login' is posted)

            # 1. Attempt Login with full credentials
            cursor.execute("SELECT * FROM Recipient WHERE Email = %s AND Password = %s", [initial_email, initial_password])
            recipient = cursor.fetchone()

            if recipient:
                # Login successful
                session['user_id'] = recipient['RecipientID']
                session['user_role'] = 'recipient'
                flash('Login successful! You can now make a blood request.', 'success')
                return redirect(url_for('recipient_page', view='dashboard'))
            
            # 2. Login Failed: Check if user exists by email only
            cursor.execute("SELECT RecipientID FROM Recipient WHERE Email = %s", [initial_email])
            existing_user = cursor.fetchone()

            if existing_user:
                # User exists, but password was wrong
                flash('Invalid Password for existing account. Please try again.', 'danger')
                return redirect(url_for('recipient_page', view='login', email=initial_email))
            else:
                # User does not exist, redirect to registration page
                flash('Account not found. Please complete your registration.', 'info')
                # Pass the email and password to pre-fill or use in the registration form
                return redirect(url_for('recipient_page', view='register', email=initial_email, password=initial_password))

        except Exception as e:
            conn.rollback()
            flash(f'An error occurred: {e}', 'danger')
            return redirect(url_for('recipient_page', view='login'))

    # GET: Login/Register Forms
    # We pass the parameters to the template for pre-filling/hidden fields
    return render_template('recipient_page.html', view=view, email=request.args.get('email', ''), password=request.args.get('password', ''))


# --- 4. Admin Workflow ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_page():
    # Always default view to 'login' for URL/GET requests
    view = request.args.get('view', 'login') 
    cursor = get_db_cursor()
    if cursor is None: return redirect(url_for('homepage'))
    conn = g.conn

    # 1. Check for Authentication
    if not g.user or g.role != 'admin':
        # If unauthenticated, handle only the POST login attempt
        if request.method == 'POST':
            # Check if the required login fields are present
            if 'username' in request.form and 'password' in request.form:
                username = request.form['username']
                password = request.form['password']
                
                cursor.execute("SELECT AdminID FROM AdminLogin WHERE Username = %s AND Password = %s", (username, password))
                admin = cursor.fetchone()

                if admin:
                    session['user_id'] = admin['AdminID']
                    session['user_role'] = 'admin'
                    flash('Admin login successful!', 'success')
                    # Redirect after successful login
                    return redirect(url_for('admin_page', view='dashboard')) 
                else:
                    # Handle auto-creation/login failure for new/invalid user
                    cursor.execute("SELECT AdminID FROM AdminLogin WHERE Username = %s", [username])
                    if cursor.fetchone():
                        flash('Invalid Password', 'danger')
                    else:
                        try:
                            # Auto-create Admin (simple registration)
                            cursor.execute("INSERT INTO AdminLogin (Username, Password) VALUES (%s, %s)", (username, password))
                            conn.commit()
                            cursor.execute("SELECT AdminID FROM AdminLogin WHERE Username = %s", [username])
                            new_admin = cursor.fetchone()
                            session['user_id'] = new_admin['AdminID']
                            session['user_role'] = 'admin'
                            flash('New Admin record created and logged in!', 'success')
                            return redirect(url_for('admin_page', view='dashboard'))
                        except Exception as e:
                            conn.rollback()
                            flash(f"Error creating admin: {e}", 'danger')
                            
            else:
                # This catches POST requests from the dashboard (like Reject) 
                # when the user session has expired. Prevents the KeyError.
                flash('Session expired or access denied. Please log in.', 'danger')
        
        # Render login page if unauthenticated (GET or failed POST)
        return render_template('admin_page.html', view='login')


    # 2. Authenticated Admin Dashboard Logic
    # We are now guaranteed g.user and g.role == 'admin'
    view = 'dashboard'
        
    # --- POST: Admin Action Handlers (Request Management) ---
    if request.method == 'POST':
        try:
            # 1. Request Management
            if 'request_action' in request.form:
                req_id = request.form['request_id']
                action = request.form['request_action']
                
                # CRITICAL FIX: Convert ID to integer immediately for safer use in queries
                req_id_int = int(req_id)
                
                if action == 'Approve':
                    # Use req_id_int for query parameter
                    cursor.execute("SELECT RequiredUnits, BloodGroup, RequestStatus FROM BloodRequest WHERE RequestID = %s", [req_id_int])
                    request_details = cursor.fetchone()
                    
                    if request_details and request_details['RequestStatus'] == 'Pending':
                        units_needed = request_details['RequiredUnits']
                        blood_group = request_details['BloodGroup']
                        
                        # Deduct stock upon approval (THIS IS THE DEDUCTION LOGIC)
                        if update_blood_stock(blood_group, -units_needed, cursor, conn):
                            # Use list for query parameters: [status, id]
                            cursor.execute("UPDATE BloodRequest SET RequestStatus = %s WHERE RequestID = %s", ['Approved', req_id_int])
                            flash(f'Request {req_id} Approved. {units_needed}mL of {blood_group} deducted from stock (Reserved).', 'success')
                        else:
                            flash(f'Approval failed: Insufficient stock of {blood_group} ({units_needed}mL needed).', 'danger')
                    else:
                        flash('Only Pending requests can be Approved.', 'danger')
                        
                elif action == 'Reject':
                     # Rejection logic (no stock change needed)
                     # Use list for query parameters: [status, id]
                    cursor.execute("UPDATE BloodRequest SET RequestStatus = %s WHERE RequestID = %s", ['Rejected', req_id_int])
                    flash(f'Request {req_id} Rejected.', 'info')

                elif action == 'Complete':
                    # Update status to Completed. Stock deduction already occurred at Approval.
                    cursor.execute("SELECT RequestStatus FROM BloodRequest WHERE RequestID = %s", [req_id_int])
                    request_details = cursor.fetchone()
                    
                    if request_details and request_details['RequestStatus'] == 'Approved':
                        # Use list for query parameters: [status, id]
                        cursor.execute("UPDATE BloodRequest SET RequestStatus = %s WHERE RequestID = %s", ['Completed', req_id_int])
                        flash(f'Request {req_id} Completed. Stock was previously reserved upon Approval.', 'success')
                    else:
                        flash('Cannot complete a request that is not Approved.', 'danger')
            
            # THE MANUAL STOCK UPDATE BLOCK WAS REMOVED HERE.
            # Stock management is now ONLY driven by Donor Submissions and Request Approvals.

            conn.commit()
            return redirect(url_for('admin_page', view='dashboard'))

        except Exception as e:
            conn.rollback()
            flash(f'Transaction failed: {e}', 'danger')
            return redirect(url_for('admin_page', view='dashboard'))


    # --- GET: Dashboard Data Fetching ---
    
    # 1. Fetch Blood Stock
    cursor.execute("SELECT BloodGroup, AvailableUnits FROM BloodStock")
    blood_stock = cursor.fetchall()
    
    # 2. Fetch Requests
    cursor.execute("""
        SELECT br.*, r.Name AS RecipientName 
        FROM BloodRequest br JOIN Recipient r ON br.RecipientID = r.RecipientID 
        ORDER BY br.RequestDate DESC
    """)
    all_requests = cursor.fetchall()

    pending_requests = [req for req in all_requests if req['RequestStatus'] == 'Pending']
    approved_requests = [req for req in all_requests if req['RequestStatus'] == 'Approved']
    
    # 3. Fetch Donors and Recipients
    cursor.execute("SELECT DonorID, Name, BloodGroup, Email, LastDonationDate FROM Donor")
    all_donors = cursor.fetchall()
    
    # Calculate eligibility for Admin view
    for donor in all_donors:
        # Need to refetch all details for eligibility check (or assume defaults)
        cursor.execute("SELECT * FROM Donor WHERE DonorID = %s", [donor['DonorID']])
        full_donor_data = cursor.fetchone()
        
        # Ensure required keys exist with defaults for safety in check_donor_eligibility
        donor_data_for_check = {
            **full_donor_data,
            'Weight': full_donor_data.get('Weight') or 70.0, 
            'ChronicDiseases': full_donor_data.get('ChronicDiseases') or 'None',
            'LastDonationDate': full_donor_data.get('LastDonationDate')
        }
        
        eligible, _ = check_donor_eligibility(donor_data_for_check)
        donor['EligibilityStatus'] = 'Eligible' if eligible else 'Ineligible'

    cursor.execute("SELECT RecipientID, Name, BloodGroup, ContactNumber FROM Recipient")
    all_recipients = cursor.fetchall()

    # 4. Reporting Summary
    cursor.execute("SELECT SUM(UnitsDonated) AS total_donations FROM Donation")
    total_donations = cursor.fetchone()['total_donations'] or 0
    
    cursor.execute("SELECT RequestStatus, COUNT(*) as count FROM BloodRequest GROUP BY RequestStatus")
    request_counts_raw = cursor.fetchall()
    request_counts = {item['RequestStatus']: item['count'] for item in request_counts_raw}

    reports = {
        'total_donations': total_donations,
        'total_requests': sum(request_counts.values()),
        'pending_requests': request_counts.get('Pending', 0),
        'approved_requests': request_counts.get('Approved', 0),
        'rejected_requests': request_counts.get('Rejected', 0),
        'completed_requests': request_counts.get('Completed', 0),
    }

    return render_template('admin_page.html', view=view, blood_stock=blood_stock, pending_requests=pending_requests, approved_requests=approved_requests, all_donors=all_donors, all_recipients=all_recipients, reports=reports)

# --- General Logout ---
@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_role', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('homepage'))

if __name__ == '__main__':
    # NOTE: In a production environment, use a proper WSGI server (e.g., Gunicorn)
    # and ensure you replace the default database credentials.
    app.run(debug=True)