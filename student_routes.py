from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from models import User, Exam, Question, Mark, Log, db
from utils import add_log, student_required, publish_event

student_bp = Blueprint('student', __name__)

@student_bp.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(username=username, role='student').first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session['student_logged_in'] = True
            session['student_id'] = user.id
            session['student_username'] = user.username
            add_log(user.id, user.username, 'student', 'student_login', {})
            return redirect(url_for('student.student_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('student_login.html')

@student_bp.route('/student/logout')
def student_logout():
    add_log(session.get('student_id'), session.get('student_username'), 'student', 'student_logout', {})
    session.clear()
    return redirect(url_for('student.student_login'))

@student_bp.route('/student/dashboard')
@student_required
def student_dashboard():
    # Render a dashboard page with list of exams
    return render_template('student_dashboard.html')

# API Routes
@student_bp.route('/api/student/exams', methods=['GET'])
@student_required
def api_student_exams():
    exams = Exam.query.filter_by(is_published=True).order_by(Exam.start_at.asc()).all()
    out = []
    for e in exams:
        out.append({
            'id': e.id,
            'title': e.title,
            'duration': e.duration_minutes,
            'start_at': e.start_at.isoformat() if e.start_at else None,
            'num_questions': e.num_questions
        })
    add_log(
        session.get('student_id'),
        session.get('student_username'),
        'student',
        'list_exams',
        {"count": len(out)}
    )
    return jsonify({'ok': True, 'exams': out})

@student_bp.route('/api/student/exam/<int:exam_id>', methods=['GET'])
@student_required
def api_student_exam_details(exam_id):
    exam = Exam.query.filter_by(id=exam_id, is_published=True).first()
    if not exam:
        return jsonify({'ok': False, 'msg': 'exam_not_found'}), 404

    # Enforce start time: do not reveal questions before start time if configured
    if exam.start_at:
        # Compare using local naive time to match teacher's naive start_at
        now = datetime.now()
        if exam.start_at and now < exam.start_at:
            add_log(session.get('student_id'), session.get('student_username'), 'student', 'exam_not_started', {'exam_id': exam.id, 'server_now': now.isoformat(), 'start_at': exam.start_at.isoformat()})
            return jsonify({'ok': False, 'msg': 'not_started', 'start_at': exam.start_at.isoformat(), 'server_now': now.isoformat()}), 403
        if exam.start_at and exam.duration_minutes:
            from datetime import timedelta
            if now > exam.start_at + timedelta(minutes=exam.duration_minutes):
                add_log(session.get('student_id'), session.get('student_username'), 'student', 'exam_time_over', {'exam_id': exam.id, 'server_now': now.isoformat(), 'start_at': exam.start_at.isoformat()})
                return jsonify({'ok': False, 'msg': 'time_over', 'start_at': exam.start_at.isoformat(), 'server_now': now.isoformat()}), 403

    questions = Question.query.filter_by(exam_id=exam.id).order_by(Question.created_at.asc()).all()
    qlist = []
    for q in questions:
        qlist.append({
            'id': q.id,
            'text': q.text,
            'options': {
                'A': q.option_a,
                'B': q.option_b,
                'C': q.option_c,
                'D': q.option_d
            },
            'points': q.points,
            'time_seconds': q.time_seconds
        })
    add_log(
        session.get('student_id'),
        session.get('student_username'),
        'student',
        'view_exam_details',
        {'exam_id': exam.id, 'num_questions': len(qlist)}
    )
    return jsonify({'ok': True, 'exam': {
        'id': exam.id,
        'title': exam.title,
        'duration': exam.duration_minutes,
        'start_at': exam.start_at.isoformat() if exam.start_at else None,
        'questions': qlist
    }})

@student_bp.route('/api/student/submit_exam', methods=['POST'])
@student_required
def api_student_submit_exam():
    data = request.json or request.form or {}
    exam_id = data.get('exam_id')
    answers = data.get('answers', {})  # {question_id: 'A'/'B'/'C'/'D'}
    cheating_count = int(data.get('cheating_count', 0)) if str(data.get('cheating_count', '0')).isdigit() else 0

    if not exam_id or not isinstance(answers, dict):
        return jsonify({'ok': False, 'msg': 'missing_data'}), 400

    exam = Exam.query.filter_by(id=exam_id, is_published=True).first()
    if not exam:
        return jsonify({'ok': False, 'msg': 'exam_not_found'}), 404

    # Calculate original marks
    original_marks = 0
    for qid_key, ans in answers.items():
        # Frontend sends keys like 'q<id>' (e.g., 'q12'). Normalize to integer ID.
        key_str = str(qid_key)
        if key_str.startswith('q'):
            key_str = key_str[1:]
        try:
            qid = int(key_str)
        except Exception:
            # Skip malformed keys
            continue
        q = Question.query.filter_by(id=qid, exam_id=exam.id).first()
        if not q:
            continue
        # Normalize student's selected option and correct option to uppercase single letters
        student_opt = (ans or '').strip().upper()
        correct_opt = (q.correct_option or '').strip().upper()
        original_marks += 1 if student_opt == correct_opt else 0

    # Apply cheating penalty logic (to match frontend UI expectations)
    penalty_flag = 2 if cheating_count >= 2 else (1 if cheating_count == 1 else 0)
    if penalty_flag >= 2:
        final_marks = 0
    elif penalty_flag == 1:
        final_marks = max(0, original_marks * 0.5)
    else:
        final_marks = original_marks

    # Save or update Mark (store final marks)
    m = Mark.query.filter_by(exam_id=exam.id, student_id=session.get('student_id')).first()
    if not m:
        m = Mark(exam_id=exam.id, student_id=session.get('student_id'), marks=final_marks, graded_at=datetime.utcnow(), cheating_count=cheating_count)
        db.session.add(m)
    else:
        m.marks = final_marks
        m.graded_at = datetime.utcnow()
        m.cheating_count = cheating_count
    db.session.commit()

    add_log(
        session.get('student_id'),
        session.get('student_username'),
        'student',
        'submit_exam',
        {'exam_id': exam.id, 'original_marks': original_marks, 'final_marks': final_marks, 'cheating_count': cheating_count}
    )

    # Additionally, record an explicit cheating event if any cheating was detected
    # so that teacher/admin can easily filter and view cheating incidents.
    if cheating_count and cheating_count > 0:
        add_log(
            session.get('student_id'),
            session.get('student_username'),
            'student',
            'cheating_detected',
            {'exam_id': exam.id, 'cheating_count': cheating_count}
        )

    # Publish event for teacher monitoring
    publish_event({'type': 'submit_exam', 'student_id': session.get('student_id'), 'student_username': session.get('student_username'), 'exam_id': exam.id, 'marks': final_marks, 'cheating_count': cheating_count, 'time': datetime.utcnow().isoformat()})

    return jsonify({'ok': True, 'total_marks': final_marks, 'original_marks': original_marks, 'cheating_penalty': penalty_flag})

@student_bp.route('/api/student/my_marks', methods=['GET'])
@student_required
def api_student_my_marks():
    """Return current student's marks per exam. The template expects exam_title and cheating_count fields."""
    sid = session.get('student_id')
    if not sid:
        return jsonify({'ok': False, 'msg': 'not_logged_in'}), 401
    marks = Mark.query.filter_by(student_id=sid).all()
    # Preload recent submit logs to backfill cheating_count if missing (e.g., old rows before migration)
    recent_logs = Log.query.filter_by(who_user_id=sid, event_type='submit_exam').order_by(Log.created_at.desc()).limit(200).all()
    out = []
    for m in marks:
        exam = Exam.query.get(m.exam_id)
        cheat_cnt = m.cheating_count if hasattr(m, 'cheating_count') else 0
        if not cheat_cnt:
            # Try to backfill from logs
            for lg in recent_logs:
                try:
                    if lg.meta and int(lg.meta.get('exam_id')) == int(m.exam_id):
                        cheat_cnt = int(lg.meta.get('cheating_count', 0))
                        break
                except Exception:
                    pass
        out.append({
            'exam_id': m.exam_id,
            'exam_title': exam.title if exam else f'Exam {m.exam_id}',
            'marks': m.marks,
            'cheating_count': cheat_cnt or 0
        })
    return jsonify({'ok': True, 'marks': out})

@student_bp.route('/api/student/event', methods=['POST'])
@student_required
def api_student_event():
    """Student-side event reporting for real-time monitoring (e.g., exam_start, cheating_detected)."""
    d = request.json or request.form or {}
    etype = (d.get('type') or '').strip()
    if not etype:
        return jsonify({'ok': False, 'msg': 'missing_type'}), 400
    meta = {k: v for k, v in d.items() if k != 'type'}
    ev = {
        'type': etype,
        'student_id': session.get('student_id'),
        'student_username': session.get('student_username'),
        'meta': meta,
        'time': datetime.utcnow().isoformat()
    }
    publish_event(ev)
    add_log(session.get('student_id'), session.get('student_username'), 'student', f'event_{etype}', meta)
    return jsonify({'ok': True})
