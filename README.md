# Exam System (Flask)

This project is a small Flask admin UI for creating/listing users and viewing logs. Changes were made so it uses SQLite by default, making it easy to run locally and deploy to GitHub.

## What I changed
- Default database changed to SQLite (file `data.sqlite` in project root) so you don't need to install Postgres or other DB drivers.
- `DATABASE_URL` env var is still supported for production (e.g., Heroku). If `DATABASE_URL` is set it will be used instead.
- Removed `psycopg2-binary` from `requirements.txt` because SQLite doesn't need it.

## Requirements
- Python 3.10+ recommended (the project uses Flask 2.3.x)

## Setup (Windows PowerShell)
1. Create and activate a virtual environment:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. (Optional) Create a `.env` file in the project root to override defaults. Example `.env`:

```
FLASK_SECRET=change-me
# Optional: DATABASE_URL=sqlite:///C:/full/path/to/data.sqlite
```

4. Run the app:

```powershell
python app.py
```

5. Open `http://127.0.0.1:5000/admin/login` in your browser. Use username `admin` and password `admin` to login.

## Deploying to GitHub Pages / GitHub Codespaces
- GitHub Pages can't run a Flask server. To run the app on GitHub infrastructure consider:
  - GitHub Codespaces (run within the codespace), or
  - Deploy to Heroku / Railway / Render and connect your GitHub repo.

## Notes
- If you want to use Postgres or MySQL, set `DATABASE_URL` or set `DB_DIALECT`/other DB_* env vars and install the appropriate driver (`psycopg2-binary` or `pymysql`).
- The database file `data.sqlite` will be created automatically on first run.

If you'd like, I can also add a small `.gitignore` and a sample `.env` file.
