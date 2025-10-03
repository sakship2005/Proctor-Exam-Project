import os
from dotenv import load_dotenv

load_dotenv()  # loads .env if present

class Config:
    # --- Config ---
    # Prefer an explicit DATABASE_URL (useful for deploys like Heroku/GitHub)
    DATABASE_URL = os.getenv('DATABASE_URL')

    # Backwards-compatible env vars (kept for existing setups). We default to SQLite
    # so the app can run without installing extra DB drivers when deployed to GitHub.
    DB_DIALECT = os.getenv('DB_DIALECT', 'sqlite')  # 'postgres', 'mysql' or 'sqlite'
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASS = os.getenv('DB_PASS', 'lucky29')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'exam_system1')
    
    SECRET_KEY = os.getenv('FLASK_SECRET', 'dev-secret-please-change')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    @staticmethod
    def get_database_uri():
        """Build and return the database URI"""
        if Config.DATABASE_URL:
            # If user provided a full DATABASE_URL (e.g., for production), use it directly.
            return Config.DATABASE_URL
        else:
            if Config.DB_DIALECT.lower() == 'mysql':
                # use pymysql (install pymysql if you choose mysql)
                return f'mysql+pymysql://{Config.DB_USER}:{Config.DB_PASS}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}'
            elif Config.DB_DIALECT.lower() in ('postgres', 'postgresql'):
                # postgres
                return f'postgresql+psycopg2://{Config.DB_USER}:{Config.DB_PASS}@{Config.DB_HOST}:{Config.DB_PORT}/{Config.DB_NAME}'
            else:
                # default: lightweight file-based SQLite database in project folder
                db_path = os.path.join(os.path.dirname(__file__), 'data.sqlite')
                return f'sqlite:///{db_path}'
