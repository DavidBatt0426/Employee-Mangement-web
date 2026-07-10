import os
import sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-change-this')
DB = os.path.join(os.path.dirname(__file__), 'employee_app.db')


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        title TEXT NOT NULL,
        access_level TEXT NOT NULL CHECK(access_level IN ('Full', 'Only View'))
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        hire_date TEXT NOT NULL,
        termination_date TEXT,
        status TEXT NOT NULL CHECK(status IN ('Active', 'Inactive', 'Hold')),
        pay_rate REAL NOT NULL,
        title TEXT NOT NULL,
        department TEXT NOT NULL
    )''')
    cur.execute('SELECT COUNT(*) AS count FROM users')
    if cur.fetchone()['count'] == 0:
        cur.execute('INSERT INTO users (username, password_hash, title, access_level) VALUES (?, ?, ?, ?)',
                    ('admin', generate_password_hash('admin123'), 'Administrator', 'Full'))
        cur.execute('INSERT INTO users (username, password_hash, title, access_level) VALUES (?, ?, ?, ?)',
                    ('viewer', generate_password_hash('viewer123'), 'Viewer', 'Only View'))
    cur.execute('SELECT COUNT(*) AS count FROM employees')
    if cur.fetchone()['count'] == 0:
        sample = [
            ('John Smith', '2026-06-01', '', 'Active', 25.00, 'Technician', 'Operations'),
            ('Maria Johnson', '2025-09-15', '', 'Active', 32.50, 'Manager', 'Sales'),
            ('Sam Lee', '2024-02-10', '', 'Hold', 28.00, 'Analyst', 'Finance'),
        ]
        cur.executemany('''INSERT INTO employees
            (name, hire_date, termination_date, status, pay_rate, title, department)
            VALUES (?, ?, ?, ?, ?, ?, ?)''', sample)
    conn.commit()
    conn.close()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper


def full_access_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if session.get('access_level') != 'Full':
            flash('Only users with Full access can make changes.', 'error')
            return redirect(url_for('employees'))
        return fn(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return dict(current_user=session)


@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['title'] = user['title']
            session['access_level'] = user['access_level']
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db()
    employee_count = conn.execute('SELECT COUNT(*) AS count FROM employees').fetchone()['count']
    user_count = conn.execute('SELECT COUNT(*) AS count FROM users').fetchone()['count']
    conn.close()
    return render_template('dashboard.html', employee_count=employee_count, user_count=user_count)


@app.route('/employees')
@login_required
def employees():
    search = request.args.get('search', '').strip()
    conn = get_db()
    if search:
        like = f'%{search}%'
        rows = conn.execute('''SELECT * FROM employees
            WHERE name LIKE ? OR title LIKE ? OR department LIKE ? OR status LIKE ?
            ORDER BY id DESC''', (like, like, like, like)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM employees ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('employees.html', employees=rows, search=search)


@app.route('/employees/add', methods=['GET', 'POST'])
@login_required
@full_access_required
def add_employee():
    if request.method == 'POST':
        data = (request.form['name'], request.form['hire_date'], request.form.get('termination_date', ''),
                request.form['status'], float(request.form['pay_rate']), request.form['title'], request.form['department'])
        conn = get_db()
        conn.execute('''INSERT INTO employees (name, hire_date, termination_date, status, pay_rate, title, department)
                        VALUES (?, ?, ?, ?, ?, ?, ?)''', data)
        conn.commit()
        conn.close()
        flash('Employee added successfully.', 'success')
        return redirect(url_for('employees'))
    return render_template('employee_form.html', employee=None, action='Add')


@app.route('/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
@login_required
@full_access_required
def edit_employee(employee_id):
    conn = get_db()
    employee = conn.execute('SELECT * FROM employees WHERE id = ?', (employee_id,)).fetchone()
    if not employee:
        conn.close()
        flash('Employee not found.', 'error')
        return redirect(url_for('employees'))
    if request.method == 'POST':
        data = (request.form['name'], request.form['hire_date'], request.form.get('termination_date', ''),
                request.form['status'], float(request.form['pay_rate']), request.form['title'], request.form['department'], employee_id)
        conn.execute('''UPDATE employees SET name=?, hire_date=?, termination_date=?, status=?, pay_rate=?, title=?, department=?
                        WHERE id=?''', data)
        conn.commit()
        conn.close()
        flash('Employee updated successfully.', 'success')
        return redirect(url_for('employees'))
    conn.close()
    return render_template('employee_form.html', employee=employee, action='Edit')


@app.route('/employees/<int:employee_id>/delete', methods=['POST'])
@login_required
@full_access_required
def delete_employee(employee_id):
    conn = get_db()
    conn.execute('DELETE FROM employees WHERE id = ?', (employee_id,))
    conn.commit()
    conn.close()
    flash('Employee deleted successfully.', 'success')
    return redirect(url_for('employees'))


@app.route('/users')
@login_required
@full_access_required
def users():
    conn = get_db()
    rows = conn.execute('SELECT id, username, title, access_level FROM users ORDER BY id DESC').fetchall()
    conn.close()
    return render_template('users.html', users=rows)


@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@full_access_required
def add_user():
    if request.method == 'POST':
        conn = get_db()
        try:
            conn.execute('INSERT INTO users (username, password_hash, title, access_level) VALUES (?, ?, ?, ?)',
                         (request.form['username'].strip(), generate_password_hash(request.form['password']),
                          request.form['title'], request.form['access_level']))
            conn.commit()
            flash('User added successfully.', 'success')
        except sqlite3.IntegrityError:
            flash('Username already exists.', 'error')
        conn.close()
        return redirect(url_for('users'))
    return render_template('user_form.html', user=None, action='Add')


@app.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@full_access_required
def edit_user(user_id):
    conn = get_db()
    user = conn.execute('SELECT id, username, title, access_level FROM users WHERE id = ?', (user_id,)).fetchone()
    if not user:
        conn.close()
        flash('User not found.', 'error')
        return redirect(url_for('users'))
    if request.method == 'POST':
        if request.form.get('password'):
            conn.execute('UPDATE users SET username=?, password_hash=?, title=?, access_level=? WHERE id=?',
                         (request.form['username'].strip(), generate_password_hash(request.form['password']),
                          request.form['title'], request.form['access_level'], user_id))
        else:
            conn.execute('UPDATE users SET username=?, title=?, access_level=? WHERE id=?',
                         (request.form['username'].strip(), request.form['title'], request.form['access_level'], user_id))
        conn.commit()
        conn.close()
        flash('User updated successfully.', 'success')
        return redirect(url_for('users'))
    conn.close()
    return render_template('user_form.html', user=user, action='Edit')


@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@full_access_required
def delete_user(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account while logged in.', 'error')
        return redirect(url_for('users'))
    conn = get_db()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash('User deleted successfully.', 'success')
    return redirect(url_for('users'))


init_db()

if __name__ == '__main__':
    app.run(debug=True)
