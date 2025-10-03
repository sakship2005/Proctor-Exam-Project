from functools import wraps
from flask import session, redirect, url_for
from models import Log, db
import queue
import threading
import random
import time

# Simple in-memory pub/sub for real-time monitoring
_subscribers = []  # list of Queues
_subs_lock = threading.Lock()

def publish_event(event: dict):
    with _subs_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(event)
            except Exception:
                pass

def subscribe_events():
    q = queue.Queue()
    with _subs_lock:
        _subscribers.append(q)
    try:
        while True:
            ev = q.get()
            yield ev
    finally:
        with _subs_lock:
            if q in _subscribers:
                _subscribers.remove(q)

def add_log(who_id, username, role, event_type, meta=None):
    """Helper function to add log entries"""
    entry = Log(who_user_id=who_id, username=username, role=role, event_type=event_type, meta=meta or {})
    db.session.add(entry)
    db.session.commit()

def admin_required(fn):
    """Decorator to protect admin routes"""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return fn(*a, **kw)
    return wrapper

# ===== Distributed Systems Simulations =====
# Ricart–Agrawala mutual exclusion (simulated)
def simulate_ricart_agarwala(requests):
    """
    requests: list of tuples (node_id, timestamp)
    Returns an ordered list representing the critical section entry order and a log.
    """
    # Sort by (timestamp, node_id) to simulate total ordering
    ordered = sorted(requests, key=lambda x: (x[1], x[0]))
    log = []
    for node_id, ts in ordered:
        log.append({
            'event': 'enter_cs',
            'node': node_id,
            'timestamp': ts
        })
        # simulate work
        log.append({
            'event': 'exit_cs',
            'node': node_id,
            'timestamp': ts
        })
    return {'order': [n for n, _ in ordered], 'log': log}

# Load balancing / failover simulation
_primary_fail_ratio = 0.5  # 50% failure chance

def primary_process(payload):
    """Randomly fail to simulate overload/unstable primary."""
    if random.random() < _primary_fail_ratio:
        raise RuntimeError('primary_overloaded')
    return {'processor': 'primary', 'received': payload}

def backup_process(payload):
    return {'processor': 'backup', 'received': payload}

# Consistency simulation: leader/replica with lag
_leader_store = {}
_replica_store = {}
_replica_lag_seconds = 2
_replica_lock = threading.Lock()

def consistency_write(key, value):
    _leader_store[key] = value
    # schedule replication after lag
    def do_replicate():
        with _replica_lock:
            _replica_store[key] = value
    t = threading.Timer(_replica_lag_seconds, do_replicate)
    t.daemon = True
    t.start()
    return True

def consistency_read(mode, key):
    if mode == 'strong':
        return _leader_store.get(key)
    else:  # eventual
        with _replica_lock:
            return _replica_store.get(key)

def student_required(fn):
    """Decorator to protect student routes"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('student_logged_in'):
            return redirect(url_for('student_login'))
        return fn(*args, **kwargs)
    return wrapper

def teacher_required(fn):
    """Decorator to protect teacher routes"""
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get('teacher_logged_in'):
            return redirect(url_for('teacher_login'))
        return fn(*a, **kw)
    return wrapper
