# -----------------------------------------------------------------------------
# 1. IMPORTS DE LA BIBLIOTHÈQUE STANDARD PYTHON
# -----------------------------------------------------------------------------
import hashlib
import logging
import math
import shutil
import sys
import traceback
import os
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from logging.handlers import RotatingFileHandler

# -----------------------------------------------------------------------------
# 2. IMPORTS DES BIBLIOTHÈQUES TIERCES (PIP)
# -----------------------------------------------------------------------------
from flask import (Flask, flash, g, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, session, url_for)
from flask_wtf.csrf import CSRFProtect
from fpdf import FPDF, XPos, YPos
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from werkzeug.security import check_password_hash, generate_password_hash

# -----------------------------------------------------------------------------
# 3. IMPORTS DES MODULES LOCAUX
# -----------------------------------------------------------------------------
from db import get_db
from db import init_app as init_db_app
from utils import (admin_required, get_alerte_info, is_setup_needed,
                   limit_objets_required, login_required)
from views.auth import auth_bp
from views.inventaire import inventaire_bp
from views.admin import admin_bp

class PDFWithFooter(FPDF):
    def footer(self):
        self.set_y(-15)
        # CORRECTION : Utilisation de la police de base et de la nouvelle syntaxe
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='R')

# --- CONFIGURATION DE L'APPLICATION ---
app = Flask(__name__)
app.config.from_object('config')
init_db_app(app)
app.config['SECRET_KEY'] = os.environ.get('GMLCL_SECRET_KEY', 'une-cle-temporaire-pour-le-developpement-a-changer')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
csrf = CSRFProtect(app)

# ENREGISTREMENT DES BLUEPRINTS
app.register_blueprint(auth_bp)
app.register_blueprint(inventaire_bp)
USER_DATA_PATH = os.path.join(os.environ.get('APPDATA'), 'GMLCL')
os.makedirs(USER_DATA_PATH, exist_ok=True)
app.config['UPLOAD_FOLDER'] = os.path.join(USER_DATA_PATH, 'uploads', 'images')
app.config['FDS_UPLOAD_FOLDER'] = os.path.join(USER_DATA_PATH, 'uploads', 'fds')
DATABASE = os.path.join(USER_DATA_PATH, 'base.db')
app.config['DATABASE'] = DATABASE
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['FDS_UPLOAD_FOLDER'], exist_ok=True)
app.register_blueprint(admin_bp)

if not app.debug:
    log_file_path = os.path.join(USER_DATA_PATH, 'app.log')
    logging.basicConfig(
        level=logging.ERROR,
        format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
        handlers=[
            RotatingFileHandler(
                log_file_path, maxBytes=1024000, backupCount=5
            )
        ]
    )
    app.logger.info('Logging configuré pour écrire dans %s', log_file_path)

ITEMS_PER_PAGE = 10
CLE_PRO_SECRETE = os.environ.get('GMLCL_PRO_KEY', 'valeur-par-defaut-si-non-definie')


# --- FILTRES JINJA2 PERSONNALISÉS ---
def format_datetime(value, fmt='%d/%m/%Y %H:%M'):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except (ValueError, TypeError):
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except (ValueError, TypeError):
                    return value
    if isinstance(value, (datetime, date)):
        return value.strftime(fmt)
    return value

app.jinja_env.filters['strftime'] = format_datetime

def format_datetime_fr(value, fmt):
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
        except (ValueError, TypeError):
            try:
                value = datetime.fromisoformat(value)
            except (ValueError, TypeError):
                return value
    if not isinstance(value, (datetime, date)):
        return value
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    mois = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]
    format_fr = fmt.replace('%A', jours[value.weekday()].capitalize())
    format_fr = format_fr.replace('%B', mois[value.month - 1])
    return value.strftime(format_fr)

app.jinja_env.filters['strftime_fr'] = format_datetime_fr

def annee_scolaire_format(year):
    if isinstance(year, int):
        return f"{year}-{year + 1}"
    return year

app.jinja_env.filters['annee_scolaire'] = annee_scolaire_format

# --- GESTION DE L'INITIALISATION AU PREMIER LANCEMENT ---
@app.before_request
def check_setup():
    if not os.path.exists(DATABASE):
        return
    allowed_endpoints = ['static', 'setup', 'login', 'register']
    if request.endpoint and request.endpoint not in allowed_endpoints:
        if is_setup_needed(app):
            return redirect(url_for('auth.setup'))

# --- FONCTIONS COMMUNES ET PROCESSEUR DE CONTEXTE ---
@app.context_processor
def inject_alert_info():
    # Si l'application n'est pas encore configurée ou si l'utilisateur n'est pas connecté,
    # on renvoie des valeurs par défaut sans interroger la base de données.
    if 'user_id' not in session or is_setup_needed(app):
        return {'alertes_total': 0, 'alertes_stock': 0, 'alertes_peremption': 0}
    
    # Ce bloc ne s'exécute que si l'app est configurée ET l'utilisateur connecté.
    try:
        db = get_db()
        return get_alerte_info(db)
    except sqlite3.Error:
        # En cas d'erreur de base de données inattendue, on évite de planter l'application.
        return {'alertes_total': '!', 'alertes_stock': '!', 'alertes_peremption': '!'}


@app.context_processor
def inject_licence_info():
    """
    Injecte le statut de la licence dans le contexte de tous les templates.
    Rend la variable 'licence' disponible globalement.
    """
    licence_info = {'statut': 'FREE', 'is_pro': False, 'instance_id': 'N/A'}

    # On ne fait rien si la session n'est pas active ou si l'app n'est pas configurée.
    if 'user_id' not in session or is_setup_needed(app):
        return {'licence': licence_info}

    try:
        db = get_db()
        params = db.execute(
            "SELECT cle, valeur FROM parametres "
            "WHERE cle IN ('licence_statut', 'instance_id')").fetchall()
        params_dict = {row['cle']: row['valeur'] for row in params}

        if params_dict.get('licence_statut') == 'PRO':
            licence_info['statut'] = 'PRO'
            licence_info['is_pro'] = True

        if params_dict.get('instance_id'):
            licence_info['instance_id'] = params_dict.get('instance_id')

    except sqlite3.Error as e:
        app.logger.warning(
            f"Impossible de lire les informations de licence. Erreur : {e}"
        )
    
    return {'licence': licence_info}

# --- ROUTES PRINCIPALES ---

@app.route("/jour/<string:date_str>")
@login_required
def vue_jour(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Format de date invalide.", "error")
        return redirect(url_for('calendrier'))

    db = get_db()
    start_of_day = datetime.strptime(f"{date_str} 00:00:00", '%Y-%m-%d %H:%M:%S')
    end_of_day = datetime.strptime(f"{date_str} 23:59:59", '%Y-%m-%d %H:%M:%S')

    reservations_brutes = db.execute(
        """
        SELECT
            r.groupe_id, r.debut_reservation, r.fin_reservation,
            u.nom_utilisateur
        FROM reservations r
        JOIN utilisateurs u ON r.utilisateur_id = u.id
        WHERE datetime(r.debut_reservation) <= ? AND datetime(r.fin_reservation) > ?
        GROUP BY r.groupe_id, r.debut_reservation, r.fin_reservation, u.nom_utilisateur
        ORDER BY r.debut_reservation
        """, (end_of_day.strftime('%Y-%m-%d %H:%M:%S'), start_of_day.strftime('%Y-%m-%d %H:%M:%S'))).fetchall()

    # --- NOUVELLE LOGIQUE : Préparation des données pour la vue en liste ---
    reservations_par_heure = {hour: {'starts': [], 'continues': []} for hour in range(24)}

    for resa in reservations_brutes:
        debut_dt = datetime.fromisoformat(resa['debut_reservation'])
        fin_dt = datetime.fromisoformat(resa['fin_reservation'])

        # On ne traite que les heures visibles (8h à 20h)
        start_hour = max(8, debut_dt.hour)
        end_hour = min(20, fin_dt.hour if fin_dt.minute > 0 else fin_dt.hour - 1)

        # Si la réservation commence bien ce jour-là
        if debut_dt.date() == date_obj:
            reservations_par_heure[debut_dt.hour]['starts'].append(dict(resa))
        
        # Pour les heures suivantes, on ajoute un bloc "continuation"
        for hour in range(start_hour + 1, end_hour + 1):
            if hour >= 8 and hour <= 20:
                # On vérifie que le bloc n'est pas déjà présent (cas de plusieurs objets pour un même groupe_id)
                if not any(d.get('groupe_id') == resa['groupe_id'] for d in reservations_par_heure[hour]['continues']):
                    reservations_par_heure[hour]['continues'].append(dict(resa))

    return render_template("vue_jour.html",
                           date_concernee=date_obj,
                           reservations_par_heure=reservations_par_heure)


# --- ROUTES SÉCURISÉES ET DE GESTION ---
@app.route("/calendrier")
@login_required
def calendrier():
    db = get_db()
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("calendrier.html",
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)

@app.route("/panier")
@login_required
def panier():
    return render_template("panier.html")

@app.route("/alertes")
@login_required
def alertes():
    db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # CORRECTION: Calcul du stock disponible pour la liste des alertes de stock
    objets_stock_query = """
        SELECT o.id, o.nom, o.quantite_physique, o.seuil, a.nom AS armoire,
            c.nom AS categorie, o.image, o.en_commande,
            o.date_peremption, o.traite,
            (o.quantite_physique - COALESCE(SUM(r.quantite_reservee), 0)) as quantite_disponible
        FROM objets o 
        JOIN armoires a ON o.armoire_id = a.id
        JOIN categories c ON o.categorie_id = c.id
        LEFT JOIN reservations r ON o.id = r.objet_id AND r.fin_reservation > ?
        GROUP BY o.id
        HAVING quantite_disponible <= o.seuil 
        ORDER BY o.nom
    """
    objets_stock = db.execute(objets_stock_query, (now_str,)).fetchall()

    date_limite = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    # CORRECTION: Calcul du stock disponible pour la liste des péremptions
    objets_peremption_query = """
        SELECT o.id, o.nom, o.quantite_physique, o.seuil, a.nom AS armoire,
               c.nom AS categorie, o.image, o.en_commande, o.date_peremption,
               o.traite,
               (o.quantite_physique - COALESCE(SUM(r.quantite_reservee), 0)) as quantite_disponible
        FROM objets o 
        JOIN armoires a ON o.armoire_id = a.id
        JOIN categories c ON o.categorie_id = c.id
        LEFT JOIN reservations r ON o.id = r.objet_id AND r.fin_reservation > ?
        WHERE o.date_peremption IS NOT NULL AND o.date_peremption < ?
        GROUP BY o.id
        ORDER BY o.date_peremption ASC
    """
    objets_peremption = db.execute(objets_peremption_query, (now_str, date_limite, )).fetchall()
    
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    
    return render_template("alertes.html",
                           objets_stock=objets_stock,
                           objets_peremption=objets_peremption,
                           date_actuelle=datetime.now(),
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)


@app.route("/gestion_armoires")
@login_required
def gestion_armoires():
    db = get_db()
    armoires = db.execute("""
        SELECT a.id, a.nom, COUNT(o.id) as count FROM armoires a
        LEFT JOIN objets o ON a.id = o.armoire_id
        GROUP BY a.id, a.nom ORDER BY a.nom
        """).fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("gestion_armoires.html",
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)


@app.route("/gestion_categories")
@login_required
def gestion_categories():
    db = get_db()
    categories = db.execute("""
        SELECT c.id, c.nom, COUNT(o.id) as count FROM categories c
        LEFT JOIN objets o ON c.id = o.categorie_id
        GROUP BY c.id, c.nom ORDER BY c.nom
        """).fetchall()
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    return render_template("gestion_categories.html",
                           categories=categories,
                           armoires=armoires,
                           now=datetime.now)

@app.route("/a-propos")
@login_required
def a_propos():
    return render_template("a_propos.html")
    
@app.route("/admin/activer_licence", methods=["POST"])
@admin_required
def activer_licence():
    licence_cle_fournie = request.form.get('licence_cle', '').strip()
    db = get_db()

    instance_id_row = db.execute(
        "SELECT valeur FROM parametres WHERE cle = 'instance_id'").fetchone()
    if not instance_id_row:
        flash(
            "Erreur critique : Identifiant d'instance manquant. "
            "Impossible de vérifier la licence.", "error")
        return redirect(url_for('admin.admin'))

    instance_id = instance_id_row['valeur']

    chaine_a_verifier = f"{instance_id}-{CLE_PRO_SECRETE}"
    cle_valide_calculee = hashlib.sha256(
        chaine_a_verifier.encode('utf-8')).hexdigest()

    if licence_cle_fournie == cle_valide_calculee[:16]:
        try:
            db.execute("UPDATE parametres SET valeur = 'PRO' "
                       "WHERE cle = 'licence_statut'")
            db.execute(
                "UPDATE parametres SET valeur = ? WHERE cle = 'licence_cle'",
                (licence_cle_fournie, ))
            db.commit()
            flash(
                "Licence Pro activée avec succès ! Toutes les "
                "fonctionnalités sont maintenant débloquées.", "success")
        except sqlite3.Error as e:
            db.rollback()
            flash(f"Erreur de base de données lors de l'activation : {e}",
                  "error")
    else:
        flash(
            "La clé de licence fournie est invalide ou ne correspond pas à "
            "cette installation.", "error")

    return redirect(url_for('admin.admin'))


@app.route("/admin/reset_licence", methods=["POST"])
@admin_required
def reset_licence():
    admin_password = request.form.get('admin_password')
    db = get_db()

    admin_user = db.execute(
        "SELECT mot_de_passe FROM utilisateurs WHERE id = ?",
        (session['user_id'], )).fetchone()

    if not admin_user or not check_password_hash(admin_user['mot_de_passe'],
                                                 admin_password):
        flash(
            "Mot de passe administrateur incorrect. "
            "La réinitialisation a été annulée.", "error")
        return redirect(url_for('admin.admin'))

    try:
        db.execute(
            "UPDATE parametres SET valeur = 'FREE' WHERE cle = 'licence_statut'"
        )
        db.execute(
            "UPDATE parametres SET valeur = '' WHERE cle = 'licence_cle'")
        db.commit()
        flash("La licence a été réinitialisée au statut GRATUIT.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données lors de la réinitialisation : {e}",
              "error")

    return redirect(url_for('admin.admin'))


# --- ROUTES POUR LA GESTION DES KITS ---
@app.route("/admin/kits")
@admin_required
def gestion_kits():
    db = get_db()
    kits = db.execute("""
        SELECT k.id, k.nom, k.description, COUNT(ko.id) as count
        FROM kits k
        LEFT JOIN kit_objets ko ON k.id = ko.kit_id
        GROUP BY k.id, k.nom, k.description
        ORDER BY k.nom
        """).fetchall()
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("admin_kits.html",
                           kits=kits,
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)


@app.route("/admin/kits/ajouter", methods=["POST"])
@admin_required
def ajouter_kit():
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Le nom du kit ne peut pas être vide.", "error")
        return redirect(url_for('gestion_kits'))

    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO kits (nom, description) VALUES (?, ?)",
            (nom, description))
        db.commit()
        new_kit_id = cursor.lastrowid
        flash(
            f"Le kit '{nom}' a été créé. "
            "Vous pouvez maintenant y ajouter des objets.", "success")
        return redirect(url_for('modifier_kit', kit_id=new_kit_id))
    except sqlite3.IntegrityError:
        flash(f"Un kit avec le nom '{nom}' existe déjà.", "error")
        return redirect(url_for('gestion_kits'))


@app.route("/admin/kits/modifier/<int:kit_id>", methods=["GET", "POST"])
@admin_required
def modifier_kit(kit_id):
    db = get_db()
    kit = db.execute("SELECT * FROM kits WHERE id = ?", (kit_id, )).fetchone()
    if not kit:
        flash("Kit non trouvé.", "error")
        return redirect(url_for('gestion_kits'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if request.method == "POST":
        objet_id_str = request.form.get("objet_id")
        quantite_str = request.form.get("quantite")

        # --- LOGIQUE D'AJOUT D'UN NOUVEL OBJET AU KIT ---
        if objet_id_str and quantite_str:
            try:
                objet_id = int(objet_id_str)
                quantite = int(quantite_str)

                # CORRECTION: Vérification du stock disponible
                stock_info = db.execute(
                    f"""
                    SELECT o.nom, (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = o.id AND r.fin_reservation > '{now_str}'), 0)) as quantite_disponible
                    FROM objets o WHERE o.id = ?
                    """, (objet_id,)
                ).fetchone()

                if not stock_info:
                    flash("Objet non trouvé.", "error")
                    return redirect(url_for('modifier_kit', kit_id=kit_id))

                if quantite > stock_info['quantite_disponible']:
                    flash(f"Quantité invalide pour '{stock_info['nom']}'. Vous ne pouvez pas ajouter plus que le stock disponible ({stock_info['quantite_disponible']}).", "error")
                    return redirect(url_for('modifier_kit', kit_id=kit_id))

                existing = db.execute("SELECT id FROM kit_objets WHERE kit_id = ? AND objet_id = ?", (kit_id, objet_id)).fetchone()
                if existing:
                    db.execute("UPDATE kit_objets SET quantite = ? WHERE id = ?", (quantite, existing['id']))
                else:
                    db.execute("INSERT INTO kit_objets (kit_id, objet_id, quantite) VALUES (?, ?, ?)", (kit_id, objet_id, quantite))
                db.commit()
                flash(f"L'objet '{stock_info['nom']}' a été ajouté/mis à jour dans le kit.", "success")

            except (ValueError, TypeError):
                flash("Données invalides.", "error")
            
            return redirect(url_for('modifier_kit', kit_id=kit_id))

        # --- LOGIQUE DE MISE À JOUR DES QUANTITÉS EXISTANTES ---
        for key, value in request.form.items():
            if key.startswith("quantite_"):
                try:
                    kit_objet_id = int(key.split("_")[1])
                    new_quantite = int(value)

                    objet_info = db.execute(
                        f"""
                        SELECT o.nom, o.id as objet_id, (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = o.id AND r.fin_reservation > '{now_str}'), 0)) as quantite_disponible
                        FROM kit_objets ko JOIN objets o ON ko.objet_id = o.id
                        WHERE ko.id = ?
                        """, (kit_objet_id,)
                    ).fetchone()

                    if not objet_info: continue

                    if new_quantite > objet_info['quantite_disponible']:
                         flash(f"Quantité invalide pour '{objet_info['nom']}'. Vous ne pouvez pas dépasser le stock disponible ({objet_info['quantite_disponible']}).", "error")
                    else:
                        db.execute("UPDATE kit_objets SET quantite = ? WHERE id = ?", (new_quantite, kit_objet_id))
                        flash(f"Quantité pour '{objet_info['nom']}' mise à jour.", "success")
                
                except (ValueError, TypeError):
                    flash("Une quantité fournie est invalide.", "error")
        
        db.commit()
        return redirect(url_for('modifier_kit', kit_id=kit_id))

    # --- RÉCUPÉRATION DES DONNÉES POUR L'AFFICHAGE (GET) ---
    objets_in_kit = db.execute(
        f"""
        SELECT ko.id, o.nom, 
               (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = o.id AND r.fin_reservation > '{now_str}'), 0)) as stock_disponible, 
               ko.quantite
        FROM kit_objets ko
        JOIN objets o ON ko.objet_id = o.id
        WHERE ko.kit_id = ?
        ORDER BY o.nom
        """, (kit_id, )).fetchall()

    objets_disponibles = db.execute(
        f"""
        SELECT id, nom, (quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = objets.id AND r.fin_reservation > '{now_str}'), 0)) as quantite_disponible 
        FROM objets
        WHERE id NOT IN (SELECT objet_id FROM kit_objets WHERE kit_id = ?)
        ORDER BY nom
        """, (kit_id, )).fetchall()

    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()

    return render_template("admin_kit_modifier.html",
                           kit=kit,
                           objets_in_kit=objets_in_kit,
                           objets_disponibles=objets_disponibles,
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)


@app.route("/admin/kits/retirer_objet/<int:kit_objet_id>")
@admin_required
def retirer_objet_kit(kit_objet_id):
    db = get_db()
    kit_objet = db.execute("SELECT kit_id FROM kit_objets WHERE id = ?",
                           (kit_objet_id, )).fetchone()
    if kit_objet:
        kit_id = kit_objet['kit_id']
        db.execute("DELETE FROM kit_objets WHERE id = ?", (kit_objet_id, ))
        db.commit()
        flash("Objet retiré du kit.", "success")
        return redirect(url_for('modifier_kit', kit_id=kit_id))
    flash("Erreur : objet du kit non trouvé.", "error")
    return redirect(url_for('gestion_kits'))


@app.route("/admin/kits/supprimer/<int:kit_id>", methods=["POST"])
@admin_required
def supprimer_kit(kit_id):
    db = get_db()
    kit = db.execute("SELECT nom FROM kits WHERE id = ?",
                     (kit_id, )).fetchone()
    if kit:
        db.execute("DELETE FROM kits WHERE id = ?", (kit_id, ))
        db.commit()
        flash(f"Le kit '{kit['nom']}' a été supprimé.", "success")
    else:
        flash("Kit non trouvé.", "error")
    return redirect(url_for('gestion_kits'))


def generer_rapport_pdf(data, date_debut, date_fin, group_by):
    pdf = PDFWithFooter()
    pdf.alias_nb_pages()
    pdf.add_page(orientation='L')
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport d\'Activite', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(
        0, 10,
        f"Periode du {datetime.strptime(date_debut, '%Y-%m-%d').strftime('%d/%m/%Y')} "
        f"au {datetime.strptime(date_fin, '%Y-%m-%d').strftime('%d/%m/%Y')}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(5)

    col_widths = {"date": 25, "heure": 15, "user": 35, "action": 60, "objet": 60, "details": 75}
    table_width = sum(col_widths.values())
    line_height = 7 # Hauteur de ligne fixe

    def draw_header():
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(col_widths["date"], 8, 'Date', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        pdf.cell(col_widths["heure"], 8, 'Heure', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        pdf.cell(col_widths["user"], 8, 'Utilisateur', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        pdf.cell(col_widths["action"], 8, 'Action', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        pdf.cell(col_widths["objet"], 8, 'Objet Concerne', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
        pdf.cell(col_widths["details"], 8, 'Details', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)

    draw_header()

    current_group = None
    
    for item in data:
        if pdf.get_y() > 190: # Marge de sécurité pour le saut de page
            pdf.add_page(orientation='L')
            draw_header()
            if current_group:
                pdf.set_font('Helvetica', 'B', 10)
                pdf.set_fill_color(230, 240, 255)
                pdf.cell(table_width, 8, f"Type d'action : {current_group}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L', fill=True)

        if group_by == 'action' and item['action'] != current_group:
            current_group = item['action']
            pdf.set_font('Helvetica', 'B', 10)
            pdf.set_fill_color(230, 240, 255)
            pdf.cell(table_width, 8, f"Type d'action : {current_group}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L', fill=True)

        pdf.set_font('Helvetica', '', 8)
        timestamp_dt = datetime.fromisoformat(item['timestamp'])
        
        # === LOGIQUE DE DESSIN SIMPLE ET FIABLE ===
        pdf.cell(col_widths["date"], line_height, timestamp_dt.strftime('%d/%m/%Y'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
        pdf.cell(col_widths["heure"], line_height, timestamp_dt.strftime('%H:%M'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
        pdf.cell(col_widths["user"], line_height, item['nom_utilisateur'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
        pdf.cell(col_widths["action"], line_height, item['action'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
        pdf.cell(col_widths["objet"], line_height, item['objet_nom'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L')
        pdf.cell(col_widths["details"], line_height, item['details'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='L')

    return BytesIO(pdf.output())


def generer_rapport_excel(data, date_debut, date_fin, group_by):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rapport d'Activite"

    title_font = Font(name='Calibri', size=16, bold=True)
    subtitle_font = Font(name='Calibri', size=11, italic=True, color="6c7a89")
    header_font = Font(name='Calibri', size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4A5568",
                              end_color="4A5568",
                              fill_type="solid")
    group_font = Font(name='Calibri', size=11, bold=True, color="2D3748")
    group_fill = PatternFill(start_color="E2E8F0",
                             end_color="E2E8F0",
                             fill_type="solid")
    even_row_fill = PatternFill(start_color="F7FAFC",
                                end_color="F7FAFC",
                                fill_type="solid")

    center_align = Alignment(horizontal='center',
                             vertical='center',
                             wrap_text=True)
    left_align = Alignment(horizontal='left',
                           vertical='center',
                           wrap_text=True)

    thin_border_side = Side(style='thin', color="4A5568")
    thick_border_side = Side(style='medium', color="000000")

    cell_border = Border(left=thin_border_side,
                         right=thin_border_side,
                         top=thin_border_side,
                         bottom=thin_border_side)

    start_col = 2
    headers = [
        "Date", "Heure", "Utilisateur", "Action", "Objet Concerne", "Details"
    ]
    end_col = start_col + len(headers) - 1

    sheet.merge_cells(start_row=2,
                      start_column=start_col,
                      end_row=2,
                      end_column=end_col)
    title_cell = sheet.cell(row=2, column=start_col)
    title_cell.value = "Rapport d'Activite"
    title_cell.font = title_font
    title_cell.alignment = Alignment(horizontal='center')

    sheet.merge_cells(start_row=3,
                      start_column=start_col,
                      end_row=3,
                      end_column=end_col)
    subtitle_cell = sheet.cell(row=3, column=start_col)
    subtitle_cell.value = (
        f"Periode du "
        f"{datetime.strptime(date_debut, '%Y-%m-%d').strftime('%d/%m/%Y')} au "
        f"{datetime.strptime(date_fin, '%Y-%m-%d').strftime('%d/%m/%Y')}")
    subtitle_cell.font = subtitle_font
    subtitle_cell.alignment = Alignment(horizontal='center')

    header_row = 5
    for i, header_text in enumerate(headers, start=start_col):
        cell = sheet.cell(row=header_row, column=i, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = cell_border

    row_index = header_row + 1
    current_group = None
    last_date_str = None
    is_even = False

    for item in data:
        if group_by == 'action' and item['action'] != current_group:
            current_group = item['action']
            last_date_str = None
            cell = sheet.cell(row=row_index,
                              column=start_col,
                              value=f"Type d'action : {current_group}")
            sheet.merge_cells(start_row=row_index,
                              start_column=start_col,
                              end_row=row_index,
                              end_column=end_col)
            for c in range(start_col, end_col + 1):
                sheet.cell(row=row_index, column=c).fill = group_fill
                sheet.cell(row=row_index, column=c).font = group_font
                sheet.cell(row=row_index, column=c).border = cell_border
            row_index += 1
            is_even = False

        timestamp_dt = datetime.fromisoformat(item['timestamp'])
        current_date_str = timestamp_dt.strftime('%d/%m/%Y')

        date_str_display = current_date_str
        if group_by == 'date' and current_date_str == last_date_str:
            date_str_display = ""

        row_data = [
            date_str_display,
            timestamp_dt.strftime('%H:%M'), item['nom_utilisateur'],
            item['action'], item['objet_nom'], item['details']
        ]

        for col_index, value in enumerate(row_data, start=start_col):
            cell = sheet.cell(row=row_index, column=col_index, value=value)
            cell.border = cell_border
            if col_index in [
                    start_col, start_col + 1, start_col + 2, start_col + 3
            ]:
                cell.alignment = center_align
            else:
                cell.alignment = left_align
            if is_even:
                cell.fill = even_row_fill

        last_date_str = current_date_str
        row_index += 1
        is_even = not is_even

    end_row_index = row_index - 1
    if end_row_index >= header_row:
        for row in sheet.iter_rows(min_row=header_row,
                                   max_row=end_row_index,
                                   min_col=start_col,
                                   max_col=end_col):
            for cell in row:
                new_border = Border(left=cell.border.left,
                                    right=cell.border.right,
                                    top=cell.border.top,
                                    bottom=cell.border.bottom)
                if cell.row == header_row:
                    new_border.top = thick_border_side
                if cell.row == end_row_index:
                    new_border.bottom = thick_border_side
                if cell.column == start_col:
                    new_border.left = thick_border_side
                if cell.column == end_col:
                    new_border.right = thick_border_side
                cell.border = new_border

    column_widths = {'B': 15, 'C': 10, 'D': 25, 'E': 50, 'F': 40, 'G': 60}
    for col, width in column_widths.items():
        sheet.column_dimensions[col].width = width

    sheet.freeze_panes = sheet.cell(row=header_row + 1, column=start_col)

    if end_row_index >= header_row:
        sheet.auto_filter.ref = (
            f"{sheet.cell(row=header_row, column=start_col).coordinate}:"
            f"{sheet.cell(row=end_row_index, column=end_col).coordinate}")

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


@app.route("/fournisseurs")
@login_required
def voir_fournisseurs():
    db = get_db()
    fournisseurs = db.execute(
        "SELECT * FROM fournisseurs ORDER BY nom").fetchall()
    return render_template("fournisseurs.html", fournisseurs=fournisseurs)


@app.route("/admin/fournisseurs", methods=['GET', 'POST'])
@admin_required
def gestion_fournisseurs():
    db = get_db()
    if request.method == 'POST':
        nom = request.form.get('nom', '').strip()
        site_web = request.form.get('site_web', '').strip()
        logo_name = None

        if not nom:
            flash("Le nom du fournisseur est obligatoire.", "error")
            return redirect(url_for('gestion_fournisseurs'))

        if 'logo' in request.files:
            logo = request.files['logo']
            if logo and logo.filename != '':
                filename = secure_filename(logo.filename)
                logo.save(os.path.join('static/images/fournisseurs', filename))
                logo_name = filename

        try:
            db.execute(
                "INSERT INTO fournisseurs (nom, site_web, logo) "
                "VALUES (?, ?, ?)", (nom, site_web or None, logo_name))
            db.commit()
            flash(f"Le fournisseur '{nom}' a été ajouté.", "success")
        except sqlite3.IntegrityError:
            flash(f"Un fournisseur avec le nom '{nom}' existe déjà.", "error")
        except sqlite3.Error as e:
            flash(f"Erreur de base de données : {e}", "error")
        return redirect(url_for('gestion_fournisseurs'))

    fournisseurs = db.execute(
        "SELECT * FROM fournisseurs ORDER BY nom").fetchall()
    return render_template("admin_fournisseurs.html",
                           fournisseurs=fournisseurs)


@app.route("/admin/fournisseurs/supprimer/<int:id>", methods=['POST'])
@admin_required
def supprimer_fournisseur(id):
    db = get_db()
    fournisseur = db.execute("SELECT logo, nom FROM fournisseurs WHERE id = ?",
                             (id, )).fetchone()
    if fournisseur:
        if fournisseur['logo']:
            try:
                os.remove(
                    os.path.join('static/images/fournisseurs',
                                 fournisseur['logo']))
            except OSError:
                pass

        db.execute("DELETE FROM fournisseurs WHERE id = ?", (id, ))
        db.commit()
        flash(f"Le fournisseur '{fournisseur['nom']}' a été supprimé.",
              "success")
    else:
        flash("Fournisseur non trouvé.", "error")
    return redirect(url_for('gestion_fournisseurs'))


@app.route("/admin/fournisseurs/modifier/<int:id>", methods=['POST'])
@admin_required
def modifier_fournisseur(id):
    db = get_db()
    fournisseur_avant = db.execute("SELECT * FROM fournisseurs WHERE id = ?",
                                   (id, )).fetchone()
    if not fournisseur_avant:
        flash("Fournisseur non trouvé.", "error")
        return redirect(url_for('gestion_fournisseurs'))

    nom = request.form.get('nom', '').strip()
    site_web = request.form.get('site_web', '').strip()
    logo_name = fournisseur_avant['logo']

    if not nom:
        flash("Le nom du fournisseur est obligatoire.", "error")
        return redirect(url_for('gestion_fournisseurs'))

    if request.form.get('supprimer_logo'):
        if logo_name:
            try:
                os.remove(os.path.join('static/images/fournisseurs',
                                       logo_name))
            except OSError:
                pass
        logo_name = None
    elif 'logo' in request.files:
        nouveau_logo = request.files['logo']
        if nouveau_logo and nouveau_logo.filename != '':
            if logo_name:
                try:
                    os.remove(
                        os.path.join('static/images/fournisseurs', logo_name))
                except OSError:
                    pass
            filename = secure_filename(nouveau_logo.filename)
            nouveau_logo.save(
                os.path.join('static/images/fournisseurs', filename))
            logo_name = filename

    try:
        db.execute(
            "UPDATE fournisseurs SET nom = ?, site_web = ?, logo = ? "
            "WHERE id = ?", (nom, site_web or None, logo_name, id))
        db.commit()
        flash(f"Le fournisseur '{nom}' a été mis à jour.", "success")
    except sqlite3.IntegrityError:
        flash(f"Un autre fournisseur avec le nom '{nom}' existe déjà.",
              "error")
    except sqlite3.Error as e:
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('gestion_fournisseurs'))


# --- ROUTES POUR LA GESTION DU BUDGET ---
@app.route("/budget/voir")
@login_required
def voir_budget():
    db = get_db()
    now = datetime.now()
    
    # Logique de l'année scolaire : commence en septembre.
    annee_scolaire_actuelle = now.year if now.month >= 9 else now.year - 1
    
    budget_actuel = db.execute(
        "SELECT * FROM budgets WHERE annee = ? AND cloture = 0",
        (annee_scolaire_actuelle, )).fetchone()

    depenses = []
    total_depenses = 0
    solde = 0

    if budget_actuel:
        depenses = db.execute(
            """SELECT d.id, d.contenu, d.montant, d.date_depense,
                      d.est_bon_achat, d.fournisseur_id, f.nom as fournisseur_nom
            FROM depenses d
            LEFT JOIN fournisseurs f ON d.fournisseur_id = f.id
            WHERE d.budget_id = ?
            ORDER BY d.date_depense DESC""",
            (budget_actuel['id'], )).fetchall()

        total_depenses_result = db.execute(
            "SELECT SUM(montant) as total FROM depenses WHERE budget_id = ?",
            (budget_actuel['id'], )).fetchone()
        total_depenses = (total_depenses_result['total']
                          if total_depenses_result['total'] is not None else 0)
        solde = budget_actuel['montant_initial'] - total_depenses

    return render_template("budget_voir.html",
                           budget_actuel=budget_actuel,
                           depenses=depenses,
                           total_depenses=total_depenses,
                           solde=solde)


@app.route("/budget", methods=['GET'])
@admin_required
def budget():
    db = get_db()
    now = datetime.now()
    
    # CORRECTION : Le basculement se fait maintenant en août (mois 8)
    annee_scolaire_actuelle = now.year if now.month >= 8 else now.year - 1

    budgets_archives = db.execute(
        "SELECT annee FROM budgets ORDER BY annee DESC").fetchall()

    annee_a_afficher_str = request.args.get('annee', type=str)
    
    if annee_a_afficher_str:
        annee_a_afficher = int(annee_a_afficher_str)
    else:
        # Par défaut, on affiche l'année scolaire en cours
        annee_a_afficher = annee_scolaire_actuelle

    budget_a_afficher = db.execute("SELECT * FROM budgets WHERE annee = ?",
                                   (annee_a_afficher, )).fetchone()

    # Si aucun budget n'existe pour l'année à afficher (cas du premier lancement), on en crée un vide
    if not budget_a_afficher and not budgets_archives:
        try:
            cursor = db.execute(
                "INSERT INTO budgets (annee, montant_initial, cloture) VALUES (?, ?, 0)",
                (annee_a_afficher, 0.0)
            )
            db.commit()
            budget_id = cursor.lastrowid
            budget_a_afficher = db.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()
            budgets_archives = db.execute("SELECT annee FROM budgets ORDER BY annee DESC").fetchall()
        except sqlite3.IntegrityError:
            db.rollback()
            budget_a_afficher = db.execute("SELECT * FROM budgets WHERE annee = ?", (annee_a_afficher,)).fetchone()

    depenses = []
    total_depenses = 0
    solde = 0
    cloture_autorisee = False

    if budget_a_afficher:
        depenses = db.execute(
            """SELECT d.id, d.contenu, d.montant, d.date_depense,
                      d.est_bon_achat, d.fournisseur_id, f.nom as fournisseur_nom
               FROM depenses d
               LEFT JOIN fournisseurs f ON d.fournisseur_id = f.id
               WHERE d.budget_id = ?
               ORDER BY d.date_depense DESC""",
            (budget_a_afficher['id'], )).fetchall()

        total_depenses_result = db.execute(
            "SELECT SUM(montant) as total FROM depenses WHERE budget_id = ?",
            (budget_a_afficher['id'], )).fetchone()
        total_depenses = (total_depenses_result['total'] if total_depenses_result['total'] is not None else 0)
        solde = budget_a_afficher['montant_initial'] - total_depenses

        # Logique de sécurité pour la clôture
        annee_fin_budget = budget_a_afficher['annee'] + 1
        date_limite_cloture = date(annee_fin_budget, 6, 1) # 1er Juin de l'année N+1
        if date.today() >= date_limite_cloture:
            cloture_autorisee = True

    budget_actuel_pour_modales = db.execute(
        "SELECT * FROM budgets WHERE annee = ? AND cloture = 0",
        (annee_scolaire_actuelle, )).fetchone()

    annee_proposee_pour_creation = annee_scolaire_actuelle
    if not budget_actuel_pour_modales:
        derniere_annee_budget = db.execute("SELECT MAX(annee) as max_annee FROM budgets").fetchone()
        if derniere_annee_budget and derniere_annee_budget['max_annee'] is not None:
            annee_proposee_pour_creation = derniere_annee_budget['max_annee'] + 1
        else:
            annee_proposee_pour_creation = annee_scolaire_actuelle

    fournisseurs = db.execute(
        "SELECT id, nom FROM fournisseurs ORDER BY nom").fetchall()

    return render_template(
        "budget.html",
        budget_affiche=budget_a_afficher,
        budget_actuel_pour_modales=budget_actuel_pour_modales,
        annee_proposee_pour_creation=annee_proposee_pour_creation,
        depenses=depenses,
        total_depenses=total_depenses,
        solde=solde,
        fournisseurs=fournisseurs,
        budgets_archives=budgets_archives,
        annee_selectionnee=annee_a_afficher,
        cloture_autorisee=cloture_autorisee,
        now=datetime.now)


@app.route("/budget/definir", methods=['POST'])
@admin_required
def definir_budget():
    db = get_db()
    montant = request.form.get('montant_initial')
    annee = request.form.get('annee')

    if not montant or not annee:
        flash("L'année et le montant sont obligatoires.", "error")
        return redirect(url_for('budget'))

    try:
        montant_float = float(montant.replace(',', '.'))
        annee_int = int(annee)

        existing_budget = db.execute(
            "SELECT id FROM budgets WHERE annee = ?", (annee_int,)
        ).fetchone()
        if existing_budget:
            db.execute(
                "UPDATE budgets SET montant_initial = ?, cloture = 0 WHERE id = ?",
                (montant_float, existing_budget['id'])
            )
        else:
            db.execute(
                "INSERT INTO budgets (annee, montant_initial) VALUES (?, ?)",
                (annee_int, montant_float)
            )

        db.commit()
        flash(
            f"Le budget pour l'année scolaire {annee_scolaire_format(annee_int)} a été défini à "
            f"{montant_float:.2f} €.", "success"
        )
    except ValueError:
        flash("Le montant ou l'année saisi(e) est invalide.", "error")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('budget', annee=annee))


@app.route("/budget/ajouter_depense", methods=['POST'])
@admin_required
def ajouter_depense():
    db = get_db()
    budget_id = request.form.get('budget_id')
    fournisseur_id = request.form.get('fournisseur_id')
    contenu = request.form.get('contenu', '').strip()
    montant = request.form.get('montant')
    date_depense = request.form.get('date_depense')
    est_bon_achat = 1 if request.form.get('est_bon_achat') == 'on' else 0

    if not all([budget_id, contenu, montant, date_depense]):
        flash("Tous les champs sont obligatoires pour ajouter une dépense.",
              "error")
        return redirect(url_for('budget'))

    if est_bon_achat:
        fournisseur_id = None
    elif not fournisseur_id:
        flash(
            "Veuillez sélectionner un fournisseur ou cocher la case "
            "'Bon d'achat'.", "error")
        return redirect(url_for('budget'))

    try:
        montant_float = float(montant.replace(',', '.'))
        db.execute(
            """INSERT INTO depenses (budget_id, fournisseur_id, contenu,
               montant, date_depense, est_bon_achat)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (budget_id, fournisseur_id, contenu, montant_float, date_depense,
             est_bon_achat))
        db.commit()
        flash("La dépense a été ajoutée avec succès.", "success")
    except ValueError:
        flash("Le montant saisi est invalide.", "error")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('budget'))


@app.route("/budget/modifier_depense/<int:id>", methods=['POST'])
@admin_required
def modifier_depense(id):
    db = get_db()
    depense = db.execute("SELECT id FROM depenses WHERE id = ?",
                         (id, )).fetchone()
    if not depense:
        flash("Dépense non trouvée.", "error")
        return redirect(url_for('budget'))

    fournisseur_id = request.form.get('fournisseur_id')
    contenu = request.form.get('contenu', '').strip()
    montant = request.form.get('montant')
    date_depense = request.form.get('date_depense')
    est_bon_achat = 1 if request.form.get('est_bon_achat') == 'on' else 0

    if not all([contenu, montant, date_depense]):
        flash("Les champs contenu, montant et date sont obligatoires.",
              "error")
        return redirect(request.referrer or url_for('budget'))

    if est_bon_achat:
        fournisseur_id = None
    elif not fournisseur_id:
        flash(
            "Veuillez sélectionner un fournisseur ou cocher la case "
            "'Bon d'achat'.", "error")
        return redirect(request.referrer or url_for('budget'))

    try:
        montant_float = float(montant.replace(',', '.'))
        db.execute(
            """UPDATE depenses SET fournisseur_id = ?, contenu = ?,
               montant = ?, date_depense = ?, est_bon_achat = ?
               WHERE id = ?""", (fournisseur_id, contenu, montant_float,
                                 date_depense, est_bon_achat, id))
        db.commit()
        flash("La dépense a été modifiée avec succès.", "success")
    except ValueError:
        flash("Le montant saisi est invalide.", "error")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(request.referrer or url_for('budget'))


@app.route("/budget/supprimer_depense/<int:id>", methods=['POST'])
@admin_required
def supprimer_depense(id):
    db = get_db()
    depense = db.execute("SELECT id FROM depenses WHERE id = ?",
                         (id, )).fetchone()
    if depense:
        try:
            db.execute("DELETE FROM depenses WHERE id = ?", (id, ))
            db.commit()
            flash("La dépense a été supprimée avec succès.", "success")
        except sqlite3.Error as e:
            db.rollback()
            flash(f"Erreur de base de données : {e}", "error")
    else:
        flash("Dépense non trouvée.", "error")

    return redirect(request.referrer or url_for('budget'))


@app.route("/budget/cloturer", methods=['POST'])
@admin_required
def cloturer_budget():
    budget_id = request.form.get('budget_id')
    db = get_db()
    
    budget = db.execute("SELECT * FROM budgets WHERE id = ?", (budget_id,)).fetchone()

    if not budget:
        flash("Budget non trouvé.", "error")
        return redirect(url_for('budget'))

    # --- VÉRIFICATION DE SÉCURITÉ CÔTÉ SERVEUR ---
    annee_fin_budget = budget['annee'] + 1
    date_limite_cloture = date(annee_fin_budget, 6, 1)
    if date.today() < date_limite_cloture:
        flash(f"La clôture du budget {annee_scolaire_format(budget['annee'])} n'est autorisée qu'à partir du {date_limite_cloture.strftime('%d/%m/%Y')}.", "error")
        return redirect(url_for('budget', annee=budget['annee']))

    if budget['cloture']:
        flash(f"Le budget pour l'année scolaire {annee_scolaire_format(budget['annee'])} est déjà clôturé.", "warning")
        return redirect(url_for('budget'))

    try:
        db.execute("UPDATE budgets SET cloture = 1 WHERE id = ?", (budget_id,))
        db.commit()
        flash(f"Le budget pour l'année scolaire {annee_scolaire_format(budget['annee'])} a été clôturé avec succès.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('budget'))


@app.route("/budget/exporter")
@admin_required
def exporter_budget():
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    format_type = request.args.get('format')

    if not all([date_debut, date_fin, format_type]):
        flash("Tous les champs sont requis pour l'export.", "error")
        return redirect(url_for('budget'))

    db = get_db()
    depenses_data = db.execute(
        """
        SELECT d.date_depense, d.contenu, d.montant, f.nom as fournisseur_nom
        FROM depenses d
        LEFT JOIN fournisseurs f ON d.fournisseur_id = f.id
        WHERE d.date_depense BETWEEN ? AND ?
        ORDER BY d.date_depense ASC
        """, (date_debut, date_fin)).fetchall()

    if not depenses_data:
        flash("Aucune dépense trouvée pour la période sélectionnée.",
              "warning")
        return redirect(url_for('budget'))

    if format_type == 'pdf':
        buffer = generer_budget_pdf(depenses_data, date_debut, date_fin)
        return send_file(buffer,
                         as_attachment=True,
                         download_name='rapport_depenses.pdf',
                         mimetype='application/pdf')
    elif format_type == 'excel':
        buffer = generer_budget_excel(depenses_data, date_debut, date_fin)
        return send_file(
            buffer,
            as_attachment=True,
            download_name='rapport_depenses.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    flash("Format d'exportation non valide.", "error")
    return redirect(url_for('budget'))


# --- ROUTES POUR LA GESTION DES ÉCHÉANCES ---
@app.route("/admin/echeances")
@admin_required
def gestion_echeances():
    db = get_db()
    echeances_brutes = db.execute(
        "SELECT * FROM echeances ORDER BY date_echeance ASC").fetchall()

    echeances_converties = []
    for echeance in echeances_brutes:
        echeance_dict = dict(echeance)
        echeance_dict['date_echeance'] = datetime.strptime(
            echeance['date_echeance'], '%Y-%m-%d').date()
        echeances_converties.append(echeance_dict)

    return render_template("admin_echeances.html",
                           echeances=echeances_converties,
                           date_actuelle=datetime.now().date(),
                           url_ajout=url_for('ajouter_echeance'))


@app.route("/admin/echeances/ajouter", methods=['POST'])
@admin_required
def ajouter_echeance():
    intitule = request.form.get('intitule', '').strip()
    date_echeance = request.form.get('date_echeance')
    details = request.form.get('details', '').strip()

    if not all([intitule, date_echeance]):
        flash("L'intitulé et la date d'échéance sont obligatoires.", "error")
        return redirect(url_for('gestion_echeances'))

    db = get_db()
    try:
        db.execute(
            "INSERT INTO echeances (intitule, date_echeance, details) "
            "VALUES (?, ?, ?)", (intitule, date_echeance, details or None))
        db.commit()
        flash("L'échéance a été ajoutée avec succès.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('gestion_echeances'))


@app.route("/admin/echeances/modifier/<int:id>", methods=['POST'])
@admin_required
def modifier_echeance(id):
    db = get_db()
    echeance = db.execute("SELECT id FROM echeances WHERE id = ?",
                          (id, )).fetchone()
    if not echeance:
        flash("Échéance non trouvée.", "error")
        return redirect(url_for('gestion_echeances'))

    intitule = request.form.get('intitule', '').strip()
    date_echeance = request.form.get('date_echeance')
    details = request.form.get('details', '').strip()
    traite = 1 if request.form.get('traite') == 'on' else 0

    if not all([intitule, date_echeance]):
        flash("L'intitulé et la date d'échéance sont obligatoires.", "error")
        return redirect(url_for('gestion_echeances'))

    try:
        db.execute(
            "UPDATE echeances SET intitule = ?, date_echeance = ?, "
            "details = ?, traite = ? WHERE id = ?",
            (intitule, date_echeance, details or None, traite, id))
        db.commit()
        flash("L'échéance a été modifiée avec succès.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('gestion_echeances'))


@app.route("/admin/echeances/supprimer/<int:id>", methods=['POST'])
@admin_required
def supprimer_echeance(id):
    db = get_db()
    echeance = db.execute("SELECT id FROM echeances WHERE id = ?",
                          (id, )).fetchone()
    if echeance:
        try:
            db.execute("DELETE FROM echeances WHERE id = ?", (id, ))
            db.commit()
            flash("L'échéance a été supprimée avec succès.", "success")
        except sqlite3.Error as e:
            db.rollback()
            flash(f"Erreur de base de données : {e}", "error")
    else:
        flash("Échéance non trouvée.", "error")

    return redirect(url_for('gestion_echeances'))


# --- ROUTES POUR LES RAPPORTS ---
@app.route("/admin/rapports", methods=['GET'])
@admin_required
def rapports():
    db = get_db()
    dernieres_actions = db.execute("""
        SELECT h.timestamp, h.action, o.nom as objet_nom, u.nom_utilisateur
        FROM historique h
        JOIN objets o ON h.objet_id = o.id
        JOIN utilisateurs u ON h.utilisateur_id = u.id
        ORDER BY h.timestamp DESC
        LIMIT 5
        """).fetchall()

    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()

    return render_template("rapports.html",
                           dernieres_actions=dernieres_actions,
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)

@app.route("/admin/rapports/exporter", methods=['GET'])
@admin_required
def exporter_rapports():
    db = get_db()
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')
    group_by = request.args.get('group_by')
    format_type = request.args.get('format')

    if not all([date_debut, date_fin, group_by, format_type]):
        flash("Tous les champs sont requis pour générer un rapport.", "error")
        return redirect(url_for('rapports'))

    try:
        date_fin_dt = datetime.strptime(date_fin, '%Y-%m-%d') + timedelta(days=1)
        date_fin_str = date_fin_dt.strftime('%Y-%m-%d')
    except ValueError:
        flash("Format de date invalide.", "error")
        return redirect(url_for('rapports'))

    query = """
        SELECT h.timestamp, h.action, h.details, o.nom as objet_nom,
               u.nom_utilisateur
        FROM historique h
        JOIN objets o ON h.objet_id = o.id
        JOIN utilisateurs u ON h.utilisateur_id = u.id
        WHERE h.timestamp >= ? AND h.timestamp < ?
    """
    order_clause = "ORDER BY h.timestamp ASC"
    if group_by == 'action':
        order_clause = "ORDER BY h.action ASC, h.timestamp ASC"
    query += order_clause

    historique_data = db.execute(query, (date_debut, date_fin_str)).fetchall()

    if not historique_data:
        flash("Aucune donnée d'historique trouvée pour la période sélectionnée.", "warning")
        return redirect(url_for('rapports'))

    if format_type == 'pdf':
        buffer = generer_rapport_pdf(historique_data, date_debut, date_fin, group_by)
        return send_file(buffer,
                         as_attachment=True,
                         download_name='rapport_activite.pdf',
                         mimetype='application/pdf')
    elif format_type == 'excel':
        buffer = generer_rapport_excel(historique_data, date_debut, date_fin, group_by)
        return send_file(
            buffer,
            as_attachment=True,
            download_name='rapport_activite.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    
    flash("Format d'exportation non valide.", "error")
    return redirect(url_for('rapports'))


@app.route("/objet/<int:objet_id>/telecharger_fds")
@login_required
def telecharger_fds_objet(objet_id):
    db = get_db()
    objet = db.execute(
        "SELECT fds_nom_original, fds_nom_securise FROM objets WHERE id = ?",
        (objet_id, )).fetchone()
    if objet and objet['fds_nom_securise']:
        try:
            return send_file(os.path.join(app.config['FDS_UPLOAD_FOLDER'],
                                          objet['fds_nom_securise']),
                             as_attachment=True,
                             download_name=objet['fds_nom_original'])
        except FileNotFoundError:
            flash("Le fichier FDS n'a pas été trouvé sur le serveur.", "error")
            return redirect(url_for('inventaire.voir_objet', objet_id=objet_id))
    else:
        flash("Cet objet n'a pas de FDS associée.", "error")
        return redirect(url_for('inventaire.voir_objet', objet_id=objet_id))


# --- ROUTES D'ACTION ---
@app.route("/ajouter", methods=["POST"])
@login_required
def ajouter():
    type_objet = request.form.get("type")
    nom = request.form.get("nom", "").strip()
    redirect_to = ("gestion_armoires"
                   if type_objet == "armoire" else "gestion_categories")
    if not nom:
        flash("Le nom ne peut pas être vide.", "error")
        return redirect(url_for(redirect_to))
    table_name = "armoires" if type_objet == "armoire" else "categories"
    db = get_db()
    try:
        db.execute(f"INSERT INTO {table_name} (nom) VALUES (?)", (nom, ))
        db.commit()
        flash(f"L'élément '{nom}' a été créé.", "success")
    except sqlite3.IntegrityError:
        flash(f"L'élément '{nom}' existe déjà.", "error")
    return redirect(url_for(redirect_to))

@app.route("/supprimer/<type_objet>/<int:id>", methods=["POST"])
@admin_required
def supprimer(type_objet, id):
    db = get_db()
    redirect_to = ("gestion_armoires"
                   if type_objet == "armoire" else "gestion_categories")
    if type_objet == "armoire":
        if db.execute("SELECT COUNT(id) FROM objets WHERE armoire_id = ?",
                      (id, )).fetchone()[0] > 0:
            flash(
                "Impossible de supprimer. Cette armoire contient encore "
                "des objets.", "error")
            return redirect(url_for(redirect_to))
    table_map = {"armoire": "armoires", "categorie": "categories"}
    if type_objet in table_map:
        table_name = table_map[type_objet]
        nom_element = db.execute(f"SELECT nom FROM {table_name} WHERE id = ?",
                                 (id, )).fetchone()
        db.execute(f"DELETE FROM {table_name} WHERE id = ?", (id, ))
        db.commit()
        if nom_element:
            flash(
                f"L'élément '{nom_element['nom']}' a été supprimé avec succès.",
                "success")
    else:
        flash("Type d'élément à supprimer non valide.", "error")
    return redirect(url_for(redirect_to))

@app.route("/modifier_armoire", methods=["POST"])
@admin_required
def modifier_armoire():
    data = request.get_json()
    armoire_id, nouveau_nom = data.get("id"), data.get("nom")
    if not all([armoire_id, nouveau_nom, nouveau_nom.strip()]):
        return jsonify(success=False, error="Données invalides"), 400
    db = get_db()
    try:
        db.execute("UPDATE armoires SET nom = ? WHERE id = ?",
                   (nouveau_nom.strip(), armoire_id))
        db.commit()
        return jsonify(success=True, nouveau_nom=nouveau_nom.strip())
    except sqlite3.IntegrityError:
        return jsonify(success=False,
                       error="Ce nom d'armoire existe déjà."), 500


@app.route("/modifier_categorie", methods=["POST"])
@admin_required
def modifier_categorie():
    data = request.get_json()
    categorie_id, nouveau_nom = data.get("id"), data.get("nom")
    if not all([categorie_id, nouveau_nom, nouveau_nom.strip()]):
        return jsonify(success=False, error="Données invalides"), 400
    db = get_db()
    try:
        db.execute("UPDATE categories SET nom = ? WHERE id = ?",
                   (nouveau_nom.strip(), categorie_id))
        db.commit()
        return jsonify(success=True, nouveau_nom=nouveau_nom.strip())
    except sqlite3.IntegrityError:
        return jsonify(success=False,
                       error="Ce nom de catégorie existe déjà."), 500


# --- ROUTES API ---
@app.route("/api/rechercher")
@login_required
def api_rechercher():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    db = get_db()
    resultats = db.execute(
        """SELECT o.id, o.nom, o.armoire_id, a.nom as armoire_nom,
                  c.nom as categorie_nom
           FROM objets o
           JOIN armoires a ON o.armoire_id = a.id
           JOIN categories c ON o.categorie_id = c.id
           WHERE unaccent(LOWER(o.nom)) LIKE unaccent(LOWER(?))
           LIMIT 10""", (f"%{query}%", )).fetchall()
    return jsonify([dict(row) for row in resultats])


@app.route("/api/reservations_par_mois/<int:year>/<int:month>")
@login_required
def api_reservations_par_mois(year, month):
    db = get_db()

    start_date_str = f"{year}-{str(month).zfill(2)}-01 00:00:00"

    if month == 12:
        end_date_str = f"{year + 1}-01-01 00:00:00"
    else:
        end_date_str = f"{year}-{str(month + 1).zfill(2)}-01 00:00:00"

    reservations = db.execute(
        """
        SELECT
            DATE(r.debut_reservation) as jour_reservation,
            r.groupe_id,
            r.utilisateur_id,
            u.nom_utilisateur
        FROM reservations r
        JOIN utilisateurs u ON r.utilisateur_id = u.id
        WHERE r.debut_reservation >= ? AND r.debut_reservation < ?
              AND r.groupe_id IS NOT NULL
        GROUP BY jour_reservation, r.groupe_id
        """, (start_date_str, end_date_str)).fetchall()

    results = {}
    for row in reservations:
        date = row['jour_reservation']
        if date not in results:
            results[date] = []

        results[date].append(
            {'is_mine': row['utilisateur_id'] == session['user_id']})
    return jsonify(results)


@app.route("/api/reservation_details/<groupe_id>")
@login_required
def api_reservation_details(groupe_id):
    db = get_db()
    reservations = db.execute(
        """
        SELECT r.quantite_reservee, o.id as objet_id, o.nom as objet_nom, 
               u.nom_utilisateur, r.utilisateur_id, r.kit_id, k.nom as kit_nom,
               r.debut_reservation, r.fin_reservation
        FROM reservations r
        JOIN objets o ON r.objet_id = o.id
        JOIN utilisateurs u ON r.utilisateur_id = u.id
        LEFT JOIN kits k ON r.kit_id = k.id
        WHERE r.groupe_id = ?
        """, (groupe_id, )).fetchall()

    if not reservations:
        return jsonify({'error': 'Réservation non trouvée'}), 404

    details = {
        'kits': {},
        'objets_manuels': [],
        'nom_utilisateur': reservations[0]['nom_utilisateur'],
        'utilisateur_id': reservations[0]['utilisateur_id'],
        'debut_reservation': reservations[0]['debut_reservation'],
        'fin_reservation': reservations[0]['fin_reservation']
    }

    objets_manuels_bruts = [dict(r) for r in reservations if r['kit_id'] is None]
    objets_kits_reserves = [r for r in reservations if r['kit_id'] is not None]

    kits_comptes = {}
    for r in objets_kits_reserves:
        if r['kit_id'] not in kits_comptes:
            kits_comptes[r['kit_id']] = {'nom': r['kit_nom'], 'objets_reserves': {}}
        kits_comptes[r['kit_id']]['objets_reserves'][r['objet_id']] = r['quantite_reservee']

    for kit_id, data in kits_comptes.items():
        objets_base_du_kit = db.execute("SELECT objet_id, quantite FROM kit_objets WHERE kit_id = ?", (kit_id,)).fetchall()
        if not objets_base_du_kit: continue
        
        id_objet_calcul, quantite_par_kit = next(((obj['objet_id'], obj['quantite']) for obj in objets_base_du_kit if obj['objet_id'] in data['objets_reserves']), (None, 0))

        if id_objet_calcul and quantite_par_kit > 0:
            quantite_reelle_reservee = data['objets_reserves'][id_objet_calcul]
            nombre_de_kits = quantite_reelle_reservee // quantite_par_kit
            details['kits'][str(kit_id)] = {'quantite': nombre_de_kits, 'nom': data['nom']}

    objets_manuels_agreges = {}
    for item in objets_manuels_bruts:
        obj_id = item['objet_id']
        nom = item['objet_nom'] 
        quantite = item['quantite_reservee']
        
        if obj_id not in objets_manuels_agreges:
            objets_manuels_agreges[obj_id] = {'nom': nom, 'quantite_reservee': 0}
        objets_manuels_agreges[obj_id]['quantite_reservee'] += quantite

    for obj_id, data in objets_manuels_agreges.items():
        details['objets_manuels'].append({
            'objet_id': obj_id,
            'nom': data['nom'],
            'quantite_reservee': data['quantite_reservee']
        })

    return jsonify(details)


@app.route("/api/reservation_data/<date>")
@login_required
def api_reservation_data(date):
    db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    objets_bruts = db.execute(
        f"""
        SELECT 
            o.id, o.nom, c.nom as categorie, o.quantite_physique,
            COALESCE((SELECT SUM(r.quantite_reservee) 
                      FROM reservations r 
                      WHERE r.objet_id = o.id AND r.fin_reservation > '{now_str}'), 0) as total_reserve
        FROM objets o
        JOIN categories c ON o.categorie_id = c.id
        ORDER BY c.nom, o.nom
        """
    ).fetchall()
    
    grouped_objets = {}
    objets_map = {}
    for row in objets_bruts:
        categorie_nom = row['categorie']
        if categorie_nom not in grouped_objets:
            grouped_objets[categorie_nom] = []
        
        quantite_disponible = row['quantite_physique'] - row['total_reserve']
        
        obj_data = {
            "id": row['id'],
            "nom": row['nom'],
            "quantite_totale": row['quantite_physique'],
            "quantite_disponible": quantite_disponible if quantite_disponible >= 0 else 0
        }
        grouped_objets[categorie_nom].append(obj_data)
        objets_map[row['id']] = obj_data

    kits = db.execute("SELECT id, nom, description FROM kits ORDER BY nom").fetchall()
    kits_details = []
    for kit in kits:
        objets_du_kit = db.execute("SELECT objet_id, quantite FROM kit_objets WHERE kit_id = ?", (kit['id'],)).fetchall()
        
        disponibilite_kit = 9999
        if not objets_du_kit:
            disponibilite_kit = 0
        else:
            for obj_in_kit in objets_du_kit:
                objet_data = objets_map.get(obj_in_kit['objet_id'])
                if not objet_data or obj_in_kit['quantite'] == 0:
                    disponibilite_kit = 0
                    break
                
                kits_possibles = math.floor(objet_data['quantite_disponible'] / obj_in_kit['quantite'])
                if kits_possibles < disponibilite_kit:
                    disponibilite_kit = kits_possibles

        kits_details.append({
            'id': kit['id'],
            'nom': kit['nom'],
            'description': kit['description'],
            'objets': [dict(o) for o in objets_du_kit],
            'disponibilite': disponibilite_kit if disponibilite_kit != 9999 else 0
        })

    return jsonify({'objets': grouped_objets, 'kits': kits_details})


# Cette route est obsolète mais nous la laissons vide pour ne pas créer d'erreur 404 si elle est appelée
@app.route("/api/reserver", methods=["POST"])
@login_required
def api_reserver():
    return jsonify(success=False, error="Cette route est obsolète."), 400


@app.route("/api/modifier_reservation", methods=["POST"])
@login_required
def api_modifier_reservation():
    data = request.get_json()
    groupe_id = data.get("groupe_id")
    db = get_db()
    
    try:
        # On utilise une transaction pour s'assurer que tout réussit ou tout échoue
        db.execute("BEGIN")
        
        # Étape 1: Supprimer l'ancienne réservation
        db.execute("DELETE FROM reservations WHERE groupe_id = ?", (groupe_id,))
        
        # Étape 2: Valider et insérer la nouvelle réservation comme un "mini-panier"
        creneau_key = f"{data['date']}_{data['heure_debut']}_{data['heure_fin']}"
        mini_cart = { creneau_key: data }
        
        response = api_valider_panier_interne(mini_cart, groupe_id_existant=groupe_id) 
        
        if response.get('success'):
            db.commit()
            flash("Réservation modifiée avec succès !", "success")
            return jsonify(success=True)
        else:
            db.rollback() # Annule la suppression si la nouvelle réservation échoue
            return jsonify(success=False, error=response.get('error', 'Erreur inconnue lors de la modification')), 400

    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return jsonify(success=False, error=f"Une erreur interne est survenue : {e}"), 500

def api_valider_panier_interne(cart_data, groupe_id_existant=None):
    db = get_db()
    user_id = session['user_id']
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        objets_requis = {}
        for creneau_key, resa_details in cart_data.items():
            for kit_id, kit_data in resa_details.get('kits', {}).items():
                objets_du_kit = db.execute("SELECT objet_id, quantite FROM kit_objets WHERE kit_id = ?", (kit_id,)).fetchall()
                for obj_in_kit in objets_du_kit:
                    objets_requis[obj_in_kit['objet_id']] = objets_requis.get(obj_in_kit['objet_id'], 0) + (obj_in_kit['quantite'] * kit_data.get('quantite', 0))
            for obj_id, obj_data in resa_details.get('objets', {}).items():
                objets_requis[int(obj_id)] = objets_requis.get(int(obj_id), 0) + obj_data.get('quantite', 0)

        for obj_id, quantite_demandee in objets_requis.items():
            if quantite_demandee <= 0: continue
            stock_info = db.execute("""SELECT o.nom, (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = o.id AND r.fin_reservation > ?), 0)) as quantite_disponible
                                        FROM objets o WHERE o.id = ?""", (now_str, objet_id,)).fetchone()
            if not stock_info or stock_info['quantite_disponible'] < quantite_demandee:
                return {'success': False, 'error': f"Stock insuffisant pour '{stock_info['nom']}'"}

        for creneau_key, resa_details in cart_data.items():
            groupe_id = groupe_id_existant or str(uuid.uuid4())
            debut_dt = datetime.strptime(f"{resa_details['date']} {resa_details['heure_debut']}", '%Y-%m-%d %H:%M')
            fin_dt = datetime.strptime(f"{resa_details['date']} {resa_details['heure_fin']}", '%Y-%m-%d %H:%M')
            
            final_reservations = {}
            for kit_id_str, kit_data in resa_details.get('kits', {}).items():
                objets_du_kit = db.execute("SELECT objet_id, quantite FROM kit_objets WHERE kit_id = ?", (kit_id_str,)).fetchall()
                for obj_in_kit in objets_du_kit:
                    key = (obj_in_kit['objet_id'], int(kit_id_str))
                    final_reservations[key] = final_reservations.get(key, 0) + (obj_in_kit['quantite'] * kit_data.get('quantite', 0))
            for obj_id_str, obj_data in resa_details.get('objets', {}).items():
                key = (int(obj_id_str), None)
                final_reservations[key] = final_reservations.get(key, 0) + obj_data.get('quantite', 0)

            for (obj_id, kit_id), quantite_totale in final_reservations.items():
                if quantite_totale > 0:
                    db.execute(
                        """INSERT INTO reservations (objet_id, quantite_reservee, debut_reservation, fin_reservation, utilisateur_id, groupe_id, kit_id)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (obj_id, quantite_totale, debut_dt, fin_dt, user_id, groupe_id, kit_id))
                    action = "Modification Réservation" if groupe_id_existant else "Réservation"
                    enregistrer_action(obj_id, action, f"Quantité: {quantite_totale} pour le {debut_dt.strftime('%d/%m/%Y')}")
        
        return {'success': True}
    except Exception as e:
        traceback.print_exc()
        return {'success': False, 'error': f"Erreur interne: {e}"}

@app.route("/api/valider_panier", methods=["POST"])
@login_required
def api_valider_panier():
    cart_data = request.get_json()
    if not cart_data:
        return jsonify(success=False, error="Le panier est vide."), 400

    db = get_db()
    try:
        # On utilise une transaction pour s'assurer que l'ensemble du panier est validé ou rien du tout.
        db.execute("BEGIN")
        response = api_valider_panier_interne(cart_data)
        
        if response.get('success'):
            db.commit()
            flash("Toutes vos réservations ont été confirmées avec succès !", "success")
            return jsonify(success=True)
        else:
            db.rollback()
            return jsonify(success=False, error=response.get('error')), 400
            
    except Exception as e:
        db.rollback()
        traceback.print_exc()
        return jsonify(success=False, error=f"Une erreur interne est survenue : {e}"), 500

@app.route("/api/supprimer_reservation", methods=["POST"])
@login_required
def api_supprimer_reservation():
    data = request.get_json()
    groupe_id = data.get("groupe_id")
    db = get_db()
    try:
        reservation_info = db.execute("SELECT utilisateur_id FROM reservations WHERE groupe_id = ? LIMIT 1", (groupe_id, )).fetchone()
        if not reservation_info:
            return jsonify(success=False, error="Réservation non trouvée."), 404
        if (session.get('user_role') != 'admin' and reservation_info['utilisateur_id'] != session['user_id']):
            return jsonify(success=False, error="Vous n'avez pas la permission de supprimer cette réservation."), 403
        
        db.execute("DELETE FROM reservations WHERE groupe_id = ?", (groupe_id,))
        db.commit()
        
        flash("La réservation a été annulée.", "success")
        return jsonify(success=True)
    except sqlite3.Error as e:
        db.rollback()
        return jsonify(success=False, error=str(e)), 500





@app.route("/api/suggestion_commande/<int:objet_id>")
@admin_required
def api_suggestion_commande(objet_id):
    db = get_db()

    date_limite = datetime.now() - timedelta(days=90)

    result = db.execute(
        """
        SELECT SUM(quantite_reservee)
        FROM reservations
        WHERE objet_id = ? AND debut_reservation >= ?
        """, (objet_id, date_limite)).fetchone()

    consommation = result[0] if result and result[0] is not None else 0

    suggestion = 0
    if consommation > 0:
        suggestion = math.ceil(consommation * 1.5)
    else:
        objet = db.execute("SELECT seuil FROM objets WHERE id = ?",
                           (objet_id, )).fetchone()
        if objet:
            suggestion = objet['seuil'] * 2
        else:
            suggestion = 5

    return jsonify(suggestion=suggestion, consommation=consommation)

# --- ROUTE POUR SERVIR LES IMAGES UPLOADÉES ---
from flask import send_from_directory

@app.route('/uploads/images/<path:filename>')
@login_required
def serve_image(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- ROUTES D'IMPORT/EXPORT ET EXÉCUTION ---
@app.route("/telecharger_db")
@admin_required
def telecharger_db():
    db = get_db()
    licence_row = db.execute("SELECT valeur FROM parametres WHERE cle = ?",
                             ('licence_statut', )).fetchone()
    is_pro = licence_row and licence_row['valeur'] == 'PRO'

    if not is_pro:
        flash(
            "Le téléchargement de la base de données est une fonctionnalité "
            "de la version Pro.", "warning")
        return redirect(url_for('admin.admin'))

    return send_file(DATABASE, as_attachment=True)


@app.route("/importer_db", methods=["POST"])
@admin_required
def importer_db():
    if 'fichier' not in request.files:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for('admin.admin'))
    fichier = request.files.get("fichier")
    if not fichier or fichier.filename == '':
        flash("Aucun fichier selecté.", "error")
        return redirect(url_for('admin.admin'))
    if fichier and fichier.filename.endswith(".db"):
        temp_db_path = DATABASE + ".tmp"
        fichier.save(temp_db_path)
        shutil.move(temp_db_path, DATABASE)
        flash("Base de données importée avec succès !", "success")
    else:
        flash("Le fichier fourni n'est pas une base de données valide (.db).",
              "error")
    return redirect(url_for('admin.admin'))


@app.route("/admin/exporter")
@admin_required
def generer_pdf(data):
    # ... (le début de la fonction est identique)
    for categorie, items in sorted(grouped_data.items()):
        # ...
        for i, item in enumerate(items):
            # ...
            pdf.cell(85, 7, item['nom'].encode('latin-1', 'replace').decode('latin-1'), 1, 0)
            # CORRECTION: Utiliser la bonne clé pour la quantité
            pdf.cell(20, 7, str(item['quantite_disponible']), 1, 0, 'C')
            pdf.cell(40, 7, item['armoire'].encode('latin-1', 'replace').decode('latin-1'), 1, 0)
            # ...
    return BytesIO(pdf.output())

def generer_excel(data):
    # ... (le début de la fonction est identique)
    for item in data:
        # ...
        # CORRECTION: Utiliser la bonne clé pour la quantité
        row_data = [
            item['categorie'], item['nom'], item['quantite_disponible'], item['armoire'],
            date_peremption_val
        ]
        for i, value in enumerate(row_data):
            cell = sheet.cell(row=row_index, column=start_col + i, value=value)
            cell.border = thin_border
            cell.alignment = center_align if i > 0 else Alignment(
                vertical='center')
            if isinstance(value, datetime):
                cell.number_format = 'DD/MM/YYYY'
            if is_even:
                cell.fill = even_row_fill
        if item['categorie'] != current_cat:
            if current_cat is not None and start_merge_row < row_index:
                sheet.merge_cells(start_row=start_merge_row,
                                  start_column=start_col,
                                  end_row=row_index - 1,
                                  end_column=start_col)
                cell = sheet.cell(row=start_merge_row, column=start_col)
                cell.font = category_font
                cell.alignment = category_align
            current_cat = item['categorie']
            start_merge_row = row_index
        row_index += 1
        is_even = not is_even
    if current_cat is not None and start_merge_row < row_index - 1:
        sheet.merge_cells(start_row=start_merge_row,
                          start_column=start_col,
                          end_row=row_index - 1,
                          end_column=start_col)
        cell = sheet.cell(row=start_merge_row, column=start_col)
        cell.font = category_font
        cell.alignment = category_align
    column_widths = {'B': 30, 'C': 50, 'D': 15, 'E': 30, 'F': 20}
    for col, width in column_widths.items():
        sheet.column_dimensions[col].width = width
    sheet.freeze_panes = 'A5'
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer


def generer_budget_pdf(data, date_debut, date_fin):
    pdf = PDFWithFooter()
    pdf.alias_nb_pages()
    pdf.add_page(orientation='P')
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport des Depenses', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(
        0, 10,
        f"Periode du {datetime.strptime(date_debut, '%Y-%m-%d').strftime('%d/%m/%Y')} "
        f"au {datetime.strptime(date_fin, '%Y-%m-%d').strftime('%d/%m/%Y')}",
        new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)

    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(25, 8, 'Date', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(50, 8, 'Fournisseur', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(85, 8, 'Contenu de la commande'.encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(30, 8, 'Montant (EUR)', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)

    pdf.set_font('Helvetica', '', 9)
    total_depenses = 0
    fill = False
    for item in data:
        pdf.set_fill_color(240, 240, 240)
        date_str = datetime.strptime(item['date_depense'], '%Y-%m-%d').strftime('%d/%m/%Y')
        fournisseur = (item['fournisseur_nom'] or 'N/A').encode('latin-1', 'replace').decode('latin-1')
        contenu = item['contenu'].encode('latin-1', 'replace').decode('latin-1')
        montant = item['montant']
        total_depenses += montant

        pdf.cell(25, 7, date_str, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=fill)
        pdf.cell(50, 7, fournisseur, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=fill)
        pdf.cell(85, 7, contenu, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L', fill=fill)
        pdf.cell(30, 7, f"{montant:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R', fill=fill)
        fill = not fill

    pdf.set_font('Helvetica', 'B', 10)
    total_text = 'Total des depenses'.encode('latin-1', 'replace').decode('latin-1')
    pdf.cell(160, 8, total_text, border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='R')
    pdf.cell(30, 8, f"{total_depenses:.2f}", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='R')

    return BytesIO(pdf.output())


def generer_budget_excel(data, date_debut, date_fin):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rapport des Depenses"

    title_font = Font(name='Calibri', size=16, bold=True)
    header_font = Font(name='Calibri', size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4A5568",
                              end_color="4A5568",
                              fill_type="solid")
    total_font = Font(name='Calibri', size=11, bold=True)

    center_align = Alignment(horizontal='center',
                             vertical='center',
                             wrap_text=True)
    right_align = Alignment(horizontal='right', vertical='center')
    thin_border_side = Side(style='thin', color="BFBFBF")
    cell_border = Border(left=thin_border_side,
                         right=thin_border_side,
                         top=thin_border_side,
                         bottom=thin_border_side)
    even_row_fill = PatternFill(start_color="F0F4F8",
                                end_color="F0F4F8",
                                fill_type="solid")

    sheet.merge_cells('B2:E2')
    sheet['B2'] = 'Rapport des Dépenses'
    sheet['B2'].font = title_font
    sheet['B2'].alignment = Alignment(horizontal='center')
    sheet.merge_cells('B3:E3')
    sheet['B3'] = (
        f"Période du "
        f"{datetime.strptime(date_debut, '%Y-%m-%d').strftime('%d/%m/%Y')} au "
        f"{datetime.strptime(date_fin, '%Y-%m-%d').strftime('%d/%m/%Y')}")
    sheet['B3'].font = Font(name='Calibri',
                            size=11,
                            italic=True,
                            color="6c7a89")
    sheet['B3'].alignment = Alignment(horizontal='center')

    headers = ["Date", "Fournisseur", "Contenu de la commande", "Montant (€)"]
    for i, header_text in enumerate(headers, start=2):
        cell = sheet.cell(row=5, column=i, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align
        cell.border = cell_border

    row_index = 6
    total_depenses = 0
    is_even = False
    for item in data:
        date_val = datetime.strptime(item['date_depense'], '%Y-%m-%d')
        montant = item['montant']
        total_depenses += montant

        sheet.cell(row=row_index, column=2,
                   value=date_val).number_format = 'DD/MM/YYYY'
        sheet.cell(row=row_index,
                   column=3,
                   value=item['fournisseur_nom'] or 'N/A')
        sheet.cell(row=row_index, column=4, value=item['contenu'])
        sheet.cell(row=row_index, column=5,
                   value=montant).number_format = '#,##0.00'

        for col_idx in range(2, 6):
            cell = sheet.cell(row=row_index, column=col_idx)
            cell.border = cell_border
            if col_idx == 5:
                cell.alignment = right_align
            else:
                cell.alignment = center_align

            if is_even:
                cell.fill = even_row_fill

        is_even = not is_even
        row_index += 1

    total_cell_label = sheet.cell(row=row_index,
                                  column=4,
                                  value="Total des dépenses")
    total_cell_label.font = total_font
    total_cell_label.alignment = right_align
    total_cell_label.border = cell_border

    total_cell_value = sheet.cell(row=row_index,
                                  column=5,
                                  value=total_depenses)
    total_cell_value.font = total_font
    total_cell_value.number_format = '#,##0.00'
    total_cell_value.alignment = right_align
    total_cell_value.border = cell_border

    sheet.column_dimensions['B'].width = 15
    sheet.column_dimensions['C'].width = 30
    sheet.column_dimensions['D'].width = 50
    sheet.column_dimensions['E'].width = 15

    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static', 'icons'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route("/admin/exporter_inventaire")
@admin_required
def exporter_inventaire():
    db = get_db()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    inventaire_data = db.execute("""
        SELECT 
            o.nom, 
            c.nom AS categorie,
            a.nom AS armoire,
            (o.quantite_physique - COALESCE(SUM(r.quantite_reservee), 0)) as quantite_disponible,
            o.seuil,
            o.date_peremption
        FROM objets o 
        JOIN armoires a ON o.armoire_id = a.id
        JOIN categories c ON o.categorie_id = c.id
        LEFT JOIN reservations r ON o.id = r.objet_id AND r.fin_reservation > ?
        GROUP BY o.id, o.nom, c.nom, a.nom, o.seuil, o.date_peremption
        ORDER BY c.nom, o.nom
    """, (now_str,)).fetchall()
        
    format_type = request.args.get('format')
    if format_type == 'pdf':
        buffer = generer_inventaire_pdf(inventaire_data)
        return send_file(buffer, as_attachment=True, download_name='inventaire_complet.pdf', mimetype='application/pdf')
    elif format_type == 'excel':
        buffer = generer_inventaire_excel(inventaire_data)
        return send_file(buffer, as_attachment=True, download_name='inventaire_complet.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    
    flash("Format d'exportation non valide.","error")
    return redirect(url_for('admin.admin'))

def generer_inventaire_pdf(data):
    pdf = PDFWithFooter()
    pdf.alias_nb_pages()
    pdf.add_page(orientation='L')
    
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Inventaire Complet du Laboratoire', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(0, 10, f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(10)

    # En-têtes du tableau
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(50, 8, 'Catégorie', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(80, 8, 'Nom de l\'objet', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(25, 8, 'Qté Dispo', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(20, 8, 'Seuil', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(50, 8, 'Armoire', border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C', fill=True)
    pdf.cell(30, 8, 'Péremption', border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C', fill=True)
    
    # Regrouper les données par catégorie
    grouped_data = {}
    for item in data:
        cat = item['categorie']
        if cat not in grouped_data:
            grouped_data[cat] = []
        grouped_data[cat].append(item)

    # === NOUVELLE LOGIQUE DE DESSIN FIABLE ===
    pdf.set_font('Helvetica', '', 8)
    for categorie, items in sorted(grouped_data.items()):
        row_count = len(items)
        
        # On sauvegarde la position de départ avant de dessiner le bloc de la catégorie
        start_y = pdf.get_y()
        start_x = pdf.get_x()

        # On dessine les lignes de données en premier
        for i, item in enumerate(items):
            date_peremption_str = ""
            if item['date_peremption']:
                try:
                    date_obj = datetime.strptime(item['date_peremption'], '%Y-%m-%d')
                    date_peremption_str = date_obj.strftime('%d/%m/%Y')
                except (ValueError, TypeError):
                    date_peremption_str = item['date_peremption']

            # On se positionne à droite de la future cellule "Catégorie"
            pdf.set_x(start_x + 50)
            
            pdf.cell(80, 7, item['nom'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='L')
            pdf.cell(25, 7, str(item['quantite_disponible']), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(20, 7, str(item['seuil']), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(50, 7, item['armoire'].encode('latin-1', 'replace').decode('latin-1'), border=1, new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')
            pdf.cell(30, 7, date_peremption_str, border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

        # On calcule la hauteur totale du bloc qu'on vient de dessiner
        end_y = pdf.get_y()
        total_height = end_y - start_y

        # Maintenant, on dessine la cellule "Catégorie" fusionnée par-dessus
        pdf.set_y(start_y)
        pdf.set_x(start_x)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.multi_cell(50, total_height, categorie.encode('latin-1', 'replace').decode('latin-1'), border=1, align='C')
        pdf.set_font('Helvetica', '', 8)

        # On s'assure que le curseur est bien positionné pour la prochaine catégorie
        pdf.set_y(end_y)
        
    return BytesIO(pdf.output())

def generer_inventaire_excel(data):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Inventaire Complet"

    # Styles (inchangés)
    title_font = Font(name='Calibri', size=16, bold=True)
    header_font = Font(name='Calibri', size=11, bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4A5568", end_color="4A5568", fill_type="solid")
    center_align = Alignment(horizontal='center', vertical='center')
    left_align = Alignment(horizontal='left', vertical='center')
    # NOUVEAU : Style pour les cellules fusionnées
    category_align = Alignment(horizontal='left', vertical='center')


    # Titre et date (inchangés)
    sheet.merge_cells('A1:F1')
    sheet['A1'] = 'Inventaire Complet du Laboratoire'
    sheet['A1'].font = title_font
    sheet['A1'].alignment = center_align
    sheet.merge_cells('A2:F2')
    sheet['A2'] = f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
    
    # En-têtes (inchangés)
    headers = ["Catégorie", "Nom de l'objet", "Quantité Disponible", "Seuil", "Armoire", "Date de Péremption"]
    for i, header_text in enumerate(headers, start=1):
        cell = sheet.cell(row=4, column=i, value=header_text)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = center_align

    # === NOUVELLE LOGIQUE POUR LES DONNÉES AVEC FUSION ===
    row_index = 5
    current_category = None
    start_merge_row = 5 # La première ligne de données

    for item in data:
        # Si la catégorie change par rapport à la ligne précédente
        if item['categorie'] != current_category:
            # Et si ce n'est pas la toute première ligne...
            if current_category is not None:
                # ...alors on fusionne le bloc de la catégorie précédente.
                if start_merge_row < row_index - 1:
                    sheet.merge_cells(start_row=start_merge_row, start_column=1, end_row=row_index - 1, end_column=1)
                    # On applique l'alignement vertical à la cellule fusionnée
                    sheet.cell(row=start_merge_row, column=1).alignment = category_align
            
            # On met à jour pour la nouvelle catégorie
            current_category = item['categorie']
            start_merge_row = row_index

        # On écrit les données de la ligne actuelle
        sheet.cell(row=row_index, column=1, value=item['categorie']) # On écrit la catégorie sur chaque ligne
        sheet.cell(row=row_index, column=2, value=item['nom']).alignment = left_align
        sheet.cell(row=row_index, column=3, value=item['quantite_disponible']).alignment = center_align
        sheet.cell(row=row_index, column=4, value=item['seuil']).alignment = center_align
        
        # CORRECTION : On centre la colonne "Armoire"
        armoire_cell = sheet.cell(row=row_index, column=5, value=item['armoire'])
        armoire_cell.alignment = center_align
        
        date_cell = sheet.cell(row=row_index, column=6)
        if item['date_peremption']:
            date_cell.value = datetime.strptime(item['date_peremption'], '%Y-%m-%d')
            date_cell.number_format = 'DD/MM/YYYY'
        date_cell.alignment = center_align
        
        row_index += 1

    # Après la fin de la boucle, il faut fusionner le DERNIER bloc de catégories
    if current_category is not None and start_merge_row < row_index - 1:
        sheet.merge_cells(start_row=start_merge_row, start_column=1, end_row=row_index - 1, end_column=1)
        sheet.cell(row=start_merge_row, column=1).alignment = category_align
    # ==========================================================

    # Largeur des colonnes et freeze (inchangés)
    sheet.column_dimensions['A'].width = 30
    sheet.column_dimensions['B'].width = 50
    sheet.column_dimensions['C'].width = 20
    sheet.column_dimensions['D'].width = 10
    sheet.column_dimensions['E'].width = 30
    sheet.column_dimensions['F'].width = 20
    
    sheet.freeze_panes = 'A5'
    buffer = BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer

if __name__ == "__main__":
    import webbrowser
    from threading import Timer

    def open_browser():
        webbrowser.open_new("http://127.0.0.1:5000")

    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        Timer(1, open_browser).start()

    app.run(debug=True, threaded=True)