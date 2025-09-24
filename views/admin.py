# ============================================================
# IMPORTS
# ============================================================

# Imports depuis la bibliothèque standard
import hashlib
from datetime import datetime, date, timedelta

# Imports depuis les bibliothèques tierces (Flask, etc.)
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, jsonify, send_file)
from werkzeug.security import check_password_hash, generate_password_hash

# Imports depuis nos propres modules
from db import get_db
from utils import admin_required, login_required
# On importera d'autres fonctions de utils au besoin

# ============================================================
# CRÉATION DU BLUEPRINT POUR L'ADMINISTRATION
# ============================================================
# On utilise url_prefix pour que toutes les routes de ce blueprint
# commencent automatiquement par /admin
admin_bp = Blueprint(
    'admin', 
    __name__,
    template_folder='../templates',
    url_prefix='/admin'
)

# ============================================================
# LES FONCTIONS DE ROUTES ADMIN
# ============================================================
@admin_bp.route("/admin")
@admin_required
def admin():
    db = get_db()
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("admin.html",
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)

#=== GESTION UTILISATEURS ===
@admin_bp.route("/utilisateurs")
@admin_required
def gestion_utilisateurs():
    db = get_db()
    utilisateurs = db.execute(
        "SELECT id, nom_utilisateur, role, email FROM utilisateurs "
        "ORDER BY nom_utilisateur").fetchall()
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("admin_utilisateurs.html",
                           utilisateurs=utilisateurs,
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)


#=== MODIFIER EMAIL ===
@admin_bp.route("/utilisateurs/modifier_email/<int:id_user>",
           methods=["POST"])
@admin_required
def modifier_email_utilisateur(id_user):
    email = request.form.get('email', '').strip()
    if not email or '@' not in email:
        flash("Veuillez fournir une adresse e-mail valide.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))

    db = get_db()
    user = db.execute("SELECT nom_utilisateur FROM utilisateurs WHERE id = ?",
                      (id_user, )).fetchone()
    if not user:
        flash("Utilisateur non trouvé.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))

    try:
        db.execute("UPDATE utilisateurs SET email = ? WHERE id = ?",
                   (email, id_user))
        db.commit()
        flash(
            f"L'adresse e-mail pour '{user['nom_utilisateur']}' a été "
            "mise à jour.", "success")
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Erreur de base de données : {e}", "error")

    return redirect(url_for('admin.gestion_utilisateurs'))

#=== SUPPRIMER UTILISATEUR ===
@admin_bp.route("/utilisateurs/supprimer/<int:id_user>", methods=["POST"])
@admin_required
def supprimer_utilisateur(id_user):
    if id_user == session['user_id']:
        flash("Vous ne pouvez pas supprimer votre propre compte.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))
    db = get_db()
    user = db.execute("SELECT nom_utilisateur FROM utilisateurs WHERE id = ?",
                      (id_user, )).fetchone()
    if user:
        db.execute("DELETE FROM utilisateurs WHERE id = ?", (id_user, ))
        db.commit()
        flash(f"L'utilisateur '{user['nom_utilisateur']}' a été supprimé.",
              "success")
    else:
        flash("Utilisateur non trouvé.", "error")
    return redirect(url_for('admin.gestion_utilisateurs'))

#=== PROMOUVOIR UTILISATEUR ===
@admin_bp.route("/utilisateurs/promouvoir/<int:id_user>", methods=["POST"])
@admin_required
def promouvoir_utilisateur(id_user):
    if id_user == session['user_id']:
        flash("Action non autorisée sur votre propre compte.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))
    password = request.form.get('password')
    db = get_db()
    admin_actuel = db.execute(
        "SELECT mot_de_passe FROM utilisateurs WHERE id = ?",
        (session['user_id'], )).fetchone()
    if not admin_actuel or not check_password_hash(
            admin_actuel['mot_de_passe'], password):
        flash(
            "Mot de passe administrateur incorrect. "
            "La passation de pouvoir a échoué.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))
    try:
        db.execute("UPDATE utilisateurs SET role = 'admin' WHERE id = ?",
                   (id_user, ))
        db.execute("UPDATE utilisateurs SET role = 'utilisateur' WHERE id = ?",
                   (session['user_id'], ))
        db.commit()
        flash(
            "Passation de pouvoir réussie ! "
            "Vous êtes maintenant un utilisateur standard.", "success")
        return redirect(url_for('auth.logout'))
    except sqlite3.Error as e:
        db.rollback()
        flash(f"Une erreur est survenue lors de la passation de pouvoir : {e}",
              "error")
        return redirect(url_for('admin.gestion_utilisateurs'))

#=== REINITIALISER MDP ===
@admin_bp.route("/admin/utilisateurs/reinitialiser_mdp/<int:id_user>",
           methods=["POST"])
@admin_required
def reinitialiser_mdp(id_user):
    if id_user == session['user_id']:
        flash(
            "Vous ne pouvez pas réinitialiser votre propre mot de passe ici.",
            "error")
        return redirect(url_for('admin.gestion_utilisateurs'))
    nouveau_mdp = request.form.get('nouveau_mot_de_passe')
    if not nouveau_mdp or len(nouveau_mdp) < 4:
        flash(
            "Le nouveau mot de passe est requis et doit contenir "
            "au moins 4 caractères.", "error")
        return redirect(url_for('admin.gestion_utilisateurs'))
    db = get_db()
    user = db.execute("SELECT nom_utilisateur FROM utilisateurs WHERE id = ?",
                      (id_user, )).fetchone()
    if user:
        try:
            db.execute("UPDATE utilisateurs SET mot_de_passe = ? WHERE id = ?",
                       (generate_password_hash(nouveau_mdp,
                                               method='scrypt'), id_user))
            db.commit()
            flash(
                f"Le mot de passe pour l'utilisateur "
                f"'{user['nom_utilisateur']}' a été réinitialisé avec succès.",
                "success")
        except sqlite3.Error as e:
            db.rollback()
            flash(f"Erreur de base de données : {e}", "error")
    else:
        flash("Utilisateur non trouvé.", "error")
    return redirect(url_for('admin.gestion_utilisateurs'))


#=== GESTION KITS ===
@admin_bp.route("/kits")
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

#=== AJOUTER KIT ===
@admin_bp.route("/kits/ajouter", methods=["POST"])
@admin_required
def ajouter_kit():
    nom = request.form.get("nom", "").strip()
    description = request.form.get("description", "").strip()
    if not nom:
        flash("Le nom du kit ne peut pas être vide.", "error")
        return redirect(url_for('admin.gestion_kits'))

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
        return redirect(url_for('admin.modifier_kit', kit_id=new_kit_id))
    except sqlite3.IntegrityError:
        flash(f"Un kit avec le nom '{nom}' existe déjà.", "error")
        return redirect(url_for('admin.gestion_kits'))

#=== MODIFIER KIT ===
@admin_bp.route("/kits/modifier/<int:kit_id>", methods=["GET", "POST"])
@admin_required
def modifier_kit(kit_id):
    db = get_db()
    kit = db.execute("SELECT * FROM kits WHERE id = ?", (kit_id, )).fetchone()
    if not kit:
        flash("Kit non trouvé.", "error")
        return redirect(url_for('admin.gestion_kits'))

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if request.method == "POST":
        objet_id_str = request.form.get("objet_id")
        quantite_str = request.form.get("quantite")

        if objet_id_str and quantite_str:
            try:
                objet_id = int(objet_id_str)
                quantite = int(quantite_str)
                stock_info = db.execute(
                    f"""
                    SELECT o.nom, (o.quantite_physique - COALESCE((SELECT SUM(r.quantite_reservee) FROM reservations r WHERE r.objet_id = o.id AND r.fin_reservation > '{now_str}'), 0)) as quantite_disponible
                    FROM objets o WHERE o.id = ?
                    """, (objet_id,)
                ).fetchone()

                if not stock_info:
                    flash("Objet non trouvé.", "error")
                    return redirect(url_for('admin.modifier_kit', kit_id=kit_id))

                if quantite > stock_info['quantite_disponible']:
                    flash(f"Quantité invalide pour '{stock_info['nom']}'. Vous ne pouvez pas ajouter plus que le stock disponible ({stock_info['quantite_disponible']}).", "error")
                    return redirect(url_for('admin.modifier_kit', kit_id=kit_id))

                existing = db.execute("SELECT id FROM kit_objets WHERE kit_id = ? AND objet_id = ?", (kit_id, objet_id)).fetchone()
                if existing:
                    db.execute("UPDATE kit_objets SET quantite = ? WHERE id = ?", (quantite, existing['id']))
                else:
                    db.execute("INSERT INTO kit_objets (kit_id, objet_id, quantite) VALUES (?, ?, ?)", (kit_id, objet_id, quantite))
                db.commit()
                flash(f"L'objet '{stock_info['nom']}' a été ajouté/mis à jour dans le kit.", "success")

            except (ValueError, TypeError):
                flash("Données invalides.", "error")
            
            return redirect(url_for('admin.modifier_kit', kit_id=kit_id))

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
        return redirect(url_for('admin.modifier_kit', kit_id=kit_id))

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


#=== RETIRER OBJET DUN KIT ===
@admin_bp.route("/kits/retirer_objet/<int:kit_objet_id>")
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
        return redirect(url_for('admin.modifier_kit', kit_id=kit_id))
    flash("Erreur : objet du kit non trouvé.", "error")
    return redirect(url_for('admin.gestion_kits'))


#=== SUPPRIMER KIT ===
@admin_bp.route("/kits/supprimer/<int:kit_id>", methods=["POST"])
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
    return redirect(url_for('admin.gestion_kits'))