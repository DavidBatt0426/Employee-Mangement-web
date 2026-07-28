# Employee Management App — PostgreSQL Version

This version stores users and employees in PostgreSQL so records remain after the web service restarts.

Demo accounts:
- admin / admin123
- viewer / viewer123

Render web service:
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app`
- Environment variable: `DATABASE_URL` should use the Render Postgres internal database URL.
