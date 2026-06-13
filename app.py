import shutil
import os
import ssl
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import send_file, url_for
from datetime import datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, render_template, request, redirect, session, jsonify, flash
from werkzeug.security import check_password_hash, generate_password_hash
import random
import string
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from invoice_generator import generate_invoice

try:
    import psycopg2
    DATABASE_URL = os.environ.get("DATABASE_URL")
    USE_POSTGRES = bool(DATABASE_URL)
except ImportError:
    USE_POSTGRES = False

import sqlite3
from models.ml_model import predict_risk
from utils.auth import login_required, role_required
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get("SECRET_KEY", "blueledger-dev-secret-change-in-production")
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 1800

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"]
)

# USERS
users = {
    "manager": {"password": "123", "role": "manager"},
    "accountant": {"password": "123", "role": "accountant"}
}

# EMAIL CONFIG
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "support.blueledgerai@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# IN-MEMORY STORES
pending_signups = {}

# ─── DB HELPERS ───────────────────────────────────────────────
def get_db():
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect("database.db")

def p():
    return "%s" if USE_POSTGRES else "?"

# ─── EMAIL ────────────────────────────────────────────────────
def send_email(to, subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to, msg.as_string())
    print("Email sent to", to)

def try_send_email(to, subject, body):
    if not EMAIL_PASSWORD:
        return False
    send_email(to, subject, body)
    return True

# ─── HELPERS ──────────────────────────────────────────────────
def generate_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$"
    return ''.join(random.choices(chars, k=length))

def generate_otp():
    return str(random.randint(100000, 999999))

def verify_password(stored, provided):
    if stored.startswith("pbkdf2:") or stored.startswith("scrypt:"):
        return check_password_hash(stored, provided)
    return stored == provided

def parse_login_credentials():
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get("username", "").strip(), data.get("password", "").strip(), True
    return request.form.get("username", "").strip(), request.form.get("password", "").strip(), False

def authenticate_user(username, password):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        f"SELECT username, password, role FROM registered_users WHERE username={p()} OR email={p()}",
        (username, username),
    )
    user = cur.fetchone()
    conn.close()
    if not user:
        demo = users.get(username)
        if demo and demo["password"] == password:
            return {"username": username, "role": demo["role"]}, None
        return None, "User not found"
    db_username, db_password, db_role = user[0], user[1], user[2]
    if not verify_password(db_password, password):
        return None, "Invalid password"
    return {"username": db_username, "role": db_role or "user"}, None

def provision_new_user(username, role="user"):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM budgets WHERE username={p()}", (username,))
    if not cur.fetchone():
        cur.execute(f"INSERT INTO budgets (username, monthly_budget) VALUES ({p()}, {p()})", (username, 0))
    cur.execute(f"INSERT INTO logs (action, username) VALUES ({p()}, {p()})", ("Account provisioned — fresh dashboard", username))
    conn.commit()
    conn.close()

# ─── DATABASE INIT ────────────────────────────────────────────
def init_db():
    os.makedirs("backups", exist_ok=True)
    conn = get_db()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY, username TEXT, amount REAL,
            category TEXT, date TEXT, risk_status TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS budgets (
            id SERIAL PRIMARY KEY, username TEXT, monthly_budget REAL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY, action TEXT, username TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS registered_users (
            id SERIAL PRIMARY KEY, username TEXT UNIQUE, password TEXT,
            email TEXT UNIQUE, role TEXT DEFAULT 'user')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS pending_otps (
            id SERIAL PRIMARY KEY, email TEXT UNIQUE, password TEXT,
            otp TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    else:
        cur.execute("""CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY, username TEXT, amount REAL,
            category TEXT, date TEXT, risk_status TEXT)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY, username TEXT, monthly_budget REAL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY, action TEXT, username TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS registered_users (
            id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT,
            email TEXT UNIQUE, role TEXT DEFAULT 'user')""")
        cur.execute("""CREATE TABLE IF NOT EXISTS pending_otps (
            id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT,
            otp TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()
    seed_default_users()

def seed_default_users():
    conn = get_db()
    cur = conn.cursor()
    for username, info in users.items():
        cur.execute(f"SELECT id FROM registered_users WHERE username={p()}", (username,))
        if cur.fetchone():
            continue
        email = f"{username}@blueledger.local"
        cur.execute(
            f"INSERT INTO registered_users (username, password, email, role) VALUES ({p()},{p()},{p()},{p()})",
            (username, generate_password_hash(info["password"]), email, info["role"]),
        )
        cur.execute(f"INSERT INTO budgets (username, monthly_budget) VALUES ({p()},{p()})", (username, 0))
    conn.commit()
    conn.close()

def backup_database():
    if os.path.exists("database.db"):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"backups/database_backup_{timestamp}.db"
        shutil.copy("database.db", backup_file)
        print("✅ Database backup created:", backup_file)

# ─── ROUTES ───────────────────────────────────────────────────
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

@app.route("/l", methods=["POST"])
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
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

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute(f"SELECT SUM(amount) FROM expenses WHERE username={p()}", (session["user"],))
    total_expenses = cur.fetchone()[0] or 0

    cur.execute(f"SELECT COUNT(*) FROM expenses WHERE username={p()}", (session["user"],))
    total_transactions = cur.fetchone()[0]

    cur.execute(f"SELECT monthly_budget FROM budgets WHERE username={p()} ORDER BY id DESC LIMIT 1", (session["user"],))
    budget = cur.fetchone()
    current_budget = budget[0] if budget else 0

    cur.execute(f"SELECT COUNT(*) FROM expenses WHERE username={p()} AND risk_status LIKE {p()}", (session["user"], "%High Risk%"))
    high_risk = cur.fetchone()[0]
    conn.close()

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
    if current_budget > 0 and total_expenses > current_budget * 0.9:
        insights.append("📉 Enterprise budget is nearing critical utilization threshold.")
    if total_transactions > 20:
        insights.append("📊 AI forecasting engine predicts increased operational financial activity.")
    if high_risk >= 3:
        insights.append("🚨 Multiple high-risk anomalies indicate potential enterprise financial threats.")
    if current_budget > 0 and total_expenses < current_budget * 0.5:
        insights.append("💰 Enterprise financial reserves are currently in healthy condition.")

    return render_template("dashboard.html",
        total_expenses=total_expenses,
        total_transactions=total_transactions,
        current_budget=current_budget,
        high_risk=high_risk,
        insights=insights,
        risk_count=high_risk)

@app.route("/chart")
@login_required
def chart():
    return render_template("chart.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/ai-risk")
@login_required
def ai_risk():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM expenses WHERE username={p()} AND risk_status LIKE {p()}", (session["user"], "%High Risk%"))
    risks = cur.fetchall()
    conn.close()
    return render_template("ai_risk.html", risks=risks)

@app.route("/report")
@login_required
def report():
    return send_file("expense_report.pdf", as_attachment=True)

@app.route("/invoice")
@login_required
def invoice():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM expenses WHERE username={p()}", (session["user"],))
    expenses = cur.fetchall()
    cur.execute(f"SELECT * FROM budgets WHERE username={p()} ORDER BY id DESC LIMIT 1", (session["user"],))
    budget = cur.fetchone()
    conn.close()
    os.makedirs("invoices", exist_ok=True)
    path = generate_invoice(session["user"], expenses, budget)
    return send_file(path, as_attachment=True, download_name=f"BlueLedger_Invoice_{session['user']}.pdf")

@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    conn = get_db()
    cur = conn.cursor()
    risk_status = None
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            category = request.form["category"]
            date = request.form["date"]
            risk_status = predict_risk(amount)
            cur.execute(
                f"INSERT INTO expenses (username, amount, category, date, risk_status) VALUES ({p()},{p()},{p()},{p()},{p()})",
                (session["user"], amount, category, date, risk_status))
            conn.commit()
            cur.execute(f"INSERT INTO logs (action, username) VALUES ({p()},{p()})", ("Added Expense", session["user"]))
            conn.commit()
        except Exception as e:
            print("ERROR:", e)
            risk_status = "⚠ System Error Occurred"
    cur.execute(f"SELECT * FROM expenses WHERE username={p()}", (session["user"],))
    data = cur.fetchall()
    conn.close()
    return render_template("expenses.html", data=data, risk_status=risk_status)

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    conn = get_db()
    cur = conn.cursor()
    if request.method == "POST":
        monthly_budget = request.form["monthly_budget"]
        cur.execute(f"INSERT INTO budgets (username, monthly_budget) VALUES ({p()},{p()})", (session["user"], monthly_budget))
        conn.commit()
    cur.execute(f"SELECT * FROM budgets WHERE username={p()} ORDER BY id DESC LIMIT 1", (session["user"],))
    budget_data = cur.fetchone()
    cur.execute(f"SELECT SUM(amount) FROM expenses WHERE username={p()}", (session["user"],))
    total_expenses = cur.fetchone()[0] or 0
    conn.close()
    return render_template("budget.html", budget_data=budget_data, total_expenses=total_expenses)

@app.route("/logs")
@login_required
@role_required("manager")
def logs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM logs ORDER BY id DESC")
    logs = cur.fetchall()
    conn.close()
    return render_template("logs.html", logs=logs)

@app.route("/analytics")
@login_required
def analytics():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT category, SUM(amount) FROM expenses WHERE username={p()} GROUP BY category", (session["user"],))
    data = cur.fetchall()
    conn.close()
    categories = [row[0] for row in data]
    amounts = [row[1] for row in data]
    plt.figure(figsize=(8, 5))
    plt.bar(categories, amounts)
    plt.title("Enterprise Expense Analytics")
    plt.xlabel("Category")
    plt.ylabel("Amount")
    plt.tight_layout()
    plt.savefig("static/chart.png")
    plt.close()
    return render_template("analytics.html")

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

@app.errorhandler(Exception)
def handle_error(error):
    print("System Error:", error)
    if request.path.startswith('/auth/'):
        return jsonify({"success": False, "message": str(error)}), 500
    return render_template("error.html", error=error)

# ─── SIGNUP ───────────────────────────────────────────────────
@app.route("/auth/signup-step1", methods=["POST"])
def signup_step1():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    otp = generate_otp()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM pending_otps WHERE email={p()}", (email,))
    cur.execute(f"INSERT INTO pending_otps (email, password, otp) VALUES ({p()},{p()},{p()})", (email, password, otp))
    conn.commit()
    conn.close()

    body = f"""
    <p>Hello,</p>
    <p>Your BlueLedger verification OTP is:</p>
    <h2 style="letter-spacing:8px; color:#1565c0">{otp}</h2>
    <p>This OTP is valid for one-time use only.</p>
    <p>— BlueLedger AI Security Team</p>
    """

    def send_in_background():
        try:
            send_email(email, "BlueLedger — Verify Your Email", body)
        except Exception as e:
            print("Signup Email Error:", e)

    threading.Thread(target=send_in_background, daemon=True).start()
    return jsonify({"success": True, "message": "OTP sent to your email."})

@app.route("/auth/signup-step2", methods=["POST"])
def signup_step2():
    data = request.get_json()
    entered_otp = data.get("otp")
    email = data.get("email")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT otp FROM pending_otps WHERE email={p()}", (email,))
    record = cur.fetchone()
    conn.close()

    if not record:
        return jsonify({"success": False, "message": "Session expired. Please start again."})
    if entered_otp != record[0]:
        return jsonify({"success": False, "message": "Invalid OTP"})

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT id FROM registered_users WHERE email={p()}", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Email already registered"})
    conn.close()
    return jsonify({"success": True})

@app.route("/auth/signup-step3", methods=["POST"])
def signup_step3():
    data = request.get_json()
    username = data.get("username")
    role = data.get("role", "user")
    email = data.get("email")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT password FROM pending_otps WHERE email={p()}", (email,))
    record = cur.fetchone()

    if not record:
        conn.close()
        return jsonify({"success": False, "message": "Session expired. Please start again."})

    password = record[0]

    cur.execute(f"SELECT id FROM registered_users WHERE email={p()}", (email,))
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Email already registered"})

    cur.execute(f"SELECT id FROM registered_users WHERE username={p()}", (username,))
    if cur.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Username already taken"})

    hashed = generate_password_hash(password)
    cur.execute(
        f"INSERT INTO registered_users (username, password, email, role) VALUES ({p()},{p()},{p()},{p()})",
        (username, hashed, email, role))
    cur.execute(f"DELETE FROM pending_otps WHERE email={p()}", (email,))
    conn.commit()
    conn.close()
    provision_new_user(username, role)
    return jsonify({"success": True})

@app.route("/auth/change-password", methods=["POST"])
def change_password():
    data = request.get_json()
    username = data.get("username", "").strip()
    current_password = data.get("current_password", "").strip()
    new_password = data.get("new_password", "").strip()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT password FROM registered_users WHERE username={p()}", (username,))
    user = cur.fetchone()

    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Username not found."})
    if not verify_password(user[0], current_password):
        conn.close()
        return jsonify({"success": False, "message": "Current password is incorrect."})

    cur.execute(f"UPDATE registered_users SET password={p()} WHERE username={p()}", (generate_password_hash(new_password), username))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

@app.route("/auth/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json()
    email = data.get("email", "").strip().lower()

    conn = get_db()
    cur = conn.cursor()
    cur.execute(f"SELECT username FROM registered_users WHERE LOWER(email)={p()}", (email,))
    db_user = cur.fetchone()
    conn.close()

    if not db_user:
        return jsonify({"success": False, "message": "No account found with that email."})

    token = generate_password(32)
    pending_signups["reset_" + token] = {"username": db_user[0], "email": email}
    reset_link = f"{request.url_root.rstrip('/')}/reset-password?token={token}"

    body = f"""
    <p>Hello,</p>
    <p>Click below to reset your password:</p>
    <p><a href="{reset_link}">{reset_link}</a></p>
    """

    def send_in_background():
        try:
            send_email(email, "BlueLedger — Reset Password", body)
        except Exception as e:
            print("Forgot Password Email Error:", e)

    threading.Thread(target=send_in_background, daemon=True).start()
    return jsonify({"success": True, "message": "Password reset link sent."})

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token") or request.form.get("token")
    record = pending_signups.get("reset_" + token)

    if not record:
        flash("Invalid or expired reset link.", "error")
        return redirect(url_for("index"))

    if request.method == "POST":
        new_password = request.form.get("new_password")
        conn = get_db()
        cur = conn.cursor()
        cur.execute(f"UPDATE registered_users SET password={p()} WHERE username={p()}", (generate_password_hash(new_password), record["username"]))
        conn.commit()
        conn.close()
        del pending_signups["reset_" + token]
        flash("Password updated successfully.", "success")
        return redirect(url_for("index"))

    return render_template("login.html", show_reset=True, reset_token=token)

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
        return jsonify({"reply": reply})
    except Exception as e:
        print("CHAT ROUTE ERROR:", str(e))
        return jsonify({"reply": "Something went wrong."})

# ─── INIT ─────────────────────────────────────────────────────
with app.app_context():
    init_db()

if __name__ == "__main__":
    init_db()
    backup_database()
    app.run(debug=True)