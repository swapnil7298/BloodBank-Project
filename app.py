# app.py - Place this in the root of your 'blood_bank_project' folder.

from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector
from datetime import datetime

# Initialize the Flask application
app = Flask(__name__)
# A secret key is required for session management
app.secret_key = 'a_very_secret_key_that_should_be_changed'

# --- Database Connection ---
def get_db():
    """
    Establishes a connection to the MySQL database.
    
    IMPORTANT: Replace 'your_mysql_password' with your actual MySQL root password.
    """
    try:
        db = mysql.connector.connect(
            host="localhost",
            user="root",
            password="", # <-- IMPORTANT: CHANGE THIS TO YOUR PASSWORD
            database="bloody_bank"
        )
        return db
    except mysql.connector.Error as err:
        # Handle connection errors gracefully
        flash(f"Database connection error: {err}", "danger")
        return None

# --- Main Public Routes ---
@app.route('/')
def index():
    """Renders the home page."""
    return render_template('index.html')

@app.route('/donor', methods=['GET', 'POST'])
def donor():
    """Handles donor registration."""
    if request.method == 'POST':
        db = get_db()
        if not db: return redirect(url_for('index'))
        
        try:
            cur = db.cursor()
            
            # Generate a new donor ID safely
            cur.execute("SELECT COALESCE(MAX(donor_id), 1000) + 1 FROM donor")
            donor_id = cur.fetchone()[0]
            
            # Insert new donor record
            sql = """
                INSERT INTO donor (donor_id, donor_name, donor_age, donor_contact, donor_address, donor_blood_grp, donor_last_date, donor_med_his)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            last_donation = request.form['last_donation'] if request.form['last_donation'] else None
            values = (
                donor_id,
                request.form['name'],
                int(request.form['age']),
                request.form['contact'],
                request.form['address'],
                request.form['blood_group'],
                last_donation,
                request.form['health_status']
            )
            cur.execute(sql, values)
            db.commit()
            flash('Thank you for registering as a donor!', 'success')
            
        except Exception as e:
            db.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
        finally:
            cur.close()
            db.close()
            
        return redirect(url_for('donor'))

    return render_template('donor.html')

@app.route('/recipient', methods=['GET', 'POST'])
def recipient():
    """Handles blood requests from recipients."""
    if request.method == 'POST':
        db = get_db()
        if not db: return redirect(url_for('index'))
        
        try:
            cur = db.cursor(dictionary=True)
            
            blood_group = request.form['blood_group']
            units_needed = int(request.form['units_needed'])
            
            # Check available stock
            cur.execute("SELECT units_available FROM bloodstock WHERE blood_group = %s", (blood_group,))
            stock = cur.fetchone()
            available_units = stock['units_available'] if stock else 0
            
            if available_units >= units_needed:
                # --- Process the request ---
                db.start_transaction()

                # 1. Generate new recipient ID
                cur.execute("SELECT COALESCE(MAX(recipient_id), 2000) + 1 FROM recipient")
                recipient_id = cur.fetchone()['COALESCE(MAX(recipient_id), 2000) + 1']

                # 2. Insert new recipient
                cur.execute("""
                    INSERT INTO recipient (recipient_id, recipient_name, recipient_age, recipient_contact, recipient_address, recipient_blood_grp, recipient_required_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (recipient_id, request.form['name'], int(request.form['age']), request.form['contact'], request.form['hospital'], blood_group, units_needed))

                # 3. Update blood stock
                cur.execute("UPDATE bloodstock SET units_available = units_available - %s WHERE blood_group = %s", (units_needed, blood_group))

                # 4. Create a blood request record
                cur.execute("SELECT COALESCE(MAX(request_id), 3000) + 1 FROM blood_request")
                request_id = cur.fetchone()['COALESCE(MAX(request_id), 3000) + 1']
                cur.execute("""
                    INSERT INTO blood_request (request_id, recipient_id, blood_group, units_requested, date_requested, request_status)
                    VALUES (%s, %s, %s, %s, %s, 'Approved')
                """, (request_id, recipient_id, blood_group, units_needed, datetime.now().date()))

                # 5. Create a transaction record
                cur.execute("SELECT COALESCE(MAX(transaction_id), 4000) + 1 FROM transaction_record")
                trans_id = cur.fetchone()['COALESCE(MAX(transaction_id), 4000) + 1']
                cur.execute("""
                    INSERT INTO transaction_record (request_id, transaction_id, units_processed, transaction_date)
                    VALUES (%s, %s, %s, %s)
                """, (request_id, trans_id, units_needed, datetime.now().date()))

                db.commit()
                flash(f"Request Approved! {units_needed} units of {blood_group} blood have been allocated.", 'success')
            else:
                flash(f"Request Denied. Only {available_units} units of {blood_group} are available.", 'danger')

        except Exception as e:
            db.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
        finally:
            cur.close()
            db.close()

        return redirect(url_for('recipient'))

    return render_template('recipient.html')

# --- Admin Routes ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Handles admin login."""
    if 'admin_logged_in' in session:
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        db = get_db()
        if not db: return render_template('admin.html')
        
        try:
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT * FROM adminn WHERE username = %s AND password = %s", 
                       (request.form['admin_id'], request.form['password']))
            admin_user = cur.fetchone()
            
            if admin_user:
                session['admin_logged_in'] = True
                session['admin_username'] = admin_user['username']
                flash('Login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                flash("Invalid credentials. Please try again.", 'danger')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
        finally:
            cur.close()
            db.close()

    return render_template('admin.html')

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    """Admin dashboard for executing SQL queries."""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin'))
    
    results = None
    query_text = ""
    if request.method == "POST":
        db = get_db()
        if not db: return redirect(url_for('admin'))
        
        query_text = request.form.get('query', '').strip()
        try:
            cur = db.cursor(dictionary=True)
            cur.execute(query_text)
            
            if query_text.lower().startswith('select'):
                results = cur.fetchall()
                if not results:
                    flash("Query executed successfully, but returned no results.", "warning")
            else:
                db.commit()
                flash(f'Query executed successfully. {cur.rowcount} rows affected.', 'success')
                results = None # No results to display for non-SELECT queries
        except Exception as e:
            db.rollback()
            flash(f'Query Error: {str(e)}', 'danger')
        finally:
            cur.close()
            db.close()
    
    return render_template('admin_dashboard.html', results=results, query_text=query_text)

@app.route('/admin/donors')
def admin_donors():
    """Displays all registered donors."""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin'))
    
    donors = []
    db = get_db()
    if db:
        try:
            cur = db.cursor(dictionary=True)
            cur.execute("SELECT * FROM donor ORDER BY donor_id DESC")
            donors = cur.fetchall()
        except Exception as e:
            flash(f'Error fetching donors: {str(e)}', 'danger')
        finally:
            cur.close()
            db.close()
            
    return render_template('admin_view_donors.html', donors=donors)

@app.route('/admin/donations', methods=['GET', 'POST'])
def admin_donations():
    """Handles recording new donations and viewing donation history."""
    if 'admin_logged_in' not in session:
        return redirect(url_for('admin'))
    
    db = get_db()
    if not db: return redirect(url_for('admin_dashboard'))

    # Handle POST request for adding a new donation
    if request.method == 'POST':
        try:
            cur = db.cursor()
            db.start_transaction()
            
            donor_id = int(request.form['donor_id'])
            blood_group = request.form['blood_group']
            units_donated = int(request.form['units_donated'])
            donation_date = request.form['donation_date']
            
            # Generate a new donation ID
            cur.execute("SELECT COALESCE(MAX(donation_id), 5000) + 1 FROM blood_donation")
            donation_id = cur.fetchone()[0]
            
            # Insert into blood_donation table
            cur.execute("""
                INSERT INTO blood_donation (donation_id, donor_id, blood_group, units_donated, donation_date)
                VALUES (%s, %s, %s, %s, %s)
            """, (donation_id, donor_id, blood_group, units_donated, donation_date))
            
            # Update blood stock
            cur.execute("UPDATE bloodstock SET units_available = units_available + %s WHERE blood_group = %s", (units_donated, blood_group))
            
            db.commit()
            flash('Donation recorded successfully! Stock updated.', 'success')
        except Exception as e:
            db.rollback()
            flash(f'Error recording donation: {str(e)}', 'danger')
        finally:
            db.close()
        return redirect(url_for('admin_donations'))

    # Handle GET request to display the form and history
    donors_list = []
    donations_history = []
    try:
        cur = db.cursor(dictionary=True)
        
        # Get all donors for the dropdown
        cur.execute("SELECT donor_id, donor_name FROM donor ORDER BY donor_name")
        donors_list = cur.fetchall()
        
        # Get donation history
        cur.execute("""
            SELECT bd.donation_id, bd.blood_group, bd.units_donated, bd.donation_date, d.donor_name, d.donor_id
            FROM blood_donation bd
            JOIN donor d ON bd.donor_id = d.donor_id
            ORDER BY bd.donation_date DESC, bd.donation_id DESC
        """)
        donations_history = cur.fetchall()
    except Exception as e:
        flash(f'Error fetching data: {str(e)}', 'danger')
    finally:
        db.close()
        
    return render_template('admin_donations.html', donors=donors_list, donations=donations_history)

@app.route('/admin/logout')
def admin_logout():
    """Logs the admin out."""
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('admin'))

# --- Main execution ---
if __name__ == '__main__':
    app.run(debug=True)
