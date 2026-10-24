# Complaint Management System (CMS)

A Flask + SQLite web app where users register, log in and submit complaints, and an admin reviews and resolves them.

## Features
- User registration and login with **hashed passwords** (Werkzeug)
- Role-based access: user dashboard vs. admin panel (decorators `login_required`, `admin_required`)
- Submit complaints, view own complaints with status and date
- Admin panel with stats, full complaint details and a Resolve action
- **CSRF protection** on all POST forms, parameterized SQL queries, safe session handling
- Responsive Bootstrap 5 UI

## Tech Stack
Python, Flask, SQLite, Jinja2, HTML, CSS, Bootstrap 5

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

Default admin (demo): `admin@gmail.com` / `admin123`
Change it by setting `ADMIN_PASSWORD` before the first run. Set `SECRET_KEY` for any real deployment.

## Project structure
```
app.py            # routes, DB helpers, auth/CSRF logic
templates/        # Jinja2 templates (base.html + pages)
static/style.css  # custom styles
database.db       # created automatically on first run
```
