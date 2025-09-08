-- schema.sql (Version corrigée et validée)

CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom_utilisateur TEXT NOT NULL UNIQUE,
    mot_de_passe TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'utilisateur',
    email TEXT
);

CREATE TABLE IF NOT EXISTS armoires (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS objets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL,
    quantite INTEGER NOT NULL,
    seuil INTEGER NOT NULL,
    armoire_id INTEGER NOT NULL,
    categorie_id INTEGER NOT NULL,
    image TEXT,
    en_commande INTEGER DEFAULT 0,
    date_peremption TEXT,
    traite INTEGER DEFAULT 0,
    fds_nom_original TEXT,
    fds_nom_securise TEXT,
    FOREIGN KEY (armoire_id) REFERENCES armoires (id) ON DELETE RESTRICT,
    FOREIGN KEY (categorie_id) REFERENCES categories (id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS historique (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    objet_id INTEGER NOT NULL,
    utilisateur_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (objet_id) REFERENCES objets (id) ON DELETE CASCADE,
    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS kit_objets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kit_id INTEGER NOT NULL,
    objet_id INTEGER NOT NULL,
    quantite INTEGER NOT NULL,
    FOREIGN KEY (kit_id) REFERENCES kits (id) ON DELETE CASCADE,
    FOREIGN KEY (objet_id) REFERENCES objets (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    objet_id INTEGER NOT NULL,
    quantite_reservee INTEGER NOT NULL,
    debut_reservation DATETIME NOT NULL,
    fin_reservation DATETIME NOT NULL,
    utilisateur_id INTEGER NOT NULL,
    groupe_id TEXT,
    kit_id INTEGER,
    FOREIGN KEY (objet_id) REFERENCES objets (id) ON DELETE CASCADE,
    FOREIGN KEY (utilisateur_id) REFERENCES utilisateurs (id) ON DELETE CASCADE,
    FOREIGN KEY (kit_id) REFERENCES kits (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS parametres (
    cle TEXT PRIMARY KEY,
    valeur TEXT
);

CREATE TABLE IF NOT EXISTS fournisseurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nom TEXT NOT NULL UNIQUE,
    site_web TEXT,
    logo TEXT
);

CREATE TABLE IF NOT EXISTS budgets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    annee INTEGER NOT NULL UNIQUE,
    montant_initial REAL NOT NULL,
    cloture BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS depenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_id INTEGER NOT NULL,
    fournisseur_id INTEGER,
    contenu TEXT NOT NULL,
    montant REAL NOT NULL,
    date_depense DATE NOT NULL,
    est_bon_achat INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (budget_id) REFERENCES budgets (id) ON DELETE CASCADE,
    FOREIGN KEY (fournisseur_id) REFERENCES fournisseurs (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS echeances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    intitule TEXT NOT NULL,
    date_echeance DATE NOT NULL,
    details TEXT,
    traite INTEGER NOT NULL DEFAULT 0
);

-- Initialisation des paramètres de base
INSERT OR IGNORE INTO parametres (cle, valeur) VALUES ('licence_statut', 'FREE');
INSERT OR IGNORE INTO parametres (cle, valeur) VALUES ('licence_cle', '');