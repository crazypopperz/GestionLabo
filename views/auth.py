from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session)
from utils import login_required
from db import get_db
from utils import is_setup_needed

auth_bp = Blueprint(
    'auth', 
    __name__,
    template_folder='../templates'
)

@auth_bp.route("/login", methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        db = get_db()
        user = db.execute(
            'SELECT * FROM utilisateurs WHERE nom_utilisateur = ?',
            (username, )).fetchone()
        if user and check_password_hash(user['mot_de_passe'], password):
            session.permanent = (user['role'] != 'admin')
            session['user_id'] = user['id']
            session['username'] = user['nom_utilisateur']
            session['user_role'] = user['role']
            flash(f"Bienvenue, {user['nom_utilisateur']} !", "success")
            return redirect(url_for('index'))
        else:
            flash("Nom d'utilisateur ou mot de passe invalide.", "error")
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if is_setup_needed():
        return redirect(url_for('auth.setup'))
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        email = request.form.get('email').strip()
        if not username or not password or not email:
            flash("Tous les champs sont requis.", "error")
            return redirect(url_for('auth.register'))
        db = get_db()
        try:
            db.execute(
                "INSERT INTO utilisateurs (nom_utilisateur, mot_de_passe, "
                "email) VALUES (?, ?, ?)",
                (username, generate_password_hash(password,
                                                  method='scrypt'), email))
            db.commit()
            flash(
                f"Le compte '{username}' a été créé. "
                "Vous pouvez maintenant vous connecter.", "success")
            return redirect(url_for('auth.login'))
        except sqlite3.IntegrityError:
            flash(f"Le nom d'utilisateur '{username}' existe déjà.", "error")
            return redirect(url_for('auth.register'))
    return render_template('register.html')

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Vous avez été déconnecté.", "success")
    return redirect(url_for('auth.login'))

@auth_bp.route("/profil", methods=['GET', 'POST'])
@login_required
def profil():
    db = get_db()
    user_id = session['user_id']
    if request.method == 'POST':
        ancien_mdp = request.form.get('ancien_mot_de_passe')
        nouveau_mdp = request.form.get('nouveau_mot_de_passe')
        confirmation_mdp = request.form.get('confirmation_mot_de_passe')
        user = db.execute("SELECT mot_de_passe FROM utilisateurs WHERE id = ?",
                          (user_id, )).fetchone()
        if not user or not check_password_hash(user['mot_de_passe'],
                                               ancien_mdp):
            flash("Votre ancien mot de passe est incorrect.", "error")
            return redirect(url_for('auth.profil'))
        if len(nouveau_mdp) < 12 or \
           not re.search(r"[a-z]", nouveau_mdp) or \
           not re.search(r"[A-Z]", nouveau_mdp) or \
           not re.search(r"[0-9]", nouveau_mdp) or \
           not re.search(r"[!@#$%^&*(),.?:{}|<>]", nouveau_mdp):
            flash("Le nouveau mot de passe doit contenir au moins 12 caractères, "
                  "incluant une majuscule, une minuscule, un chiffre et "
                  "un caractère spécial.", "error")
            return redirect(url_for('auth.profil'))
        if len(nouveau_mdp) < 4:
            flash(
                "Le nouveau mot de passe doit contenir au moins 4 caractères.",
                "error")
            return redirect(url_for('auth.profil'))
        try:
            db.execute("UPDATE utilisateurs SET mot_de_passe = ? WHERE id = ?",
                       (generate_password_hash(nouveau_mdp,
                                               method='scrypt'), user_id))
            db.commit()
            flash("Votre mot de passe a été mis à jour avec succès.",
                  "success")
            return redirect(url_for('index'))
        except sqlite3.Error as e:
            db.rollback()
            flash(f"Erreur de base de données : {e}", "error")
    armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    return render_template("profil.html",
                           armoires=armoires,
                           categories=categories,
                           now=datetime.now)

@auth_bp.route("/setup", methods=['GET', 'POST'])
def setup():
    if not is_setup_needed():
        flash("L'application est déjà configurée.", "error")
        return redirect(url_for('login'))
    
    db = get_db()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        email = request.form.get('email', '').strip()
        if not all([username, password, password_confirm, email]):
            flash("Tous les champs sont requis.", "error")
            return redirect(url_for('auth.setup'))
        if len(password) < 12 or \
           not re.search(r"[a-z]", password) or \
           not re.search(r"[A-Z]", password) or \
           not re.search(r"[0-9]", password) or \
           not re.search(r"[!@#$%^&*(),.?:{}|<>]", password):
            flash("Le mot de passe doit contenir au moins 12 caractères, "
                  "incluant une majuscule, une minuscule, un chiffre et "
                  "un caractère spécial.", "error")
            return redirect(url_for('auth.setup'))
        if password != password_confirm:
            flash("Les mots de passe ne correspondent pas.", "error")
            return redirect(url_for('auth.setup'))
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, email):
            flash("L'adresse e-mail fournie n'est pas valide.", "error")
            return redirect(url_for('auth.setup'))
        
        db.execute(
            "INSERT INTO utilisateurs (nom_utilisateur, mot_de_passe, role, "
            "email) VALUES (?, ?, 'admin', ?)",
            (username, generate_password_hash(password, method='scrypt'), email))
        
        instance_id = str(uuid.uuid4())
        db.execute(
            "INSERT OR IGNORE INTO parametres (cle, valeur) VALUES (?, ?)",
            ('instance_id', instance_id))
        db.commit()
        
        flash(
            f"Administrateur '{username}' créé avec succès ! "
            "Vous pouvez maintenant vous connecter.", "success")
        return redirect(url_for('auth.login'))

    # Si la méthode est GET, on affiche simplement la page de configuration.
    # Il n'y a plus besoin de charger de données.
    return render_template('setup.html')

    # On fournit des listes vides au template au cas où les tables n'existeraient pas encore
    armoires = []
    categories = []
    try:
        armoires = db.execute("SELECT * FROM armoires ORDER BY nom").fetchall()
        categories = db.execute("SELECT * FROM categories ORDER BY nom").fetchall()
    except sqlite3.OperationalError:
        # Les tables n'existent pas encore, ce qui est normal au premier setup
        pass
        
    return render_template('setup.html', armoires=armoires, categories=categories)