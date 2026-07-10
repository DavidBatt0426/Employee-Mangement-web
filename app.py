import os, sqlite3
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(app.root_path, "employee_app.db"))

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      title TEXT NOT NULL,
      access_level TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS employees(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      hire_date TEXT NOT NULL,
      termination_date TEXT,
      status TEXT NOT NULL,
      pay_rate REAL NOT NULL,
      title TEXT NOT NULL,
      department TEXT NOT NULL
    );
    ''')
    if db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == 0:
        db.execute("INSERT INTO users(username,password_hash,title,access_level) VALUES(?,?,?,?)",
                   ("admin", generate_password_hash("admin123"), "Administrator", "Full"))
        db.execute("INSERT INTO users(username,password_hash,title,access_level) VALUES(?,?,?,?)",
                   ("viewer", generate_password_hash("viewer123"), "Viewer", "Only View"))
    if db.execute("SELECT COUNT(*) c FROM employees").fetchone()["c"] == 0:
        db.execute("INSERT INTO employees(name,hire_date,termination_date,status,pay_rate,title,department) VALUES(?,?,?,?,?,?,?)",
                   ("Jordan Smith","2026-01-15","","Active",25.0,"Technician","Operations"))
    db.commit()

@app.before_request
def setup():
    init_db()

def login_required(fn):
    @wraps(fn)
    def wrapped(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return fn(*a, **k)
    return wrapped

def full_required(fn):
    @wraps(fn)
    def wrapped(*a, **k):
        if session.get("access_level") != "Full":
            flash("You only have view access.", "error")
            return redirect(url_for("employees"))
        return fn(*a, **k)
    return wrapped

@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = get_db().execute("SELECT * FROM users WHERE username=?", (request.form["username"].strip(),)).fetchone()
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session.update(user_id=u["id"], username=u["username"], access_level=u["access_level"])
            return redirect(url_for("dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    db=get_db()
    return render_template("dashboard.html",
      employee_count=db.execute("SELECT COUNT(*) c FROM employees").fetchone()["c"],
      active_count=db.execute("SELECT COUNT(*) c FROM employees WHERE status='Active'").fetchone()["c"],
      user_count=db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"])

@app.route("/employees")
@login_required
def employees():
    return render_template("employees.html", employees=get_db().execute("SELECT * FROM employees ORDER BY id DESC").fetchall())

@app.route("/employees/add", methods=["GET","POST"])
@login_required
@full_required
def add_employee():
    if request.method == "POST":
        get_db().execute("INSERT INTO employees(name,hire_date,termination_date,status,pay_rate,title,department) VALUES(?,?,?,?,?,?,?)",
          (request.form["name"],request.form["hire_date"],request.form.get("termination_date",""),request.form["status"],
           float(request.form["pay_rate"]),request.form["title"],request.form["department"]))
        get_db().commit(); flash("Employee added successfully.","success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None, heading="Add Employee")

@app.route("/employees/<int:i>/edit", methods=["GET","POST"])
@login_required
@full_required
def edit_employee(i):
    db=get_db(); e=db.execute("SELECT * FROM employees WHERE id=?",(i,)).fetchone()
    if request.method=="POST":
        db.execute("UPDATE employees SET name=?,hire_date=?,termination_date=?,status=?,pay_rate=?,title=?,department=? WHERE id=?",
          (request.form["name"],request.form["hire_date"],request.form.get("termination_date",""),request.form["status"],
           float(request.form["pay_rate"]),request.form["title"],request.form["department"],i))
        db.commit(); flash("Employee updated successfully.","success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=e, heading="Edit Employee")

@app.post("/employees/<int:i>/delete")
@login_required
@full_required
def delete_employee(i):
    get_db().execute("DELETE FROM employees WHERE id=?",(i,)); get_db().commit()
    flash("Employee deleted successfully.","success")
    return redirect(url_for("employees"))

@app.route("/users")
@login_required
@full_required
def users():
    return render_template("users.html", users=get_db().execute("SELECT id,username,title,access_level FROM users ORDER BY id").fetchall())

@app.route("/users/add", methods=["GET","POST"])
@login_required
@full_required
def add_user():
    if request.method=="POST":
        try:
            get_db().execute("INSERT INTO users(username,password_hash,title,access_level) VALUES(?,?,?,?)",
              (request.form["username"],generate_password_hash(request.form["password"]),request.form["title"],request.form["access_level"]))
            get_db().commit(); flash("User added successfully.","success")
            return redirect(url_for("users"))
        except sqlite3.IntegrityError:
            flash("That username already exists.","error")
    return render_template("user_form.html", user=None, heading="Add User")

@app.route("/users/<int:i>/edit", methods=["GET","POST"])
@login_required
@full_required
def edit_user(i):
    db=get_db(); u=db.execute("SELECT * FROM users WHERE id=?",(i,)).fetchone()
    if request.method=="POST":
        if request.form.get("password"):
            db.execute("UPDATE users SET username=?,password_hash=?,title=?,access_level=? WHERE id=?",
              (request.form["username"],generate_password_hash(request.form["password"]),request.form["title"],request.form["access_level"],i))
        else:
            db.execute("UPDATE users SET username=?,title=?,access_level=? WHERE id=?",
              (request.form["username"],request.form["title"],request.form["access_level"],i))
        db.commit(); flash("User updated successfully.","success")
        return redirect(url_for("users"))
    return render_template("user_form.html", user=u, heading="Edit User")

@app.post("/users/<int:i>/delete")
@login_required
@full_required
def delete_user(i):
    if i == session.get("user_id"):
        flash("You cannot delete the account you are using.","error")
    else:
        get_db().execute("DELETE FROM users WHERE id=?",(i,)); get_db().commit()
        flash("User deleted successfully.","success")
    return redirect(url_for("users"))

@app.route("/health")
def health():
    return {"status":"ok"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
