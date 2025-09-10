import sqlite3
from db import get_db
from flask import current_app, session, flash, redirect, url_for, request, g
from functools import wraps
from datetime import datetime, timedelta

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
            return redirect(url_for('inventaire.index'))
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
            return redirect(url_for('inventaire.index'))
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
                return redirect(request.referrer or url_for('inventaire.index'))
        return f(*args, **kwargs)
    return decorated_function

def get_alerte_info(db):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    date_limite = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

    query_stock = """
            SELECT COUNT(*) FROM (
            SELECT 
                o.seuil,
                (o.quantite_physique - COALESCE(SUM(r.quantite_reservee), 0)) as quantite_disponible
            FROM objets o
            LEFT JOIN reservations r ON o.id = r.objet_id AND r.fin_reservation > ?
            WHERE o.en_commande = 0
            GROUP BY o.id
            HAVING quantite_disponible <= o.seuil
        )
    """
    count_stock = db.execute(query_stock, (now_str,)).fetchone()[0]

    count_peremption = db.execute(
        "SELECT COUNT(*) FROM objets WHERE date_peremption IS NOT NULL AND "
        "date_peremption < ? AND traite = 0", (date_limite, )).fetchone()[0]
    
    total_alertes = count_stock + count_peremption
    return {
        "alertes_stock": count_stock,
        "alertes_peremption": count_peremption,
        "alertes_total": total_alertes
    }

def get_items_per_page():
    # On vérifie si on a déjà chargé le paramètre pendant cette requête
    if 'items_per_page' not in g:
        db = get_db()
        param = db.execute("SELECT valeur FROM parametres WHERE cle = ?", ('items_per_page',)).fetchone()
        # Si le paramètre n'existe pas, on met une valeur sûre par défaut
        g.items_per_page = int(param['valeur']) if param else 10
    return g.items_per_page