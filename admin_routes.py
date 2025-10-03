from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from models import User, Log, db
from utils import add_log, admin_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        if username == 'admin' and password == 'admin':
            session['admin_logged_in'] = True
            session['admin_username'] = 'admin'
            add_log(None, 'admin', 'admin', 'admin_login', {'msg': 'admin logged in'})
            return redirect(url_for('admin.admin_dashboard'))
        flash('Invalid admin credentials', 'danger')
    return render_template('admin_login.html')

@admin_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    return render_template('admin_dashboard.html')

@admin_bp.route('/admin/logout')
def admin_logout():
    add_log(None, session.get('admin_username'), 'admin', 'admin_logout', {})
    session.clear()
    return redirect(url_for('admin.admin_login'))

# API Routes
@admin_bp.route('/api/admin/create_user', methods=['POST'])
@admin_required
def api_create_user():
    d = request.form or request.json or {}
    username = d.get('username','').strip()
    password = d.get('password','').strip()
    role = d.get('role','').strip()
    if not username or not password or role not in ('student','teacher'):
        return jsonify({"ok":False, "msg":"bad_payload"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"ok":False, "msg":"username_exists"}), 409
    user = User(username=username, password_hash=generate_password_hash(password), role=role)
    db.session.add(user)
    db.session.commit()
    add_log(None, session.get('admin_username'), 'admin', 'create_user', {"new_user": username, "role": role})
    return jsonify({"ok":True, "user": {"id": user.id, "username": user.username, "role": user.role}})

@admin_bp.route('/api/admin/students', methods=['GET'])
@admin_required
def api_list_students():
    users = User.query.filter_by(role='student').order_by(User.created_at.desc()).all()
    out = [{"id":u.id, "username":u.username, "created_at":u.created_at.isoformat()} for u in users]
    add_log(None, session.get('admin_username'), 'admin', 'list_students', {"count": len(out)})
    return jsonify({"ok":True, "students": out})

@admin_bp.route('/api/admin/teachers', methods=['GET'])
@admin_required
def api_list_teachers():
    users = User.query.filter_by(role='teacher').order_by(User.created_at.desc()).all()
    out = [{"id":u.id, "username":u.username, "created_at":u.created_at.isoformat()} for u in users]
    add_log(None, session.get('admin_username'), 'admin', 'list_teachers', {"count": len(out)})
    return jsonify({"ok":True, "teachers": out})

@admin_bp.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_view_logs():
    q = Log.query
    etype = request.args.get('event_type')
    uid = request.args.get('user_id', type=int)
    cheating_only = request.args.get('cheating_only')
    if etype:
        q = q.filter_by(event_type=etype)
    if uid:
        q = q.filter_by(who_user_id=uid)
    if cheating_only and str(cheating_only).lower() in ('1','true','yes'):
        q = q.filter_by(event_type='cheating_detected')
    logs = q.order_by(Log.created_at.desc()).limit(2000).all()
    out = []
    for l in logs:
        out.append({
            "id": l.id,
            "who_user_id": l.who_user_id,
            "username": l.username,
            "role": l.role,
            "event_type": l.event_type,
            "meta": l.meta,
            "created_at": l.created_at.isoformat()
        })
    add_log(None, session.get('admin_username'), 'admin', 'view_logs', {"count": len(out), "filter_event": etype, "cheating_only": bool(cheating_only)})
    return jsonify({"ok":True, "logs": out})
