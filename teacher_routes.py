import io
import csv
from datetime import datetime
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash, current_app, Response
from werkzeug.security import check_password_hash
from models import User, Exam, Question, Mark, Log, db
from utils import add_log, teacher_required, subscribe_events, simulate_ricart_agarwala, primary_process, backup_process, consistency_write, consistency_read

teacher_bp = Blueprint('teacher', __name__)

@teacher_bp.route('/teacher/login', methods=['GET','POST'])
def teacher_login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        user = User.query.filter_by(username=username, role='teacher').first()
        if user and check_password_hash(user.password_hash, password):
            session.clear()
            session['teacher_logged_in'] = True
            session['teacher_id'] = user.id
            session['teacher_username'] = user.username
            add_log(user.id, user.username, 'teacher', 'teacher_login', {})
            return redirect(url_for('teacher.teacher_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('teacher_login.html')

@teacher_bp.route('/teacher/logout')
def teacher_logout():
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'teacher_logout', {})
    session.clear()
    return redirect(url_for('teacher.teacher_login'))

@teacher_bp.route('/teacher/dashboard')
@teacher_required
def teacher_dashboard():
    return render_template('teacher_dashboard.html')

@teacher_bp.route('/api/teacher/cheating_logs', methods=['GET'])
@teacher_required
def api_teacher_cheating_logs():
    """Return recent cheating_detected logs for exams owned by this teacher.
    Since meta is stored as JSON and may not be efficiently filterable in SQLite,
    we fetch recent entries and filter in Python by checking exam ownership.
    """
    limit = request.args.get('limit', default=300, type=int)
    # Fetch recent cheating logs
    logs = Log.query.filter_by(event_type='cheating_detected').order_by(Log.created_at.desc()).limit(limit).all()
    teacher_id = session.get('teacher_id')
    out = []
    for lg in logs:
        try:
            exam_id = int(lg.meta.get('exam_id')) if lg.meta and 'exam_id' in lg.meta else None
        except Exception:
            exam_id = None
        if not exam_id:
            continue
        exam = Exam.query.get(exam_id)
        if not exam or exam.created_by != teacher_id:
            continue
        out.append({
            'id': lg.id,
            'student_id': lg.who_user_id,
            'student_username': lg.username,
            'exam_id': exam_id,
            'exam_title': exam.title,
            'cheating_count': (lg.meta or {}).get('cheating_count', 0),
            'created_at': lg.created_at.isoformat()
        })
    add_log(teacher_id, session.get('teacher_username'), 'teacher', 'view_cheating_logs', {'count': len(out)})
    return jsonify({'ok': True, 'logs': out})

# API Routes - Exam Management
@teacher_bp.route('/api/teacher/create_exam', methods=['POST'])
@teacher_required
def api_create_exam():
    data = request.form or request.json or {}
    title = data.get('title','').strip()
    duration = int(data.get('duration', 60))
    if not title:
        return jsonify({'ok': False, 'msg': 'missing_title'}), 400
    exam = Exam(title=title, duration_minutes=duration, created_by=session.get('teacher_id'))
    db.session.add(exam)
    db.session.commit()
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'create_exam', {'exam_id': exam.id})
    return jsonify({'ok': True, 'exam': {'id': exam.id, 'title': exam.title, 'duration': exam.duration_minutes}})

@teacher_bp.route('/api/teacher/exams', methods=['GET'])
@teacher_required
def api_list_exams():
    exams = Exam.query.filter_by(created_by=session.get('teacher_id')).order_by(Exam.created_at.desc()).all()
    out = []
    for e in exams:
        out.append({
            'id': e.id,
            'title': e.title,
            'duration': e.duration_minutes,   # frontend expects 'duration'
            'start_at': e.start_at.isoformat() if e.start_at else None,
            'num_questions': e.num_questions,
            'is_published': e.is_published
        })
    return jsonify({'ok': True, 'exams': out})

@teacher_bp.route('/api/teacher/update_exam', methods=['POST'])
@teacher_required
def api_update_exam():
    d = request.form or request.json or {}
    exam_id = d.get('exam_id')
    duration = d.get('duration')
    start_at = d.get('start_at')
    is_published = d.get('is_published')
    num_questions = d.get('num_questions')
    if not exam_id:
        return jsonify({'ok':False, 'msg':'missing_exam_id'}), 400
    try:
        exam_id = int(exam_id)
    except Exception:
        return jsonify({'ok':False, 'msg':'bad_exam_id'}), 400
    exam = Exam.query.get(exam_id)
    if not exam or exam.created_by != session.get('teacher_id'):
        return jsonify({'ok':False, 'msg':'not_found_or_forbidden'}), 404
    if duration:
        try:
            exam.duration_minutes = int(duration)
        except Exception:
            pass
    if num_questions is not None:
        try:
            exam.num_questions = int(num_questions)
        except Exception:
            pass
    if start_at:
        try:
            exam.start_at = datetime.fromisoformat(start_at)
        except Exception:
            pass
    if is_published is not None:
        # accept 'true'/'false' strings or boolean
        if isinstance(is_published, str):
            exam.is_published = is_published.lower() in ('1','true','yes')
        else:
            exam.is_published = bool(is_published)
    db.session.commit()
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'update_exam', {'exam_id': exam.id})
    return jsonify({'ok':True, 'exam': {'id': exam.id, 'duration': exam.duration_minutes, 'is_published': exam.is_published, 'num_questions': exam.num_questions}})

# API Routes - Question Management
@teacher_bp.route('/api/teacher/create_question', methods=['POST'])
@teacher_required
def api_create_question():
    d = request.form or request.json or {}
    exam_id = d.get('exam_id')
    text = d.get('text', '').strip()
    option_a = d.get('option_a', '').strip()
    option_b = d.get('option_b', '').strip()
    option_c = d.get('option_c', '').strip()
    option_d = d.get('option_d', '').strip()
    correct_option = d.get('correct_option', '').strip().upper()
    points = d.get('points')
    time_seconds = d.get('time_seconds')

    # Validate input
    if not exam_id or not text or not option_a or not option_b or not option_c or not option_d or correct_option not in ('A','B','C','D'):
        return jsonify({'ok': False, 'msg': 'missing_fields'}), 400

    try:
        exam_id = int(exam_id)
        points_val = float(points) if points not in (None, '') else None
        time_sec_val = int(time_seconds) if time_seconds not in (None, '') else None
    except Exception:
        return jsonify({'ok': False, 'msg': 'bad_types'}), 400

    exam = Exam.query.get(exam_id)
    if not exam or exam.created_by != session.get('teacher_id'):
        return jsonify({'ok': False, 'msg': 'exam_not_found_or_forbidden'}), 404

    # Save question
    q = Question(
        exam_id=exam_id,
        text=text,
        option_a=option_a,
        option_b=option_b,
        option_c=option_c,
        option_d=option_d,
        correct_option=correct_option,
        points=points_val,
        time_seconds=time_sec_val
    )
    db.session.add(q)
    db.session.commit()

    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'create_question',
            {'exam_id': exam_id, 'question_id': q.id})

    return jsonify({'ok': True, 'question': {
        'id': q.id,
        'text': q.text,
        'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
        'correct': q.correct_option,
        'points': q.points,
        'time_seconds': q.time_seconds
    }})

@teacher_bp.route('/api/teacher/questions', methods=['GET'])
@teacher_required
def api_list_questions():
    exam_id = request.args.get('exam_id', type=int)
    if not exam_id:
        return jsonify({'ok': False, 'msg': 'missing_exam_id'}), 400

    exam = Exam.query.get(exam_id)
    if not exam or exam.created_by != session.get('teacher_id'):
        return jsonify({'ok': False, 'msg': 'exam_not_found_or_forbidden'}), 404

    qs = Question.query.filter_by(exam_id=exam_id).order_by(Question.created_at.asc()).all()
    out = [{
        'id': q.id,
        'text': q.text,
        'options': {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d},
        'correct': q.correct_option,
        'points': q.points,
        'time_seconds': q.time_seconds
    } for q in qs]

    return jsonify({'ok': True, 'questions': out})

# API Routes - Marks Management
@teacher_bp.route('/api/teacher/exams_for_marks', methods=['GET'])
@teacher_required
def api_exams_for_marks():
    exams = Exam.query.filter_by(created_by=session.get('teacher_id')).order_by(Exam.created_at.desc()).all()
    out = [{'id':e.id, 'title':e.title, 'is_published': e.is_published, 'num_questions': e.num_questions} for e in exams]
    return jsonify({'ok':True, 'exams': out})

@teacher_bp.route('/api/teacher/set_mark', methods=['POST'])
@teacher_required
def api_set_mark():
    d = request.form or request.json or {}
    exam_id = d.get('exam_id')
    student_id = d.get('student_id')
    marks = d.get('marks')
    if not exam_id or not student_id:
        return jsonify({'ok':False, 'msg':'missing_ids'}), 400
    try:
        exam_id = int(exam_id); student_id = int(student_id)
        marks_val = float(marks) if marks is not None and str(marks) != '' else None
    except Exception:
        return jsonify({'ok':False, 'msg':'bad_types'}), 400
    # Ensure the exam belongs to the logged-in teacher
    exam = Exam.query.get(exam_id)
    if not exam or exam.created_by != session.get('teacher_id'):
        return jsonify({'ok': False, 'msg': 'exam_not_found_or_forbidden'}), 403
    # Optional validation: marks must be non-negative if provided
    if marks_val is not None and marks_val < 0:
        return jsonify({'ok': False, 'msg': 'marks_must_be_non_negative'}), 400
    mark = Mark.query.filter_by(exam_id=exam_id, student_id=student_id).first()
    if not mark:
        mark = Mark(exam_id=exam_id, student_id=student_id, marks=marks_val, graded_at=(datetime.utcnow() if marks_val is not None else None))
        db.session.add(mark)
    else:
        mark.marks = marks_val
        mark.graded_at = (datetime.utcnow() if marks_val is not None else None)
    db.session.commit()
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'set_mark', {'exam_id': exam_id, 'student_id': student_id, 'marks': marks_val})
    return jsonify({'ok':True})

@teacher_bp.route('/api/teacher/exam_marks', methods=['GET'])
@teacher_required
def api_exam_marks():
    exam_id = request.args.get('exam_id', type=int)
    if not exam_id:
        return jsonify({'ok':False, 'msg':'missing_exam_id'}), 400
    # join students
    marks = Mark.query.filter_by(exam_id=exam_id).all()
    out = []
    for m in marks:
        student = User.query.get(m.student_id)
        out.append({'id': m.id, 'student_id': m.student_id, 'student_username': student.username if student else None, 'marks': m.marks, 'graded_at': m.graded_at.isoformat() if m.graded_at else None})
    return jsonify({'ok':True, 'marks': out})

@teacher_bp.route('/api/teacher/exam_marks_csv', methods=['GET'])
@teacher_required
def api_exam_marks_csv():
    exam_id = request.args.get('exam_id', type=int)
    if not exam_id:
        return jsonify({'ok':False, 'msg':'missing_exam_id'}), 400
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['student_id','student_username','marks','graded_at'])
    marks = Mark.query.filter_by(exam_id=exam_id).all()
    for m in marks:
        student = User.query.get(m.student_id)
        writer.writerow([m.student_id, student.username if student else '', '' if m.marks is None else m.marks, '' if not m.graded_at else m.graded_at.isoformat()])
    resp = current_app.response_class(output.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename=exam_{exam_id}_marks.csv'
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'download_csv', {'exam_id': exam_id})
    return resp

# Real-time monitoring stream (SSE)
@teacher_bp.route('/api/teacher/monitor_stream')
@teacher_required
def api_teacher_monitor_stream():
    def event_stream():
        for ev in subscribe_events():
            import json
            yield f"data: {json.dumps(ev)}\n\n"
    headers = {'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive'}
    return Response(event_stream(), headers=headers)

# ===== DS Demo Endpoints =====

@teacher_bp.route('/api/teacher/rpc_ping', methods=['GET'])
@teacher_required
def api_rpc_ping():
    try:
        import xmlrpc.client
        proxy = xmlrpc.client.ServerProxy('http://127.0.0.1:9000', allow_none=True)
        res = proxy.ping()
        add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'rpc_ping', {'result': res})
        return jsonify({'ok': True, 'result': res})
    except Exception as e:
        add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'rpc_ping_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500

@teacher_bp.route('/api/teacher/rpc_record_event', methods=['POST'])
@teacher_required
def api_rpc_record_event():
    d = request.json or request.form or {}
    try:
        import xmlrpc.client
        proxy = xmlrpc.client.ServerProxy('http://127.0.0.1:9000', allow_none=True)
        ok = proxy.record_event({
            'teacher_id': session.get('teacher_id'),
            'teacher_username': session.get('teacher_username'),
            'event': d.get('event') or 'test_event'
        })
        add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'rpc_record_event', {'stored': bool(ok), 'event': d.get('event')})
        return jsonify({'ok': True, 'stored': bool(ok)})
    except Exception as e:
        add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'rpc_record_event_error', {'error': str(e)})
        return jsonify({'ok': False, 'error': str(e)}), 500

@teacher_bp.route('/api/teacher/ricart_agarwala', methods=['POST'])
@teacher_required
def api_ricart_agarwala():
    d = request.json or request.form or {}
    # Expect requests as list of {node_id:int, timestamp:int}
    reqs = d.get('requests') or []
    try:
        parsed = [(int(item['node_id']), int(item['timestamp'])) for item in reqs]
    except Exception:
        return jsonify({'ok': False, 'msg': 'bad_requests'}), 400
    res = simulate_ricart_agarwala(parsed)
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'ricart_agarwala', {'order': res['order']})
    return jsonify({'ok': True, 'order': res['order'], 'log': res['log']})

@teacher_bp.route('/api/teacher/lb_process', methods=['POST'])
@teacher_required
def api_lb_process():
    d = request.json or request.form or {}
    payload = d.get('payload') or {}
    # Try primary; on failure, fallback to backup
    try:
        out = primary_process(payload)
        add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'lb_primary', {'payload': payload})
        return jsonify({'ok': True, 'path': 'primary', 'result': out})
    except Exception as e:
        try:
            out = backup_process(payload)
            add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'lb_backup', {'payload': payload, 'primary_error': str(e)})
            return jsonify({'ok': True, 'path': 'backup', 'result': out, 'primary_error': str(e)})
        except Exception as e2:
            add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'lb_error', {'payload': payload, 'primary_error': str(e), 'backup_error': str(e2)})
            return jsonify({'ok': False, 'error': str(e2), 'primary_error': str(e)}), 500

@teacher_bp.route('/api/teacher/consistency_write', methods=['POST'])
@teacher_required
def api_consistency_write():
    d = request.json or request.form or {}
    key = (d.get('key') or '').strip()
    value = d.get('value')
    if not key:
        return jsonify({'ok': False, 'msg': 'missing_key'}), 400
    consistency_write(key, value)
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'consistency_write', {'key': key, 'value': value})
    return jsonify({'ok': True})

@teacher_bp.route('/api/teacher/consistency_read', methods=['GET'])
@teacher_required
def api_consistency_read():
    key = request.args.get('key', '').strip()
    mode = request.args.get('mode', 'eventual')
    if not key:
        return jsonify({'ok': False, 'msg': 'missing_key'}), 400
    val = consistency_read(mode, key)
    add_log(session.get('teacher_id'), session.get('teacher_username'), 'teacher', 'consistency_read', {'key': key, 'mode': mode, 'value': val})
    return jsonify({'ok': True, 'mode': mode, 'key': key, 'value': val})
