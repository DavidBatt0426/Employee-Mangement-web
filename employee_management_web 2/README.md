# Employee Management Web App

A simple Flask web app with login, role-based access, employee management, and user control.

## Demo logins
- Full access: `admin` / `admin123`
- Only view: `viewer` / `viewer123`

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

## Deploy to Render
1. Upload this folder to GitHub.
2. Go to Render.com and create a new Web Service.
3. Connect your GitHub repo.
4. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
5. Deploy and Render will create your public URL.
