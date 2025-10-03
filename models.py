from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'teacher'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Log(db.Model):
    __tablename__ = 'logs'
    id = db.Column(db.Integer, primary_key=True)
    who_user_id = db.Column(db.Integer, nullable=True)         # optional user id who performed the action
    username = db.Column(db.String(120), nullable=True)
    role = db.Column(db.String(30), nullable=True)
    event_type = db.Column(db.String(120), nullable=False)
    meta = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Exam(db.Model):
    __tablename__ = 'exams'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False, default=60)
    start_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.Integer, nullable=True)  # teacher user id
    is_published = db.Column(db.Boolean, nullable=False, default=False)
    num_questions = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Mark(db.Model):
    __tablename__ = 'marks'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    marks = db.Column(db.Float, nullable=True)
    graded_at = db.Column(db.DateTime, nullable=True)
    cheating_count = db.Column(db.Integer, nullable=False, default=0)

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255), nullable=False)
    option_b = db.Column(db.String(255), nullable=False)
    option_c = db.Column(db.String(255), nullable=False)
    option_d = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)  # 'A','B','C','D'
    points = db.Column(db.Float, nullable=True)
    time_seconds = db.Column(db.Integer, nullable=True)  # per-question time
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
