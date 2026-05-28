import shutil
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import send_file, url_for
from datetime import datetime
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, session, jsonify, flash
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3
from models.ml_model import predict_risk
from utils.auth import login_required, role_required
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("SECRET_KEY", "blueledger-dev-secret-change-in-production")

app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True


app.config['SESSION_COOKIE_SECURE'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# USERS
users = {
    "manager": {
        "password": "123",
        "role": "manager"
    },
    "accountant": {
        "password": "123",
        "role": "accountant"
    }
}

# EMAIL CONFIG (set in environment for production)
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "support.blueledgerai@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")


def dev_email_enabled():
    """When True, OTP and reset links are shown in the UI/terminal instead of email."""
    if os.environ.get("ALLOW_DEV_OTP", "").lower() == "true":
        return True
    if os.environ.get("ALLOW_DEV_OTP", "").lower() == "false":
        return False
    return not EMAIL_PASSWORD


# EMAIL CONFIG
EMAIL_ADDRESS = "support.blueledgerai@gmail.com"
EMAIL_PASSWORD = "qvwdhzyhlvsieond"


# IN-MEMORY STORES
pending_signups = {}

# HELPER FUNCTIONS
def generate_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=length))

def generate_otp():
    return str(random.randint(100000, 999999))

def send_email(to, subject, body):
    if not EMAIL_PASSWORD:
        raise RuntimeError("EMAIL_PASSWORD is not configured")

    msg = MIMEMultipart()

    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.ehlo()
    server.starttls()
    server.ehlo()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, to, msg.as_string())
    server.quit()
    print("Email sent successfully to", to)


def try_send_email(to, subject, body):
    """Send email, or skip in local dev mode when Gmail is not configured."""
    if dev_email_enabled():
        return False
    send_email(to, subject, body)
    return True

    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))

    print("EMAIL_ADDRESS =", EMAIL_ADDRESS)
    print("EMAIL_PASSWORD =", EMAIL_PASSWORD)

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.set_debuglevel(1)

    server.ehlo()
    server.starttls()
    server.ehlo()

    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)

    server.sendmail(
        EMAIL_ADDRESS,
        to,
        msg.as_string()
    )

    server.quit()

    print("Email sent successfully")


def fix_schema(conn):
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE expenses ADD COLUMN username TEXT")
        conn.commit()
    except:
        pass
    try:
        cur.execute("ALTER TABLE budgets ADD COLUMN username TEXT")
        conn.commit()
    except:
        pass

# DATABASE
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY,
        username TEXT,
        amount REAL,
        category TEXT,
        date TEXT,
        risk_status TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY,
        username TEXT,
        monthly_budget REAL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY,
        action TEXT,
        username TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS registered_users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT UNIQUE,
        role TEXT DEFAULT 'user'
    )
    """)

    try:
        cur.execute("ALTER TABLE expenses ADD COLUMN username TEXT")
    except:
        pass
    try:
        cur.execute("ALTER TABLE budgets ADD COLUMN username TEXT")
    except:
        pass

    conn.commit()
    conn.close()
    seed_default_users()


def seed_default_users():
    """Create demo manager/accountant accounts in the database if missing."""
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    for username, info in users.items():
        cur.execute("SELECT id FROM registered_users WHERE username=?", (username,))
        if cur.fetchone():
            continue
        email = f"{username}@blueledger.local"
        cur.execute(
            """
            INSERT INTO registered_users (username, password, email, role)
            VALUES (?, ?, ?, ?)
            """,
            (username, generate_password_hash(info["password"]), email, info["role"]),
        )
        cur.execute(
            "INSERT INTO budgets (username, monthly_budget) VALUES (?, ?)",
            (username, 0),
        )
    conn.commit()
    conn.close()


def verify_password(stored_password, provided_password):
    if stored_password.startswith("pbkdf2:") or stored_password.startswith("scrypt:"):
        return check_password_hash(stored_password, provided_password)
    return stored_password == provided_password


def provision_new_user(username, role="user"):
    """Each new user gets an isolated, empty financial workspace."""
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT id FROM budgets WHERE username=?", (username,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO budgets (username, monthly_budget) VALUES (?, ?)",
            (username, 0),
        )
    cur.execute(
        "INSERT INTO logs (action, username) VALUES (?, ?)",
        ("Account provisioned — fresh dashboard", username),
    )
    conn.commit()
    conn.close()


def parse_login_credentials():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get("username", "").strip(), data.get("password", "").strip(), True
    return request.form.get("username", "").strip(), request.form.get("password", "").strip(), False


def authenticate_user(username, password):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        """
        SELECT username, password, role
        FROM registered_users
        WHERE username=? OR email=?
        """,
        (username, username),
    )
    user = cur.fetchone()
    conn.close()
    if not user:
        demo = users.get(username)
        if demo and demo["password"] == password:
            return {"username": username, "role": demo["role"]}, None
        return None, "User not found"
    db_username, db_password, db_role = user
    if not verify_password(db_password, password):
        return None, "Invalid password"
    return {"username": db_username, "role": db_role or "user"}, None


# HOME / LOGIN PAGE
@app.route("/")
@app.route("/login", methods=["GET"])
def index():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("index"))


# LOGIN
@app.route("/l", methods=["POST"])

@app.route("/login", methods=["POST"])
def login():
    username, password, wants_json = parse_login_credentials()
    if not username or not password:
        message = "Username and password are required"
        if wants_json:
            return jsonify({"success": False, "message": message})
        flash(message, "error")
        return redirect(url_for("index"))

    user, error = authenticate_user(username, password)
    if error:
        if wants_json:
            return jsonify({"success": False, "message": error})
        flash(error, "error")
        return redirect(url_for("index"))

    session["user"] = user["username"]
    session["role"] = user["role"]

    if wants_json:
        return jsonify({"success": True, "redirect": url_for("dashboard")})
    return redirect(url_for("dashboard"))

def login():

    data = request.get_json()

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        """
        SELECT username, password, role
        FROM registered_users
        WHERE username=? OR email=?
        """,
        (username, username)
    )

    user = cur.fetchone()

    conn.close()

    if not user:
        return jsonify({
            "success": False,
            "message": "User not found"
        })

    db_username = user[0]
    db_password = user[1]
    db_role = user[2]

    if password != db_password:
        return jsonify({
            "success": False,
            "message": "Invalid password"
        })

    session["user"] = db_username
    session["role"] = db_role

    return jsonify({
        "success": True,
        "redirect": "/dashboard"
    })


# DASHBOARD
@app.route("/dashboard")
@login_required
def dashboard():

    conn = sqlite3.connect("database.db")
    fix_schema(conn)
    cur = conn.cursor()

    cur.execute("SELECT SUM(amount) FROM expenses WHERE username=?", (session["user"],))
    total_expenses = cur.fetchone()[0]
    if total_expenses is None:
        total_expenses = 0

    cur.execute("SELECT COUNT(*) FROM expenses WHERE username=?", (session["user"],))
    total_transactions = cur.fetchone()[0]

    cur.execute("SELECT monthly_budget FROM budgets WHERE username=? ORDER BY id DESC LIMIT 1", (session["user"],))
    budget = cur.fetchone()
    current_budget = budget[0] if budget else 0

    cur.execute(
        "SELECT COUNT(*) FROM expenses WHERE username=? AND risk_status LIKE ?",
        (session["user"], "%High Risk%"),
    )
    high_risk = cur.fetchone()[0]

    insights = []
    if total_expenses > current_budget:
        insights.append("⚠ Enterprise spending exceeded allocated monthly budget.")
    if high_risk > 0:
        insights.append(f"🚨 {high_risk} high-risk transactions detected by AI engine.")
    if total_transactions > 15:
        insights.append("📈 Financial transaction volume increased significantly this month.")
    if total_expenses < current_budget:
        insights.append("✅ Enterprise expenses are currently under budget control.")
    if high_risk == 0:
        insights.append("🛡 No critical AI anomalies detected in enterprise transactions.")
    if total_expenses > current_budget * 0.9:
        insights.append("📉 Enterprise budget is nearing critical utilization threshold.")
    if total_transactions > 20:
        insights.append("📊 AI forecasting engine predicts increased operational financial activity.")
    if high_risk >= 3:
        insights.append("🚨 Multiple high-risk anomalies indicate potential enterprise financial threats.")
    if total_expenses < current_budget * 0.5:
        insights.append("💰 Enterprise financial reserves are currently in healthy condition.")

    conn.close()

    return render_template(
        "dashboard.html",
        total_expenses=total_expenses,
        total_transactions=total_transactions,
        current_budget=current_budget,
        high_risk=high_risk,
        insights=insights,
        risk_count=high_risk
    )

# CHART PAGE
@app.route("/chart")
@login_required
def chart():
    return render_template("chart.html")

# AI RISK PAGE
@app.route("/ai-risk")
@login_required
def ai_risk():
    conn = sqlite3.connect("database.db")
    fix_schema(conn)
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM expenses WHERE username=? AND risk_status LIKE ?",
        (session["user"], "%High Risk%"),
    )
    risks = cur.fetchall()
    conn.close()
    return render_template("ai_risk.html", risks=risks)

# REPORT PAGE
@app.route("/report")
@login_required
def report():
    return send_file("expense_report.pdf", as_attachment=True)

# EXPENSES
@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    conn = sqlite3.connect("database.db")
    fix_schema(conn)
    cur = conn.cursor()
    risk_status = None

    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            category = request.form["category"]
            date = request.form["date"]
            risk_status = predict_risk(amount)
            cur.execute(
                "INSERT INTO expenses (username, amount, category, date, risk_status) VALUES (?, ?, ?, ?, ?)",
                (session["user"], amount, category, date, risk_status)
            )
            conn.commit()
            cur.execute("INSERT INTO logs (action, username) VALUES (?, ?)", ("Added Expense", session["user"]))
            conn.commit()
        except Exception as e:
            print("ERROR:", e)
            risk_status = "⚠ System Error Occurred"

    cur.execute("SELECT * FROM expenses WHERE username=?", (session["user"],))
    data = cur.fetchall()
    conn.close()
    return render_template("expenses.html", data=data, risk_status=risk_status)

# BUDGET
@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    conn = sqlite3.connect("database.db")
    fix_schema(conn)
    cur = conn.cursor()

    if request.method == "POST":
        monthly_budget = request.form["monthly_budget"]
        cur.execute("INSERT INTO budgets (username, monthly_budget) VALUES (?, ?)", (session["user"], monthly_budget))
        conn.commit()

    cur.execute("SELECT * FROM budgets WHERE username=? ORDER BY id DESC LIMIT 1", (session["user"],))
    budget_data = cur.fetchone()

    cur.execute("SELECT SUM(amount) FROM expenses WHERE username=?", (session["user"],))
    total_expenses = cur.fetchone()[0]
    if total_expenses is None:
        total_expenses = 0

    conn.close()
    return render_template("budget.html", budget_data=budget_data, total_expenses=total_expenses)

# LOGS
@app.route("/logs")
@login_required
@role_required("manager")
def logs():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT * FROM logs ORDER BY id DESC")
    logs = cur.fetchall()
    conn.close()
    return render_template("logs.html", logs=logs)

# ANALYTICS
@app.route("/analytics")
@login_required
def analytics():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT category, SUM(amount) FROM expenses WHERE username=? GROUP BY category",
        (session["user"],),
    )
    data = cur.fetchall()
    categories = []
    amounts = []
    for row in data:
        categories.append(row[0])
        amounts.append(row[1])
    plt.figure(figsize=(8, 5))
    plt.bar(categories, amounts)
    plt.title("Enterprise Expense Analytics")
    plt.xlabel("Category")
    plt.ylabel("Amount")
    plt.tight_layout()
    plt.savefig("static/chart.png")
    conn.close()
    return render_template("analytics.html")

# BACKUPS
@app.route("/backups")
@login_required
@role_required("manager")
def backups():
    backup_folder = "backups"
    files = os.listdir(backup_folder)
    files.reverse()
    return render_template("backups.html", files=files)

@app.errorhandler(404)
def not_found(_error):
    if "user" in session:
        return render_template("error.html", error="Page not found"), 404
    return redirect(url_for("index"))


# GLOBAL ERROR HANDLER
@app.errorhandler(Exception)
def handle_error(error):
    print("System Error:", error)
    if request.path.startswith('/auth/'):
        return jsonify({"success": False, "message": str(error)}), 500
    return render_template("error.html", error=error)

# DATABASE BACKUP
def backup_database():
    if os.path.exists("database.db"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backups/database_backup_{timestamp}.db"
        shutil.copy("database.db", backup_file)
        print("✅ Database backup created:", backup_file)

# SIGNUP ROUTES
@app.route("/auth/signup-step1", methods=["POST"])
def signup_step1():

    data = request.get_json()

    email = data.get("email")
    password = data.get("password")

    otp = generate_otp()

    session["signup_email"] = email
    session["signup_password"] = password
    session["signup_otp"] = otp

    body = f"""
    <p>Hello,</p>
    <p>Your BlueLedger verification OTP is:</p>
    <h2 style="letter-spacing:8px; color:#1565c0">{otp}</h2>
    <p>This OTP is valid for one-time use only.</p>
    <p>— BlueLedger AI Security Team</p>
    """

    try:
        if try_send_email(email, "BlueLedger — Verify Your Email", body):
            return jsonify({
                "success": True,
                "message": "OTP sent to your email."
            })
    except Exception as e:
        print("Signup Email Error:", e)

    if dev_email_enabled():
        print(f"\n========== SIGNUP OTP (local dev) ==========")
        print(f"Email: {email}")
        print(f"OTP:   {otp}")
        print(f"==========================================\n")

        return jsonify({
            "success": True,
            "dev_otp": otp,
            "message": "Local mode active."
        })

    return jsonify({
        "success": False,
        "message": "Failed to send OTP email."
    })


@app.route("/auth/signup-step2", methods=["POST"])
def signup_step2():
    data = request.get_json()
    entered_otp = data.get("otp")

    saved_otp = session.get("signup_otp")

    if not saved_otp:
        return jsonify({
            "success": False,
            "message": "Session expired. Please start again."
        })

    if entered_otp != saved_otp:
        return jsonify({
            "success": False,
            "message": "Invalid OTP"
        })

    email = session.get("signup_email")

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT id FROM registered_users WHERE email=?", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({
            "success": False,
            "message": "Email already registered"
        })
    conn.close()

    return jsonify({"success": True})

@app.route("/auth/signup-step3", methods=["POST"])
def signup_step3():
    data = request.get_json()
    username = data.get("username")
    role = data.get("role", "user")
    email = session.get("signup_email")
    password = session.get("signup_password")

    if not email or not password:
        return jsonify({"success": False, "message": "Session expired. Please start again."})

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT id FROM registered_users WHERE email=?", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Email already registered"})

    cur.execute("SELECT id FROM registered_users WHERE username=?", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Username already taken"})

    hashed = generate_password_hash(password)
    cur.execute(
        "INSERT INTO registered_users (username, password, email, role) VALUES (?, ?, ?, ?)",
        (username, hashed, email, role)
    )
    conn.commit()
    conn.close()

    provision_new_user(username, role)

    session.pop("signup_email", None)
    session.pop("signup_password", None)
    session.pop("signup_otp", None)

    return jsonify({"success": True})

@app.route("/auth/change-password", methods=["POST"])
def change_password():
    data = request.get_json()
    username = data.get("username", "").strip()
    current_password = data.get("current_password", "").strip()
    new_password = data.get("new_password", "").strip()

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT password FROM registered_users WHERE username=?", (username,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Username not found."})

    if not verify_password(user[0], current_password):
        conn.close()
        return jsonify({"success": False, "message": "Current password is incorrect."})

    cur.execute(
        "UPDATE registered_users SET password=? WHERE username=?",
        (generate_password_hash(new_password), username)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# FORGOT PASSWORD ROUTES
@app.route("/auth/forgot-password", methods=["POST"])
def forgot_password():

    data = request.get_json()

    email = data.get("email", "").strip().lower()

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute(
        "SELECT username FROM registered_users WHERE LOWER(email)=?",
        (email,)
    )

    db_user = cur.fetchone()

    conn.close()

    if not db_user:
        return jsonify({
            "success": False,
            "message": "No account found with that email."
        })

    token = generate_password(32)

    pending_signups["reset_" + token] = {
        "username": db_user[0],
        "email": email
    }

    reset_link = f"{request.url_root.rstrip('/')}/reset-password?token={token}"

    body = f"""
    <p>Hello,</p>
    <p>Click below to reset your password:</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    """

    try:
        try_send_email(
            email,
            "BlueLedger — Reset Password",
            body
        )
    except Exception as e:
        print("Forgot Password Email Error:", e)

    return jsonify({
        "success": True,
        "message": "Password reset link sent."
    })


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    token = request.args.get("token") or request.form.get("token")

    record = pending_signups.get("reset_" + token)

    if not record:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":

        new_password = request.form.get("new_password")

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()

        cur.execute(
            """
            UPDATE registered_users
            SET password=?
            WHERE username=?
            """,
            (
                generate_password_hash(new_password),
                record["username"]
            )
        )

        conn.commit()
        conn.close()

        del pending_signups["reset_" + token]

        flash("Password updated successfully.", "success")

        return redirect(url_for("index"))

    return render_template(
        "login.html",
        show_reset=True,
        reset_token=token
    )


# CHAT ROUTE
@app.route("/chat", methods=["POST"])
@login_required
def chat():

    try:

        data = request.get_json()

        messages = data.get("messages", [])

        user_msg = messages[-1]["content"].lower() if messages else ""

        if "risk" in user_msg:
            reply = "AI Risk Alerts are generated using Isolation Forest anomaly detection."

        elif "budget" in user_msg:
            reply = "Budget Planning helps track monthly spending limits."

        elif "expense" in user_msg:
            reply = "Expenses are analyzed automatically by the AI engine."

        elif "report" in user_msg:
            reply = "Reports can be downloaded from the Reports module."

        elif "analytics" in user_msg or "chart" in user_msg:
            reply = "Analytics provides category-wise spending insights."

        else:
            reply = "Hello! I am your BlueLedger AI Assistant."

        return jsonify({
            "reply": reply
        })

    except Exception as e:

        print("CHAT ROUTE ERROR:", str(e))

        return jsonify({
            "reply": "Something went wrong."
        })


# Initialize database
with app.app_context():
    init_db()


if __name__ == "__main__":

    init_db()

    backup_database()

    app.run(debug=True)

