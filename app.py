from flask import Flask, render_template
from flask import jsonify
from config import Config
from models import db
from admin_routes import admin_bp
from student_routes import student_bp
from teacher_routes import teacher_bp
import threading

def start_xmlrpc_server():
    # Lightweight in-process XML-RPC server to demonstrate RPC
    try:
        from xmlrpc.server import SimpleXMLRPCServer
    except Exception:
        return
    events = []
    def ping():
        return 'pong'
    def record_event(ev: dict):
        try:
            events.append(ev)
            return True
        except Exception:
            return False
    server = SimpleXMLRPCServer(('127.0.0.1', 9000), allow_none=True, logRequests=False)
    server.register_function(ping, 'ping')
    server.register_function(record_event, 'record_event')
    th = threading.Thread(target=server.serve_forever, daemon=True)
    th.start()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = Config.get_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = Config.SQLALCHEMY_TRACK_MODIFICATIONS

# Initialize database
db.init_app(app)

# Register blueprints
app.register_blueprint(admin_bp)
app.register_blueprint(student_bp)
app.register_blueprint(teacher_bp)

# Database initialization and migration
def init_database():
    """Initialize database and handle migrations"""
    db.create_all()
    
    # Lightweight runtime migration for SQLite: add columns that may be missing
    # This helps existing local DBs created before fields were added.
    # Only run for SQLite to avoid accidental DDL on other DBs.
    try:
        if app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite'):
            # Inspect current columns in exams
            from sqlalchemy import text
            res = db.session.execute(text("PRAGMA table_info('exams');")).fetchall()
            cols = {r[1] for r in res}  # r[1] is column name
            # Add is_published column if missing
            if 'is_published' not in cols:
                db.session.execute(text("ALTER TABLE exams ADD COLUMN is_published INTEGER DEFAULT 0;"))
                db.session.commit()
            # Add num_questions column if missing
            if 'num_questions' not in cols:
                db.session.execute(text("ALTER TABLE exams ADD COLUMN num_questions INTEGER;"))
                db.session.commit()
            # Inspect current columns in questions and add any missing ones
            try:
                resq = db.session.execute(text("PRAGMA table_info('questions');")).fetchall()
                qcols = {r[1] for r in resq}
                if 'option_a' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN option_a VARCHAR(255) DEFAULT '';"))
                    db.session.commit()
                if 'option_b' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN option_b VARCHAR(255) DEFAULT '';"))
                    db.session.commit()
                if 'option_c' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN option_c VARCHAR(255) DEFAULT '';"))
                    db.session.commit()
                if 'option_d' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN option_d VARCHAR(255) DEFAULT '';"))
                    db.session.commit()
                if 'correct_option' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN correct_option VARCHAR(1) DEFAULT 'A';"))
                    db.session.commit()
                if 'points' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN points REAL;"))
                    db.session.commit()
                if 'time_seconds' not in qcols:
                    db.session.execute(text("ALTER TABLE questions ADD COLUMN time_seconds INTEGER;"))
                    db.session.commit()
                # Ensure marks.cheating_count exists
                resm = db.session.execute(text("PRAGMA table_info('marks');")).fetchall()
                mcols = {r[1] for r in resm}
                if 'cheating_count' not in mcols:
                    db.session.execute(text("ALTER TABLE marks ADD COLUMN cheating_count INTEGER DEFAULT 0;"))
                    db.session.commit()
            except Exception:
                # don't let questions migration break app start
                pass
    except Exception:
        # If migration fails, don't crash the app here; logs will show the problem.
        pass

# Initialize database with app context
with app.app_context():
    init_database()
    # Start RPC server thread
    start_xmlrpc_server()

# Main route
@app.route('/')
def home():
    return render_template('index.html')

# Server time endpoint (UTC)
@app.route('/api/server_time')
def server_time():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return jsonify({'ok': True, 'server_time_utc': now.isoformat()})

# Run the application
if __name__ == '__main__':
    app.run(debug=True)
