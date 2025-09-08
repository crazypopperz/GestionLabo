import sqlite3
import os
import unicodedata
from flask import g, current_app

def strip_accents(text):
    """Fonction pour retirer les accents d'une chaîne."""
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(current_app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        db.create_function("unaccent", 1, strip_accents)
    return db

def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Crée les tables de la base de données si elle n'existe pas."""
    db_path = current_app.config['DATABASE']
    if not os.path.exists(db_path):
        print(f"Le fichier de base de données n'existe pas. Création...")
        try:
            db = sqlite3.connect(db_path)
            
            schema_script = """
                BEGIN TRANSACTION;
                CREATE TABLE IF NOT EXISTS "armoires" (
                    "id"	INTEGER, "nom" TEXT NOT NULL UNIQUE, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "budgets" (
                    "id"	INTEGER, "annee" INTEGER NOT NULL UNIQUE, "montant_initial"	REAL NOT NULL, "cloture" BOOLEAN NOT NULL DEFAULT 0, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "categories" (
                    "id"	INTEGER, "nom" TEXT NOT NULL UNIQUE, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "fournisseurs" (
                    "id"	INTEGER, "nom" TEXT NOT NULL UNIQUE, "site_web" TEXT, "logo" TEXT, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "depenses" (
                    "id" INTEGER, "budget_id" INTEGER NOT NULL, "fournisseur_id" INTEGER, "contenu" TEXT NOT NULL, "montant" REAL NOT NULL, "date_depense" DATE NOT NULL, "est_bon_achat" INTEGER NOT NULL DEFAULT 0, PRIMARY KEY("id" AUTOINCREMENT), FOREIGN KEY("budget_id") REFERENCES "budgets"("id"), FOREIGN KEY("fournisseur_id") REFERENCES "fournisseurs"("id") ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS "echeances" (
                    "id" INTEGER, "intitule" TEXT NOT NULL, "date_echeance" DATE NOT NULL, "details" TEXT, "traite" INTEGER NOT NULL DEFAULT 0, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "utilisateurs" (
                    "id" INTEGER, "nom_utilisateur" TEXT NOT NULL UNIQUE, "mot_de_passe" TEXT NOT NULL, "role" TEXT NOT NULL DEFAULT 'utilisateur', "email" TEXT, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "kits" (
                    "id" INTEGER NOT NULL, "nom" TEXT NOT NULL UNIQUE, "description" TEXT, PRIMARY KEY("id" AUTOINCREMENT)
                );
                CREATE TABLE IF NOT EXISTS "objets" (
                    "id"	INTEGER,
                    "nom"	TEXT NOT NULL,
                    "quantite_physique"	INTEGER NOT NULL, -- La colonne "quantite" a été renommée
                    "seuil"	INTEGER NOT NULL,
                    "image"	TEXT,
                    "armoire_id"	INTEGER NOT NULL,
                    "categorie_id"	INTEGER NOT NULL,
                    "en_commande"	INTEGER DEFAULT 0,
                    "date_peremption"	TEXT,
                    "traite"	INTEGER NOT NULL DEFAULT 0,
                    "fds_nom_original"	TEXT,
                    "fds_nom_securise"	TEXT,
                    PRIMARY KEY("id" AUTOINCREMENT),
                    FOREIGN KEY("armoire_id") REFERENCES "armoires"("id") ON DELETE RESTRICT,
                    FOREIGN KEY("categorie_id") REFERENCES "categories"("id") ON DELETE RESTRICT
                );
                CREATE TABLE IF NOT EXISTS "historique" (
                    "id" INTEGER, "objet_id" INTEGER NOT NULL, "utilisateur_id" INTEGER NOT NULL, "action" TEXT NOT NULL, "details" TEXT, "timestamp" DATETIME NOT NULL, PRIMARY KEY("id" AUTOINCREMENT), FOREIGN KEY("objet_id") REFERENCES "objets"("id") ON DELETE CASCADE, FOREIGN KEY("utilisateur_id") REFERENCES "utilisateurs"("id") ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS "kit_objets" (
                    "id" INTEGER NOT NULL, "kit_id" INTEGER NOT NULL, "objet_id" INTEGER NOT NULL, "quantite" INTEGER NOT NULL, PRIMARY KEY("id" AUTOINCREMENT), FOREIGN KEY("kit_id") REFERENCES "kits"("id") ON DELETE CASCADE, FOREIGN KEY("objet_id") REFERENCES "objets"("id") ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS "parametres" (
                    "cle" TEXT, "valeur" TEXT, PRIMARY KEY("cle")
                );
                CREATE TABLE IF NOT EXISTS "reservations" (
                    "id" INTEGER, "objet_id" INTEGER NOT NULL, "utilisateur_id" INTEGER NOT NULL, "quantite_reservee" INTEGER NOT NULL, "debut_reservation" DATETIME NOT NULL, "fin_reservation" DATETIME NOT NULL, "groupe_id" TEXT, "kit_id" INTEGER, PRIMARY KEY("id" AUTOINCREMENT), FOREIGN KEY("kit_id") REFERENCES "kits"("id"), FOREIGN KEY("objet_id") REFERENCES "objets"("id"), FOREIGN KEY("utilisateur_id") REFERENCES "utilisateurs"("id")
                );
                INSERT INTO "parametres" ("cle", "valeur") VALUES ('licence_statut', 'FREE');
                INSERT INTO "parametres" ("cle", "valeur") VALUES ('licence_cle', '');
                COMMIT;
            """
            
            db.executescript(schema_script)
            db.close()
            print("Base de données et schéma initialisés avec succès.")
        except sqlite3.Error as e:
            print(f"Erreur critique lors de l'initialisation de la base de données : {e}")
            if os.path.exists(db_path):
               os.remove(db_path)

def init_db_command(app):
    if 'init-db' not in app.cli.commands:
        @app.cli.command('init-db')
        def init_db_cmd():
            """Crée les tables de la base de données."""
            with app.app_context():
                init_db()
            print('Base de données initialisée.')
        app.cli.add_command(init_db_cmd)

def init_app(app):
    """Enregistre les fonctions de la base de données avec l'application Flask."""
    app.teardown_appcontext(close_connection)
    init_db_command(app)