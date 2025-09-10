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
# LES FONCTIONS DE ROUTES SERONT COLLÉES ICI
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