import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
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

SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your elementary school?",
    "What was the make of your first car?",
    "What was your childhood nickname?",
    "What is the middle name of your oldest sibling?",
]

DEPARTMENTS = [
    "Administration",
    "Customer Service",
    "Finance",
    "Human Resources",
    "Information Technology",
    "Marketing",
    "Operations",
    "Sales",
]

JOB_TITLES = [
    "Administrator",
    "Analyst",
    "Assistant",
    "Coordinator",
    "Director",
    "Manager",
    "Specialist",
    "Supervisor",
    "Technician",
]

SETUP_LINK_HOURS = 24
MAX_RECOVERY_ATTEMPTS = 5


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    access_level = db.Column(db.String(20), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    setup_token_hash = db.Column(db.String(255), nullable=True)
    setup_token_expires = db.Column(db.DateTime(timezone=True), nullable=True)

    security_question_1 = db.Column(db.String(255), nullable=True)
    security_answer_1_hash = db.Column(db.String(255), nullable=True)
    security_question_2 = db.Column(db.String(255), nullable=True)
    security_answer_2_hash = db.Column(db.String(255), nullable=True)
    security_question_3 = db.Column(db.String(255), nullable=True)
    security_answer_3_hash = db.Column(db.String(255), nullable=True)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    hire_date = db.Column(db.String(20), nullable=False)
    termination_date = db.Column(db.String(20), default="")
    status = db.Column(db.String(20), nullable=False)
    pay_rate = db.Column(db.Float, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    department = db.Column(db.String(120), nullable=False)


def utc_now():
    return datetime.now(timezone.utc)


def normalize_answer(answer):
    return " ".join(answer.strip().lower().split())


def add_user_columns_if_missing():
    inspector = inspect(db.engine)
    if "user" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("user")}
    additions = {
        "email": "VARCHAR(255)",
        "is_active": "BOOLEAN DEFAULT TRUE",
        "setup_token_hash": "VARCHAR(255)",
        "setup_token_expires": "TIMESTAMP WITH TIME ZONE",
        "security_question_1": "VARCHAR(255)",
        "security_answer_1_hash": "VARCHAR(255)",
        "security_question_2": "VARCHAR(255)",
        "security_answer_2_hash": "VARCHAR(255)",
        "security_question_3": "VARCHAR(255)",
        "security_answer_3_hash": "VARCHAR(255)",
    }

    for column_name, column_type in additions.items():
        if column_name not in existing:
            db.session.execute(
                text(f'ALTER TABLE "user" ADD COLUMN {column_name} {column_type}')
            )

    db.session.execute(
        text('UPDATE "user" SET is_active = TRUE WHERE is_active IS NULL')
    )
    db.session.commit()


def initialize_database():
    db.create_all()
    add_user_columns_if_missing()

    if User.query.count() == 0:
        db.session.add_all(
            [
                User(
                    username="admin",
                    email=None,
                    password_hash=generate_password_hash("admin123"),
                    title="Administrator",
                    access_level="Full",
                    is_active=True,
                ),
                User(
                    username="viewer",
                    email=None,
                    password_hash=generate_password_hash("viewer123"),
                    title="Viewer",
                    access_level="Only View",
                    is_active=True,
                ),
            ]
        )

    if Employee.query.count() == 0:
        db.session.add(
            Employee(
                name="Jordan Smith",
                hire_date="2026-01-15",
                termination_date="",
                status="Active",
                pay_rate=25.00,
                title="Technician",
                department="Operations",
            )
        )

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


def make_setup_link(user):
    raw_token = secrets.token_urlsafe(32)
    user.setup_token_hash = generate_password_hash(raw_token)
    user.setup_token_expires = utc_now() + timedelta(hours=SETUP_LINK_HOURS)
    db.session.commit()

    app_url = os.environ.get("APP_URL", "").rstrip("/")
    relative_path = url_for("account_setup", user_id=user.id, token=raw_token)
    return f"{app_url}{relative_path}" if app_url else url_for(
        "account_setup",
        user_id=user.id,
        token=raw_token,
        _external=True,
        _scheme="https",
    )


def token_is_valid(user, raw_token):
    if not user or not user.setup_token_hash or not user.setup_token_expires:
        return False

    expires = user.setup_token_expires
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    return expires > utc_now() and check_password_hash(
        user.setup_token_hash,
        raw_token,
    )


@app.route("/")
def index():
    return redirect(url_for("dashboard") if "user_id" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form["identifier"].strip()
        password = request.form["password"]

        user = User.query.filter(
            (User.username == identifier) | (User.email == identifier.lower())
        ).first()

        if user and user.is_active and check_password_hash(user.password_hash, password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["access_level"] = user.access_level
            return redirect(url_for("dashboard"))

        if user and not user.is_active:
            flash("This account still needs to be set up using the email invitation.", "error")
        else:
            flash("Incorrect username, email, or password.", "error")

    return render_template("login.html")


@app.route("/account-setup/<int:user_id>/<token>", methods=["GET", "POST"])
def account_setup(user_id, token):
    user = db.session.get(User, user_id)

    if not token_is_valid(user, token):
        flash("That setup link is invalid or has expired. Ask an administrator to resend it.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirmation = request.form.get("confirm_password", "")

        questions = [
            request.form["security_question_1"],
            request.form["security_question_2"],
            request.form["security_question_3"],
        ]
        answers = [
            normalize_answer(request.form["security_answer_1"]),
            normalize_answer(request.form["security_answer_2"]),
            normalize_answer(request.form["security_answer_3"]),
        ]

        if len(password) < 8:
            flash("Your password must be at least 8 characters.", "error")
        elif password != confirmation:
            flash("The passwords do not match.", "error")
        elif len(set(questions)) != 3:
            flash("Please choose three different security questions.", "error")
        elif any(len(answer) < 2 for answer in answers):
            flash("Please answer all three security questions.", "error")
        else:
            user.password_hash = generate_password_hash(password)
            user.security_question_1 = questions[0]
            user.security_answer_1_hash = generate_password_hash(answers[0])
            user.security_question_2 = questions[1]
            user.security_answer_2_hash = generate_password_hash(answers[1])
            user.security_question_3 = questions[2]
            user.security_answer_3_hash = generate_password_hash(answers[2])
            user.setup_token_hash = None
            user.setup_token_expires = None
            user.is_active = True
            db.session.commit()

            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            session["access_level"] = user.access_level
            flash("Your account has been set up successfully.", "success")
            return redirect(url_for("dashboard"))

    return render_template(
        "account_setup.html",
        user=user,
        security_questions=SECURITY_QUESTIONS,
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    stage = session.get("password_reset_stage", "identifier")
    reset_user = None

    if session.get("password_reset_user_id"):
        reset_user = db.session.get(User, session["password_reset_user_id"])

    if request.method == "POST":
        action = request.form.get("action")

        if action == "find_account":
            identifier = request.form.get("identifier", "").strip()
            user = User.query.filter(
                (User.username == identifier) | (User.email == identifier.lower())
            ).first()

            questions_ready = (
                user
                and user.is_active
                and user.security_question_1
                and user.security_answer_1_hash
                and user.security_question_2
                and user.security_answer_2_hash
                and user.security_question_3
                and user.security_answer_3_hash
            )

            if not questions_ready:
                flash(
                    "That account cannot use security-question recovery. Contact an administrator.",
                    "error",
                )
                return render_template("forgot_password.html", stage="identifier")

            session["password_reset_user_id"] = user.id
            session["password_reset_stage"] = "questions"
            session["password_reset_attempts"] = 0
            return redirect(url_for("forgot_password"))

        if action == "verify_answers" and reset_user:
            answers = [
                normalize_answer(request.form.get("answer_1", "")),
                normalize_answer(request.form.get("answer_2", "")),
                normalize_answer(request.form.get("answer_3", "")),
            ]

            answers_match = all(
                [
                    check_password_hash(reset_user.security_answer_1_hash, answers[0]),
                    check_password_hash(reset_user.security_answer_2_hash, answers[1]),
                    check_password_hash(reset_user.security_answer_3_hash, answers[2]),
                ]
            )

            if answers_match:
                session["password_reset_stage"] = "new_password"
                return redirect(url_for("forgot_password"))

            attempts = session.get("password_reset_attempts", 0) + 1
            session["password_reset_attempts"] = attempts

            if attempts >= MAX_RECOVERY_ATTEMPTS:
                session.pop("password_reset_user_id", None)
                session.pop("password_reset_stage", None)
                session.pop("password_reset_attempts", None)
                flash("Too many incorrect attempts. Please start again.", "error")
                return redirect(url_for("forgot_password"))

            flash(
                f"One or more answers were incorrect. "
                f"{MAX_RECOVERY_ATTEMPTS - attempts} attempts remain.",
                "error",
            )

        if action == "reset_password" and reset_user and stage == "new_password":
            password = request.form.get("password", "")
            confirmation = request.form.get("confirm_password", "")

            if len(password) < 8:
                flash("The new password must be at least 8 characters.", "error")
            elif password != confirmation:
                flash("The passwords do not match.", "error")
            else:
                reset_user.password_hash = generate_password_hash(password)
                db.session.commit()

                session.clear()
                session["user_id"] = reset_user.id
                session["username"] = reset_user.username
                session["access_level"] = reset_user.access_level
                flash("Your password was reset successfully.", "success")
                return redirect(url_for("dashboard"))

    return render_template(
        "forgot_password.html",
        stage=stage,
        reset_user=reset_user,
    )


@app.route("/forgot-password/cancel")
def cancel_password_reset():
    session.pop("password_reset_user_id", None)
    session.pop("password_reset_stage", None)
    session.pop("password_reset_attempts", None)
    return redirect(url_for("login"))


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
    return render_template(
        "employees.html",
        employees=Employee.query.order_by(Employee.id.desc()).all(),
    )


@app.route("/employees/add", methods=["GET", "POST"])
@login_required
@full_access_required
def add_employee():
    if request.method == "POST":
        employee = Employee(
            name=request.form["name"].strip(),
            hire_date=request.form["hire_date"],
            termination_date=request.form.get("termination_date", ""),
            status=request.form["status"],
            pay_rate=float(request.form["pay_rate"]),
            title=request.form["title"],
            department=request.form["department"],
        )
        db.session.add(employee)
        db.session.commit()
        flash("Employee added successfully.", "success")
        return redirect(url_for("employees"))

    return render_template(
        "employee_form.html",
        employee=None,
        heading="Add Employee",
        departments=DEPARTMENTS,
        job_titles=JOB_TITLES,
    )


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
        employee.title = request.form["title"]
        employee.department = request.form["department"]
        db.session.commit()
        flash("Employee updated successfully.", "success")
        return redirect(url_for("employees"))

    return render_template(
        "employee_form.html",
        employee=employee,
        heading="Edit Employee",
        departments=DEPARTMENTS,
        job_titles=JOB_TITLES,
    )


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
        email = request.form["email"].strip().lower()
        user = User(
            username=request.form["username"].strip(),
            email=email,
            password_hash=generate_password_hash(secrets.token_urlsafe(32)),
            title=request.form["title"].strip(),
            access_level=request.form["access_level"],
            is_active=False,
        )
        db.session.add(user)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That username or email already exists.", "error")
            return render_template("user_form.html", user=None, heading="Add User")

        setup_link = make_setup_link(user)
        session["new_user_setup_link"] = setup_link
        session["new_user_setup_email"] = user.email
        flash("User created successfully. Copy the setup link below and send it to the user.", "success")
        return redirect(url_for("users"))

    return render_template("user_form.html", user=None, heading="Add User")


@app.route("/users/<int:i>/edit", methods=["GET", "POST"])
@login_required
@full_access_required
def edit_user(i):
    user = db.get_or_404(User, i)

    if request.method == "POST":
        user.username = request.form["username"].strip()
        user.email = request.form["email"].strip().lower()
        user.title = request.form["title"].strip()
        user.access_level = request.form["access_level"]

        try:
            db.session.commit()
            flash("User updated successfully.", "success")
            return redirect(url_for("users"))
        except IntegrityError:
            db.session.rollback()
            flash("That username or email already exists.", "error")

    return render_template("user_form.html", user=user, heading="Edit User")


@app.post("/users/<int:i>/resend-setup")
@login_required
@full_access_required
def resend_setup(i):
    user = db.get_or_404(User, i)

    if user.is_active:
        flash("That account is already active.", "error")
        return redirect(url_for("users"))

    setup_link = make_setup_link(user)
    session["new_user_setup_link"] = setup_link
    session["new_user_setup_email"] = user.email
    flash("A new setup link was created. Copy it below and send it to the user.", "success")
    return redirect(url_for("users"))


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

    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
    )
