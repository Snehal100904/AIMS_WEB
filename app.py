from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import mysql.connector
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

# ================= DATABASE =================
def get_db():
    return mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="",
        database="project_db",
        port=3306,
        auth_plugin='mysql_native_password'
    )

# ================= EMAIL =================
def send_email(to_email, subject, body):
    sender_email = "snehalmali149@gmail.com"
    sender_password = "oxwwlqzzjekpahzv"

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = to_email

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print("Email error:", e)

# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM admin WHERE username=%s AND password=%s",
            (username, password)
        )
        admin = cursor.fetchone()

        cursor.close()
        conn.close()

        if admin:
            session['user'] = username
            return redirect(url_for('dashboard'))
        else:
            return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    # ================= COMPONENTS =================
    cursor.execute("SELECT * FROM components")
    components = cursor.fetchall()

    # ================= TRANSACTIONS =================
    cursor.execute("""
        SELECT 
            t.student_name,
            t.admission_no,
            c.name as component_name,
            t.action,
            t.date_time
        FROM transactions t
        JOIN components c ON t.component_id = c.id
        ORDER BY t.date_time DESC
    """)
    transactions = cursor.fetchall()

    # ================= ADDED FIXES (ONLY NEW PART) =================

    # Issued count
    issued_count = len([t for t in transactions if t['action'] == 'issued'])

    # Returned count
    returned_count = len([t for t in transactions if t['action'] == 'returned'])

    # Pending requests count
    cursor.execute("""
        SELECT COUNT(*) as count 
        FROM requests 
        WHERE status IS NULL OR status='Pending'
    """)
    pending_requests = cursor.fetchone()['count']

    cursor.close()
    conn.close()

    return render_template(
        "dashboard.html",
        components=components,
        transactions=transactions,
        issued_count=issued_count,
        returned_count=returned_count,
        pending_requests=pending_requests
    )
# ================= INVENTORY =================
@app.route("/inventory", methods=["GET", "POST"])
def inventory():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form['name']
        quantity = int(request.form['quantity'])
        barcode = request.form['barcode']

        cursor.execute("""
            INSERT INTO components (name, quantity, barcode)
            VALUES (%s,%s,%s)
        """, (name, quantity, barcode))
        conn.commit()

    cursor.execute("SELECT * FROM components")
    components = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("inventory.html", components=components)

# ================= GET COMPONENT =================
@app.route("/get-component/<barcode>")
def get_component(barcode):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT name, quantity FROM components WHERE barcode=%s", (barcode,))
    data = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify(data if data else {"error": "Not found"})

# ================= GET STUDENT =================
@app.route("/get-student/<code>")
def get_student(code):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT name, email, admission_no FROM users WHERE admission_no=%s", (code,))
    data = cursor.fetchone()

    cursor.close()
    conn.close()

    return jsonify(data if data else {"error": "Not found"})

# ================= ISSUE =================
@app.route("/issue/<barcode>", methods=["POST"])
def issue_component(barcode):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    admission_no = request.form.get("admission_no")
    name = request.form.get("student_name")
    email = request.form.get("email")

    cursor.execute("SELECT * FROM components WHERE barcode=%s", (barcode,))
    component = cursor.fetchone()

    if not component or component['quantity'] <= 0:
        return "Out of stock"

    component_name = component['name']
    component_id = component['id']

    cursor.execute("UPDATE components SET quantity = quantity - 1 WHERE barcode=%s", (barcode,))

    cursor.execute("""
        INSERT INTO transactions 
        (component_id, student_name, admission_no, student_email, action, date_time)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, (component_id, name, admission_no, email, "issued", datetime.now()))

    conn.commit()
    cursor.close()
    conn.close()

    send_email(email, "Component Issued",
               f"{component_name} has been issued to you.")

    return redirect(url_for('inventory'))

# ================= RETURN =================
@app.route("/return/<barcode>", methods=["POST"])
def return_component(barcode):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    name = request.form.get("student_name")
    email = request.form.get("email")

    cursor.execute("SELECT * FROM components WHERE barcode=%s", (barcode,))
    component = cursor.fetchone()

    if not component:
        return "Not found"

    component_name = component['name']

    cursor.execute("UPDATE components SET quantity = quantity + 1 WHERE barcode=%s", (barcode,))
    conn.commit()

    cursor.close()
    conn.close()

    # ✅ EMAIL ON RETURN
    send_email(email, "Component Returned",
               f"{component_name} has been returned successfully.")

    return redirect(url_for('inventory'))

# ================= STUDENT PAGE =================
@app.route('/student')
def student_page():
    return render_template('student.html')

# ================= SUBMIT REQUEST =================
@app.route('/submit_request', methods=['POST'])
def submit_request():
    conn = get_db()
    cursor = conn.cursor()

    name = request.form['name']
    email = request.form['email']
    student_class = request.form['class']
    component = request.form['component']
    purpose = request.form['purpose']

    cursor.execute("""
        INSERT INTO requests 
        (student_name, student_email, student_class, component_name, purpose) 
        VALUES (%s, %s, %s, %s, %s)
    """, (name, email, student_class, component, purpose))

    conn.commit()
    cursor.close()
    conn.close()

    return redirect(url_for('student_page'))

# ================= STUDENT REQUEST VIEW =================
@app.route('/my_requests/<email>')
def my_requests(email):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM requests WHERE student_email=%s", (email,))
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("my_requests.html", data=data)

# ================= ADMIN REQUEST =================
@app.route('/admin_requests')
def admin_requests():
    if 'user' not in session:
        return redirect(url_for('login'))

    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM requests")
    data = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('admin_requests.html', data=data)

# ================= APPROVE / REJECT =================
@app.route('/update_request/<int:id>/<status>')
def update_request(id, status):
    conn = get_db()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM requests WHERE id=%s", (id,))
    req = cursor.fetchone()

    cursor.execute("UPDATE requests SET status=%s WHERE id=%s", (status, id))

    # Auto reduce stock
    if status == "Approved":
        cursor.execute("""
            UPDATE components 
            SET quantity = quantity - 1 
            WHERE name=%s
        """, (req['component_name'],))

    conn.commit()
    cursor.close()
    conn.close()

    # Email
    if req:
        send_email(req['student_email'], "Request Update",
                   f"Your request for {req['component_name']} is {status}")

    return redirect(url_for('admin_requests'))

if __name__ == "__main__":
   app.run(host="0.0.0.0", port=5000, debug=True)