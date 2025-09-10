# ============================================================
# IMPORTS
# ============================================================

# Imports depuis la bibliothèque standard
import math
import os
import sqlite3
import uuid
from datetime import datetime, date, timedelta

# Imports depuis les bibliothèques tierces (Flask)
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, jsonify, send_file, current_app)
from werkzeug.utils import secure_filename

# Imports depuis nos propres modules
from db import get_db
from utils import login_required, admin_required, limit_objets_required, get_alerte_info, get_items_per_page

# =============================================================
# APPEL A LA PAGINATION
# =============================================================
def get_paginated_objets(db,
                         page,
                         sort_by='nom',
                         direction='asc',
                         search_query=None,
                         armoire_id=None,
                         categorie_id=None,
                         etat=None,
                         filter_field=None,
                         filter_id=None):
    items_per_page = get_items_per_page()
    offset = (page - 1) * items_per_page
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    base_query = """
    SELECT 
    o.id, o.nom, o.quantite_physique, o.seuil, o.armoire_id, o.categorie_id,
    o.fds_nom_original, o.fds_nom_securise,
    a.nom AS armoire, c.nom AS categorie, o.image, o.en_commande,
    o.date_peremption,
    (o.quantite_physique - COALESCE(SUM(r.quantite_reservee), 0)) as quantite_disponible
    FROM objets o
    JOIN armoires a ON o.armoire_id = a.id
    JOIN categories c ON o.categorie_id = c.id
    LEFT JOIN reservations r ON o.id = r.objet_id AND r.fin_reservation > ?
    """
    conditions = []
    params = [now_str]
    
    if filter_field and filter_id:
        conditions.append(f"o.{filter_field} = ?")
        params.append(filter_id)

    if search_query:
        conditions.append("unaccent(LOWER(o.nom)) LIKE unaccent(LOWER(?))")
        params.append(f"%{search_query}%")

    if armoire_id:
        conditions.append("o.armoire_id = ?")
        params.append(armoire_id)

    if categorie_id:
        conditions.append("o.categorie_id = ?")
        params.append(categorie_id)

    if conditions:
        base_query += " WHERE " + " AND ".join(conditions)
    
    base_query += " GROUP BY o.id"

    if etat:
        date_limite_peremption = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        current_date = now_str.split(' ')[0]
        having_conditions = []

        if etat == 'perime':
            having_conditions.append("o.date_peremption < ?")
            params.append(current_date)
        elif etat == 'bientot':
            having_conditions.append("o.date_peremption >= ? AND o.date_peremption < ?")
            params.extend([current_date, date_limite_peremption])
        elif etat == 'stock':
            having_conditions.append("quantite_disponible <= o.seuil")
        elif etat == 'ok':
            having_conditions.append("quantite_disponible > o.seuil AND (o.date_peremption IS NULL OR o.date_peremption >= ?)")
            params.append(date_limite_peremption)
        
        if having_conditions:
            base_query += " HAVING " + " AND ".join(having_conditions)

    all_results = db.execute(base_query, params).fetchall()
    total_objets = len(all_results)
    total_pages = math.ceil(total_objets / items_per_page) if items_per_page > 0 else 0

    valid_sort_columns = {
        'nom': 'o.nom', 'quantite': 'quantite_disponible', 'seuil': 'o.seuil',
        'date_peremption': 'o.date_peremption', 'categorie': 'c.nom', 'armoire': 'a.nom'
    }
    sort_column = valid_sort_columns.get(sort_by, 'o.nom')
    sort_direction = 'DESC' if direction == 'desc' else 'ASC'
    
    base_query += f" ORDER BY {sort_column} {sort_direction}, o.nom ASC"
    base_query += " LIMIT ? OFFSET ?"
    params.extend([items_per_page, offset])

    objets = db.execute(base_query, params).fetchall()
    return objets, total_pages


def enregistrer_action(objet_id, action, details=""):
    if 'user_id' in session:
        db = get_db()
        try:
            db.execute(
                """INSERT INTO historique (objet_id, utilisateur_id, action,
                   details, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (objet_id, session['user_id'], action, details,
                 datetime.now()))
            db.commit()
        except sqlite3.Error as e:
            print(f"ERREUR LORS DE L'ENREGISTREMENT DE L'HISTORIQUE : {e}")
            db.rollback()
# ============================================================
# CRÉATION DU BLUEPRINT POUR L'INVENTAIRE
# ============================================================
inventaire_bp = Blueprint(
    'inventaire', 
    __name__,
    template_folder='../templates'
)

# ============================================================
# LES FONCTIONS DE ROUTES SERONT COLLÉES ICI
# ============================================================
@inventaire_bp.route("/")
@login_required
def index():
    db = get_db()
    dashboard_data = {}

    if session.get('user_role') == 'admin':
        dashboard_data['stats'] = {
            'total_objets': db.execute("SELECT COUNT(*) FROM objets").fetchone()[0],
            'total_utilisateurs': db.execute("SELECT COUNT(*) FROM utilisateurs").fetchone()[0],
            'reservations_actives': db.execute("SELECT COUNT(DISTINCT groupe_id) FROM reservations WHERE debut_reservation >= ?", (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), )).fetchone()[0]
        }
    
    now = datetime.now()
    annee_scolaire_actuelle = now.year if now.month >= 8 else now.year - 1
    budget_actuel = db.execute("SELECT * FROM budgets WHERE annee = ? AND cloture = 0", (annee_scolaire_actuelle, )).fetchone()
    solde_actuel = None
    if budget_actuel:
        total_depenses_result = db.execute("SELECT SUM(montant) as total FROM depenses WHERE budget_id = ?", (budget_actuel['id'], )).fetchone()
        total_depenses = (total_depenses_result['total'] if total_depenses_result['total'] is not None else 0)
        solde_actuel = budget_actuel['montant_initial'] - total_depenses
    dashboard_data['solde_budget'] = solde_actuel

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    dashboard_data['reservations'] = db.execute(
        """
        SELECT groupe_id, debut_reservation, COUNT(objet_id) as item_count
        FROM reservations
        WHERE utilisateur_id = ? AND datetime(debut_reservation) >= datetime(?)
        GROUP BY groupe_id
        ORDER BY debut_reservation ASC
        LIMIT 5
        """, (session['user_id'], now_str)).fetchall()

    dashboard_data['alertes_widget'] = get_alerte_info(db)

    recent_reservations = db.execute("""
        SELECT groupe_id, debut_reservation as timestamp
        FROM reservations
        WHERE utilisateur_id = ?
        GROUP BY groupe_id
        ORDER BY debut_reservation DESC
        LIMIT 5
    """, (session['user_id'],)).fetchall()

    other_actions = db.execute("""
        SELECT action, timestamp, details, o.nom as objet_nom
        FROM historique h
        JOIN objets o ON h.objet_id = o.id
        WHERE h.utilisateur_id = ? AND action NOT LIKE '%Réservation%'
        ORDER BY h.timestamp DESC
        LIMIT 5
    """, (session['user_id'],)).fetchall()

    all_actions = [dict(r) for r in recent_reservations] + [dict(a) for a in other_actions]
    all_actions.sort(key=lambda x: datetime.fromisoformat(x['timestamp']), reverse=True)
    top_5_actions = all_actions[:5]

    historique_enrichi = []
    for action in top_5_actions:
        entry = {'timestamp': action['timestamp']}
        if 'groupe_id' in action: 
            entry['type'] = 'reservation'
            entry['action'] = 'Réservation'
            
            items_reserves = db.execute("""
                SELECT r.quantite_reservee, o.nom as objet_nom, r.kit_id, k.nom as kit_nom
                FROM reservations r
                JOIN objets o ON r.objet_id = o.id
                LEFT JOIN kits k ON r.kit_id = k.id
                WHERE r.groupe_id = ?
            """, (action['groupe_id'],)).fetchall()
            
            kits = {}
            objets_manuels = {}
            for item in items_reserves:
                if item['kit_id']:
                    if item['kit_id'] not in kits:
                        kit_objets = db.execute("SELECT o.nom, ko.quantite FROM kit_objets ko JOIN objets o ON ko.objet_id = o.id WHERE ko.kit_id = ?", (item['kit_id'],)).fetchall()
                        kits[item['kit_id']] = {'nom': item['kit_nom'], 'contenu': [f"{k['quantite']}x {k['nom']}" for k in kit_objets]}
                else:
                    objets_manuels[item['objet_nom']] = objets_manuels.get(item['objet_nom'], 0) + item['quantite_reservee']
            
            entry['kits'] = list(kits.values())
            entry['objets_manuels'] = [f"{qty}x {name}" for name, qty in objets_manuels.items()]
        else: 
            entry['type'] = 'autre'
            entry['action'] = action['action']
            entry['details'] = f"{action['objet_nom']}"

        historique_enrichi.append(entry)

    dashboard_data['historique_recent'] = historique_enrichi
    
    vingt_quatre_heures_avant = datetime.now() - timedelta(hours=24)
    dashboard_data['objets_recents'] = db.execute(
        """
        SELECT o.id, o.nom FROM objets o
        WHERE o.id IN (
            SELECT objet_id FROM historique
            WHERE (action = 'Création' OR (action = 'Modification' AND details LIKE '%Quantité%'))
            AND timestamp >= ?
            GROUP BY objet_id ORDER BY MAX(timestamp) DESC
        ) LIMIT 10
        """, (vingt_quatre_heures_avant.strftime('%Y-%m-%d %H:%M:%S'), )).fetchall()

    admin_user = db.execute("SELECT nom_utilisateur, email FROM utilisateurs WHERE role = 'admin' LIMIT 1").fetchone()
    if admin_user and admin_user['email']:
        dashboard_data['admin_contact'] = admin_user['email']
    elif admin_user:
        dashboard_data['admin_contact'] = admin_user['nom_utilisateur']
    else:
        dashboard_data['admin_contact'] = "Non défini"

    date_limite_echeances = datetime.now().date() + timedelta(days=30)
    date_aujourdhui = datetime.now().date()
    echeances_brutes = db.execute(
        """
        SELECT id, intitule, date_echeance
        FROM echeances
        WHERE traite = 0 AND date_echeance >= ? AND date_echeance <= ?
        ORDER BY date_echeance ASC
        LIMIT 5
        """, (date_aujourdhui.strftime('%Y-%m-%d'), date_limite_echeances.strftime('%Y-%m-%d'))).fetchall()

    prochaines_echeances_calculees = []
    for echeance in echeances_brutes:
        echeance_dict = dict(echeance)
        date_echeance_obj = datetime.strptime(echeance['date_echeance'], '%Y-%m-%d').date()
        jours_restants = (date_echeance_obj - date_aujourdhui).days
        echeance_dict['date_echeance_obj'] = date_echeance_obj
        echeance_dict['jours_restants'] = jours_restants
        prochaines_echeances_calculees.append(echeance_dict)
    dashboard_data['prochaines_echeances'] = prochaines_echeances_calculees

    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()

    return render_template("index.html",
                           data=dashboard_data,
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)

@inventaire_bp.route("/inventaire")
@login_required
def inventaire():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'nom')
    direction = request.args.get('direction', 'asc')
    search_query = request.args.get('q', None)
    armoire_id = request.args.get('armoire', None)
    categorie_id = request.args.get('categorie', None)
    etat = request.args.get('etat', None)

    objets, total_pages = get_paginated_objets(db,
                                               page,
                                               sort_by=sort_by,
                                               direction=direction,
                                               search_query=search_query,
                                               armoire_id=armoire_id,
                                               categorie_id=categorie_id,
                                               etat=etat)

    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'endpoint': 'inventaire.inventaire',
        'id': None
    }

    return render_template("inventaire.html",
                           armoires=armoires,
                           categories=categories,
                           objets=objets,
                           pagination=pagination,
                           date_actuelle=datetime.now(),
                           now=datetime.now,
                           sort_by=sort_by,
                           direction=direction)

@inventaire_bp.route("/api/inventaire/")
@login_required
def api_inventaire():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'nom')
    direction = request.args.get('direction', 'asc')
    search_query = request.args.get('q', None)
    armoire_id = request.args.get('armoire', None)
    categorie_id = request.args.get('categorie', None)
    etat = request.args.get('etat', None)

    objets, total_pages = get_paginated_objets(db, page, sort_by, direction,
                                               search_query, armoire_id,
                                               categorie_id, etat)
    pagination = {'page': page, 'total_pages': total_pages, 'endpoint': 'inventaire.inventaire', 'id': None}
    
    html = render_template('_inventaire_content.html', objets=objets, pagination=pagination, date_actuelle=datetime.now(), sort_by=sort_by, direction=direction, session=session)
    return jsonify(html=html)

@inventaire_bp.route("/objet/<int:objet_id>")
@login_required
def voir_objet(objet_id):
    db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    objet = db.execute(
        """SELECT
            o.*, a.nom as armoire_nom, c.nom as categorie_nom,
            (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) 
                                             FROM reservations r 
                                             WHERE r.objet_id = o.id AND r.fin_reservation > ?), 0)) as quantite_disponible
           FROM objets o
           JOIN armoires a ON o.armoire_id = a.id
           JOIN categories c ON o.categorie_id = c.id
           WHERE o.id = ?""", (now_str, objet_id, )).fetchone()
    
    if not objet:
        flash("Objet non trouvé.", "error")
        return redirect(url_for('inventaire.index'))

    historique = db.execute(
        "SELECT h.*, u.nom_utilisateur FROM historique h "
        "JOIN utilisateurs u ON h.utilisateur_id = u.id "
        "WHERE h.objet_id = ? ORDER BY h.timestamp DESC",
        (objet_id, )).fetchall()

    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()

    return render_template("objet_details.html",
                           objet=objet,
                           historique=historique,
                           armoires=armoires,
                           categories=categories,
                           date_actuelle=datetime.now(),
                           now=datetime.now)

@inventaire_bp.route("/armoire/<int:id>")
@login_required
def voir_armoire(id):
    db = get_db()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'nom')
    direction = request.args.get('direction', 'asc')

    armoire = db.execute("SELECT * FROM armoires WHERE id = ?",
                         (id, )).fetchone()
    if not armoire:
        flash("Armoire non trouvée.", "error")
        return redirect(url_for('inventaire.index'))

    objets, total_pages = get_paginated_objets(db,
                                               page,
                                               sort_by=sort_by,
                                               direction=direction,
                                               filter_field='armoire_id',
                                               filter_id=id)

    armoires_list = db.execute(
        "SELECT * FROM armoires ORDER BY nom").fetchall()
    categories_list = db.execute(
        "SELECT * FROM categories ORDER BY nom").fetchall()

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'endpoint': 'inventaire.voir_armoire',
        'id': id
    }

    return render_template("armoire.html",
                           armoire=armoire,
                           objets=objets,
                           armoires=armoires_list,
                           categories=categories_list,
                           armoires_list=armoires_list,
                           categories_list=categories_list,
                           pagination=pagination,
                           date_actuelle=datetime.now(),
                           now=datetime.now,
                           sort_by=sort_by,
                           direction=direction)


@inventaire_bp.route("/categorie/<int:id>")
@login_required
def voir_categorie(id):
    db = get_db()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'nom')
    direction = request.args.get('direction', 'asc')

    categorie = db.execute("SELECT * FROM categories WHERE id = ?",
                           (id, )).fetchone()
    if not categorie:
        flash("Catégorie non trouvée.", "error")
        return redirect(url_for('inventaire.index'))

    objets, total_pages = get_paginated_objets(db,
                                               page,
                                               sort_by,
                                               direction,
                                               filter_field='categorie_id',
                                               filter_id=id)

    armoires_list = db.execute(
        "SELECT * FROM armoires ORDER BY nom").fetchall()
    categories_list = db.execute(
        "SELECT * FROM categories ORDER BY nom").fetchall()

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'endpoint': 'inventaire.voir_categorie',
        'id': id
    }

    return render_template("categorie.html",
                           categorie=categorie,
                           objets=objets,
                           armoires=armoires_list,
                           categories=categories_list,
                           armoires_list=armoires_list,
                           categories_list=categories_list,
                           pagination=pagination,
                           date_actuelle=datetime.now(),
                           now=datetime.now,
                           sort_by=sort_by,
                           direction=direction)

@inventaire_bp.route("/ajouter_objet", methods=["POST"])
@login_required
@limit_objets_required
def ajouter_objet():
    nom = request.form.get("nom", "").strip()
    quantite = request.form.get("quantite")
    seuil = request.form.get("seuil")
    armoire_id = request.form.get("armoire_id")
    categorie_id = request.form.get("categorie_id")
    date_peremption = request.form.get("date_peremption")
    date_peremption_db = date_peremption if date_peremption else None

    image_name = ""
    if 'image' in request.files:
        image = request.files['image']
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            image_name = filename

    fds_nom_original = None
    fds_nom_securise = None
    if 'fds_file' in request.files:
        fds_file = request.files['fds_file']
        if fds_file and fds_file.filename != '':
            fds_nom_original = fds_file.filename
            fds_nom_securise = str(uuid.uuid4()) + '_' + secure_filename(fds_nom_original)
            if not os.path.exists(current_app.config['FDS_UPLOAD_FOLDER']):
                os.makedirs(current_app.config['FDS_UPLOAD_FOLDER'])
            fds_file.save(os.path.join(current_app.config['FDS_UPLOAD_FOLDER'], fds_nom_securise))

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """INSERT INTO objets (nom, quantite_physique, seuil, armoire_id, categorie_id,
                               image, en_commande, date_peremption, traite,
                               fds_nom_original, fds_nom_securise)
           VALUES (?, ?, ?, ?, ?, ?, 0, ?, 0, ?, ?)""",
        (nom, quantite, seuil, armoire_id, categorie_id, image_name,
         date_peremption_db, fds_nom_original, fds_nom_securise))
    new_objet_id = cursor.lastrowid
    db.commit()
    details_str = f"Créé avec quantité physique {quantite} et seuil {seuil}."
    enregistrer_action(new_objet_id, "Création", details_str)
    flash(f"L'objet '{nom}' a été ajouté avec succès !", "success")
    return redirect(request.referrer or url_for('inventaire.index'))

@inventaire_bp.route("/modifier_objet/<int:id_objet>", methods=["POST"])
@login_required
def modifier_objet(id_objet):
    db = get_db()
    objet_avant = db.execute("SELECT * FROM objets WHERE id = ?", (id_objet, )).fetchone()
    if not objet_avant:
        flash("Objet non trouvé.", "error")
        return redirect(request.referrer or url_for('inventaire.index'))

    nom = request.form.get("nom", "").strip()
    quantite_physique = int(request.form.get("quantite")) # Le champ s'appelle 'quantite' dans le form
    seuil = int(request.form.get("seuil"))
    armoire_id = int(request.form.get("armoire_id"))
    categorie_id = int(request.form.get("categorie_id"))
    date_peremption = request.form.get("date_peremption")
    date_peremption_db = date_peremption if date_peremption else None
    image_name = objet_avant['image']

    if request.form.get('supprimer_image'):
        if image_name:
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], image_name))
            except OSError: pass
        image_name = ""
    
    if 'image' in request.files:
        nouvelle_image = request.files['image']
        if nouvelle_image and nouvelle_image.filename != '':
            if image_name:
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], image_name))
                except OSError: pass
            filename = secure_filename(nouvelle_image.filename)
            nouvelle_image.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
            image_name = filename

    fds_nom_original = objet_avant['fds_nom_original']
    fds_nom_securise = objet_avant['fds_nom_securise']
    if 'fds_file' in request.files:
        nouvelle_fds = request.files['fds_file']
        if nouvelle_fds and nouvelle_fds.filename != '':
            if fds_nom_securise:
                try:
                    os.remove(os.path.join(current_app.config['FDS_UPLOAD_FOLDER'], fds_nom_securise))
                except OSError:
                    pass
            fds_nom_original = nouvelle_fds.filename
            fds_nom_securise = str(uuid.uuid4()) + '_' + secure_filename(fds_nom_original)
            nouvelle_fds.save(os.path.join(current_app.config['FDS_UPLOAD_FOLDER'], fds_nom_securise))

    details = []
    if objet_avant['quantite_physique'] != quantite_physique:
        details.append(f"Quantité physique: {objet_avant['quantite_physique']} -> {quantite_physique}")
    if objet_avant['fds_nom_original'] != fds_nom_original:
        details.append("FDS modifiée")

    details_str = ", ".join(details) if details else "Mise à jour des informations."

    db.execute(
        """
        UPDATE objets SET nom = ?, quantite_physique = ?, seuil = ?, armoire_id = ?,
                         categorie_id = ?, image = ?, date_peremption = ?,
                         fds_nom_original = ?, fds_nom_securise = ?
        WHERE id = ?
        """,
        (nom, quantite_physique, seuil, armoire_id, categorie_id, image_name,
         date_peremption_db, fds_nom_original, fds_nom_securise, id_objet))
    db.commit()

    enregistrer_action(id_objet, "Modification", details_str)
    flash(f"L'objet '{nom}' a été mis à jour avec succès !", "success")
    return redirect(request.referrer or url_for('inventaire.index'))

@inventaire_bp.route("/objet/supprimer/<int:id_objet>", methods=["POST"])
@admin_required
def supprimer_objet(id_objet):
    """Supprime un objet, son historique, et ses fichiers associés."""
    db = get_db()
    kit_usage = db.execute("SELECT k.nom FROM kit_objets ko JOIN kits k ON ko.kit_id = k.id WHERE ko.objet_id = ?", (id_objet,)).fetchall()
    if kit_usage:
        noms_kits = ", ".join([k['nom'] for k in kit_usage])
        flash(f"Impossible de supprimer cet objet car il est utilisé dans le(s) kit(s) : {noms_kits}.", "error")
        return redirect(request.referrer or url_for('inventaire.inventaire'))
    objet = db.execute(
        "SELECT nom, image, fds_nom_securise FROM objets WHERE id = ?",
        (id_objet,)
    ).fetchone()

    if not objet:
        flash("Objet non trouvé.", "error")
        return redirect(request.referrer or url_for('inventaire.inventaire'))

    try:
        if objet['image']:
            os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], objet['image']))
        if objet['fds_nom_securise']:
            os.remove(os.path.join(current_app.config['FDS_UPLOAD_FOLDER'], objet['fds_nom_securise']))

        db.execute("DELETE FROM historique WHERE objet_id = ?", (id_objet,))
        db.execute("DELETE FROM reservations WHERE objet_id = ?", (id_objet,))
        db.execute("DELETE FROM kit_objets WHERE objet_id = ?", (id_objet,))
        db.execute("DELETE FROM objets WHERE id = ?", (id_objet,))
        db.commit()
        flash(f"L'objet '{objet['nom']}' et toutes ses données associées ont été supprimés.", "success")

    except OSError:
        flash(f"Un fichier associé à '{objet['nom']}' n'a pas pu être trouvé, mais l'objet a été supprimé de la base de données.", "warning")
        db.commit()
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Une erreur de base de données est survenue : {e}", "error")

    return redirect(request.referrer or url_for('inventaire.inventaire'))

@inventaire_bp.route("/maj_commande/<int:objet_id>", methods=["POST"])
@login_required
def maj_commande(objet_id):
    data = request.get_json()
    en_commande = 1 if data.get("en_commande") else 0
    db = get_db()
    db.execute("UPDATE objets SET en_commande = ? WHERE id = ?",
               (en_commande, objet_id))
    db.commit()
    return jsonify(success=True)


@inventaire_bp.route("/api/maj_traite/<int:objet_id>", methods=["POST"])
@login_required
def maj_traite(objet_id):
    data = request.get_json()
    traite = 1 if data.get("traite") else 0
    db = get_db()
    db.execute("UPDATE objets SET traite = ? WHERE id = ?", (traite, objet_id))
    db.commit()
    return jsonify(success=True)

@inventaire_bp.route("/api/deplacer_objets", methods=['POST'])
@admin_required
def deplacer_objets():
    data = request.get_json()
    objet_ids = data.get('objet_ids')
    destination_id = data.get('destination_id')
    type_destination = data.get('type_destination')

    if not all([objet_ids, destination_id, type_destination]):
        return jsonify(success=False, error="Données manquantes."), 400

    db = get_db()
    try:
        field_to_update = ('categorie_id' if type_destination == 'categorie'
                           else 'armoire_id')

        for objet_id in objet_ids:
            db.execute(f"UPDATE objets SET {field_to_update} = ? WHERE id = ?",
                       (destination_id, objet_id))

        db.commit()
        flash(f"{len(objet_ids)} objet(s) déplacé(s) avec succès.", "success")
        return jsonify(success=True)
    except sqlite3.Error as e:
        db.rollback()
        return jsonify(success=False, error=str(e)), 500

@inventaire_bp.route("/api/filtrer_inventaire")
@login_required
def api_filtrer_inventaire():
    db = get_db()
    page = request.args.get('page', 1, type=int)
    sort_by = request.args.get('sort_by', 'nom')
    direction = request.args.get('direction', 'asc')
    search_query = request.args.get('q', None)
    armoire_id = request.args.get('armoire', None)
    categorie_id = request.args.get('categorie', None)
    etat = request.args.get('etat', None)

    objets, total_pages = get_paginated_objets(db, page, sort_by, direction,
                                               search_query, armoire_id,
                                               categorie_id, etat)

    pagination = {
        'page': page,
        'total_pages': total_pages,
        'endpoint': 'inventaire.inventaire',
        'id': None
    }

    table_html = render_template('_table_objets.html',
                                 objets=objets,
                                 date_actuelle=datetime.now(),
                                 sort_by=sort_by,
                                 direction=direction,
                                 pagination=pagination)
    pagination_html = render_template('_pagination.html',
                                      pagination=pagination,
                                      sort_by=sort_by,
                                      direction=direction)

    return jsonify(table_html=table_html, pagination_html=pagination_html)