"""Complaint Management System (CMS) - Flask + SQLite."""
import os
import secrets
import sqlite3
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.environ.get("CMS_DATABASE", os.path.join(BASE_DIR, "database.db"))

app = Flask(__name__)
# Set SECRET_KEY in the environment for production. Random fallback is for local dev
# (sessions reset whenever the server restarts).
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


# ---------------------------------------------------------------- DATABASE
def get_db():
    """One connection per request, reused and closed automatically."""
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    """)
    # Default admin (change the password via ADMIN_PASSWORD env var or after first login)
    admin_pw = os.environ.get("ADMIN_PASSWORD", "admin123")
    exists = conn.execute("SELECT 1 FROM users WHERE email = ?",
                          ("admin@gmail.com",)).fetchone()
    if not exists:
        conn.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, 'admin')",
            ("Admin", "admin@gmail.com", generate_password_hash(admin_pw)),
        )
    conn.commit()
    conn.close()


init_db()  # runs for both `python app.py` and `flask run`


# ---------------------------------------------------------------- SECURITY
def get_csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def csrf_protect():
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        token = session.get("_csrf", "")
        if not token or not secrets.compare_digest(token, sent):
            abort(400, "Invalid or missing CSRF token")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@app.errorhandler(403)
def forbidden(_e):
    return render_template("error.html", code=403, message="Access denied."), 403


@app.errorhandler(400)
def bad_request(e):
    return render_template("error.html", code=400, message=e.description), 400


@app.errorhandler(404)
def not_found(_e):
    return render_template("error.html", code=404, message="Page not found."), 404


# ---------------------------------------------------------------- ROUTES
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("admin" if session.get("role") == "admin" else "dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name or not email or not password:
            flash("All fields are required.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                    (name, email, generate_password_hash(password)),
                )
                db.commit()
            except sqlite3.IntegrityError:
                flash("This email is already registered. Please login.", "danger")
            else:
                flash("Registration successful 🎉 Please login.", "success")
                return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session.clear()  # fresh session on login (prevents session fixation)
            session["user_id"] = user["id"]
            session["user"] = user["email"]
            session["name"] = user["name"]
            session["role"] = user["role"]
            flash("Login successful.", "success")
            return redirect(url_for("admin" if user["role"] == "admin" else "dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    stats = get_db().execute(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(status = 'Pending'), 0)  AS pending,
                  COALESCE(SUM(status = 'Resolved'), 0) AS resolved
           FROM complaints WHERE user_id = ?""",
        (session["user_id"],),
    ).fetchone()
    return render_template("dashboard.html", user=session["name"], stats=stats)


@app.route("/complaint", methods=["GET", "POST"])
@login_required
def complaint():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        if not title or not description:
            flash("Title and description are required.", "danger")
        elif len(title) > 100:
            flash("Title must be 100 characters or less.", "danger")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO complaints (user_id, title, description) VALUES (?, ?, ?)",
                (session["user_id"], title, description),
            )
            db.commit()
            flash("Complaint submitted successfully ✅", "success")
            return redirect(url_for("view_complaints"))
    return render_template("complaint.html")


@app.route("/view_complaints")
@login_required
def view_complaints():
    rows = get_db().execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    return render_template("view_complaints.html", complaints=rows)


@app.route("/admin")
@admin_required
def admin():
    db = get_db()
    complaints = db.execute(
        """SELECT c.*, u.name AS user_name, u.email AS user_email
           FROM complaints c JOIN users u ON u.id = c.user_id
           ORDER BY c.id DESC"""
    ).fetchall()
    stats = db.execute(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(status = 'Pending'), 0)  AS pending,
                  COALESCE(SUM(status = 'Resolved'), 0) AS resolved
           FROM complaints"""
    ).fetchone()
    return render_template("admin.html", complaints=complaints, stats=stats)


@app.route("/resolve/<int:complaint_id>", methods=["POST"])
@admin_required
def resolve(complaint_id):
    db = get_db()
    cur = db.execute(
        "UPDATE complaints SET status = 'Resolved' WHERE id = ?", (complaint_id,)
    )
    db.commit()
    if cur.rowcount == 0:
        abort(404)
    flash(f"Complaint #{complaint_id} marked as resolved.", "success")
    return redirect(url_for("admin"))


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
