import os
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

database_url = os.environ.get("DATABASE_URL", "sqlite:///employee_app.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}

db = SQLAlchemy(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    access_level = db.Column(db.String(20), nullable=False)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    hire_date = db.Column(db.String(20), nullable=False)
    termination_date = db.Column(db.String(20), default="")
    status = db.Column(db.String(20), nullable=False)
    pay_rate = db.Column(db.Float, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)


def initialize_database():
    db.create_all()

    if User.query.count() == 0:
        db.session.add_all([
            User(username="admin", password_hash=generate_password_hash("admin123"), title="Administrator", access_level="Full"),
            User(username="viewer", password_hash=generate_password_hash("viewer123"), title="Viewer", access_level="Only View"),
        ])

    if Employee.query.count() == 0:
        db.session.add(Employee(
            name="Jordan Smith",
            hire_date="2026-01-15",
            termination_date="",
            status="Active",
            pay_rate=25.00,
            title="Technician",
            department="Operations",
        ))

    db.session.commit()


@app.before_request
def setup_database():
    initialize_database()


def login_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return function(*args, **kwargs)
    return wrapped


def full_access_required(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if session.get("access_level") != "Full":
            flash("You only have view access.", "error")
            return redirect(url_for("employees"))
        return function(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form["username"].strip()).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session.clear()
            session.update(user_id=user.id, username=user.username, access_level=user.access_level)
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
    return render_template(
        "dashboard.html",
        employee_count=Employee.query.count(),
        active_count=Employee.query.filter_by(status="Active").count(),
        user_count=User.query.count(),
    )


@app.route("/employees")
@login_required
def employees():
    return render_template("employees.html", employees=Employee.query.order_by(Employee.id.desc()).all())


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
@full_access_required
def add_employee():
    if request.method == "POST":
        db.session.add(Employee(
            name=request.form["name"].strip(),
            hire_date=request.form["hire_date"],
            termination_date=request.form.get("termination_date", ""),
            status=request.form["status"],
            pay_rate=float(request.form["pay_rate"]),
            title=request.form["title"].strip(),
            department=request.form["department"].strip(),
        ))
        db.session.commit()
        flash("Employee added successfully.", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=None, heading="Add Employee")


@app.route("/employees/<int:i>/edit", methods=["GET", "POST"])
@login_required
@full_access_required
def edit_employee(i):
    employee = db.get_or_404(Employee, i)
    if request.method == "POST":
        employee.name = request.form["name"].strip()
        employee.hire_date = request.form["hire_date"]
        employee.termination_date = request.form.get("termination_date", "")
        employee.status = request.form["status"]
        employee.pay_rate = float(request.form["pay_rate"])
        employee.title = request.form["title"].strip()
        employee.department = request.form["department"].strip()
        db.session.commit()
        flash("Employee updated successfully.", "success")
        return redirect(url_for("employees"))
    return render_template("employee_form.html", employee=employee, heading="Edit Employee")


@app.post("/employees/<int:i>/delete")
@login_required
@full_access_required
def delete_employee(i):
    employee = db.get_or_404(Employee, i)
    db.session.delete(employee)
    db.session.commit()
    flash("Employee deleted successfully.", "success")
    return redirect(url_for("employees"))


@app.route("/users")
@login_required
@full_access_required
def users():
    return render_template("users.html", users=User.query.order_by(User.id).all())


@app.route("/users/add", methods=["GET", "POST"])
@login_required
@full_access_required
def add_user():
    if request.method == "POST":
        db.session.add(User(
            username=request.form["username"].strip(),
            password_hash=generate_password_hash(request.form["password"]),
            title=request.form["title"].strip(),
            access_level=request.form["access_level"],
        ))
        try:
            db.session.commit()
            flash("User added successfully.", "success")
            return redirect(url_for("users"))
        except IntegrityError:
            db.session.rollback()
            flash("That username already exists.", "error")
    return render_template("user_form.html", user=None, heading="Add User")


@app.route("/users/<int:i>/edit", methods=["GET", "POST"])
@login_required
@full_access_required
def edit_user(i):
    user = db.get_or_404(User, i)
    if request.method == "POST":
        user.username = request.form["username"].strip()
        user.title = request.form["title"].strip()
        user.access_level = request.form["access_level"]
        if request.form.get("password"):
            user.password_hash = generate_password_hash(request.form["password"])
        try:
            db.session.commit()
            flash("User updated successfully.", "success")
            return redirect(url_for("users"))
        except IntegrityError:
            db.session.rollback()
            flash("That username already exists.", "error")
    return render_template("user_form.html", user=user, heading="Edit User")


@app.post("/users/<int:i>/delete")
@login_required
@full_access_required
def delete_user(i):
    if i == session.get("user_id"):
        flash("You cannot delete the account you are using.", "error")
        return redirect(url_for("users"))
    user = db.get_or_404(User, i)
    db.session.delete(user)
    db.session.commit()
    flash("User deleted successfully.", "success")
    return redirect(url_for("users"))


@app.route("/health")
def health():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    with app.app_context():
        initialize_database()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
