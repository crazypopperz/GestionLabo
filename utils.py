import sqlite3
from db import get_db
from flask import current_app
from flask import session, flash, redirect, url_for, request
from functools import wraps

def is_setup_needed(app):
    try:
        with app.app_context():
            db = get_db()
            user = db.execute("SELECT id FROM utilisateurs LIMIT 1").fetchone()
            return user is None
    except (sqlite3.OperationalError, RuntimeError):
        return True

# --- DÉCORATEURS DE SÉCURITÉ ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("Veuillez vous connecter pour accéder à cette page.", "error")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('user_role') != 'admin':
            flash("Accès réservé aux administrateurs.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def pro_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db = get_db()
        try:
            licence_row = db.execute("SELECT valeur FROM parametres WHERE cle = ?", ('licence_statut', )).fetchone()
            is_pro = licence_row and licence_row['valeur'] == 'PRO'
        except sqlite3.Error:
            is_pro = False
        if not is_pro:
            flash("Cette fonctionnalité est réservée à la version Pro.", "warning")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def limit_objets_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        db = get_db()
        licence_row = db.execute("SELECT valeur FROM parametres WHERE cle = ?", ('licence_statut', )).fetchone()
        is_pro = licence_row and licence_row['valeur'] == 'PRO'
        if not is_pro:
            count = db.execute("SELECT COUNT(id) FROM objets").fetchone()[0]
            if count >= 50:
                flash("La version gratuite est limitée à 50 objets. Passez à la version Pro pour en ajouter davantage.", "warning")
                return redirect(request.referrer or url_for('index'))
        return f(*args, **kwargs)
    return decorated_function