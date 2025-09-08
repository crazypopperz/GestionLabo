# Gestion Matériel Labo Collège et Lycée (GMLCL)

**Version 1.0**

![Logo de l'application](static/logo.png)

## Description

GMLCL est une application web de gestion d'inventaire conçue spécifiquement pour les laboratoires de sciences dans les collèges et lycées. Elle permet aux enseignants et techniciens de laboratoire de suivre le stock de matériel, de gérer les réservations pour les travaux pratiques, de suivre un budget et de recevoir des alertes automatiques.

L'application est construite avec le framework Python Flask et utilise une base de données SQLite, ce qui la rend entièrement autonome, multiplateforme et facile à déployer.

### Modèle Freemium
- **Version Gratuite :** Accès à toutes les fonctionnalités, mais l'inventaire est limité à 50 objets uniques.
- **Version Pro :** Débloque un nombre illimité d'objets et la fonctionnalité de sauvegarde de la base de données.

## Table des Matières
1. [Fonctionnalités Principales](#fonctionnalités-principales)
2. [Technologies Utilisées](#technologies-utilisées)
3. [Installation (pour les développeurs)](#installation-pour-les-développeurs)
4. [Lancement de l'application](#lancement-de-lapplication)
5. [Création de l'Exécutable (Packaging)](#création-de-lexécutable-packaging)
6. [Structure du Projet](#structure-du-projet)
7. [Auteurs et Licence](#auteurs-et-licence)

## Fonctionnalités Principales

- **Gestion d'Inventaire :** Suivi des objets par armoires et catégories, avec gestion des quantités et seuils d'alerte.
- **Système de Réservation :** Calendrier interactif pour réserver du matériel pour des séances de TP.
- **Gestion de Kits :** Création de listes de matériel prédéfinies pour des réservations rapides.
- **Alertes Automatiques :** Notifications pour les stocks bas et les produits arrivant à péremption.
- **Suivi Budgétaire :** Gestion simple des budgets annuels et des dépenses associées.
- **Export de Données :** Génération de rapports d'inventaire et d'activité aux formats PDF et Excel.
- **Gestion Multi-utilisateurs :** Distinction entre les rôles administrateur et utilisateur standard.
- **Système de Licence Sécurisé :** Activation de la version Pro via une clé unique liée à l'installation.

## Technologies Utilisées

- **Backend :** Python 3, Flask
- **Base de Données :** SQLite 3
- **Frontend :** HTML5, CSS3, JavaScript (sans framework)
- **Bibliothèques Python Clés :** Flask-WTF (pour la sécurité CSRF), FPDF, OpenPyXL
- **Packaging :** PyInstaller

## Installation (pour les développeurs)

Ce guide est destiné à la mise en place d'un environnement de développement. Pour une utilisation finale, veuillez utiliser l'exécutable fourni (`GestionLabo.exe` ou `GestionLabo.app`).

1. **Cloner le projet :**
```bash
# Remplacez [URL_DU_DEPOT_GIT] par l'URL de votre dépôt si vous en utilisez un.
git clone [URL_DU_DEPOT_GIT]
cd gestion-labo
```

2. **Créer un environnement virtuel (recommandé) :**
```bash
python -m venv venv
```

3. **Activer l'environnement virtuel :**
```bash
# Sur Windows
venv\Scripts\activate

# Sur macOS/Linux
source venv/bin/activate
```

4. **Installer les dépendances :**
Un fichier `requirements.txt` est fourni pour installer toutes les bibliothèques nécessaires.
```bash
pip install -r requirements.txt
```

## Lancement de l'application

### En Mode Développement
Une fois les dépendances installées, lancez l'application avec la commande suivante. L'application sera alors accessible dans votre navigateur à l'adresse `http://127.0.0.1:5000`.
```bash
python app.py
```

### En Mode Production (via l'exécutable)
Double-cliquez sur le fichier `GestionLabo.exe` (Windows) ou `GestionLabo.app` (macOS) généré. L'application se lancera en arrière-plan et ouvrira automatiquement votre navigateur web à la bonne adresse.

## Création de l'Exécutable (Packaging)

Pour distribuer l'application, vous devez la packager en un seul fichier exécutable.

1. **Installer PyInstaller :**
```bash
pip install pyinstaller
```

2. **Lancer la commande de compilation :**
Exécutez la commande suivante depuis la racine du projet. Elle inclut les dossiers `templates`, `static` et le fichier `base.db`.
```bash
pyinstaller --onefile --windowed --add-data "templates;templates" --add-data "static;static" --add-data "base.db;." --name "GestionLabo" app.py
```
*(Note : sur macOS/Linux, remplacez le point-virgule `;` par un deux-points `:`)*

3. L'exécutable final se trouvera dans le dossier `dist/`.

## Structure du Projet

```
.
├── static/ # Fichiers CSS, JavaScript, images, etc.
│ ├── css/
│ ├── js/
│ └── ...
├── templates/ # Fichiers HTML (templates Jinja2)
├── app.py # Fichier principal de l'application Flask
├── base.db # Base de données SQLite (vierge pour la distribution)
├── keygen_ui.py # Outil de génération de clés de licence (pour le développeur)
├── requirements.txt # Liste des dépendances Python
└── README.md # Ce fichier
```

## Auteurs et Licence

- **Auteurs :** Yll Basha & Xavier De Baudry d'Asson
- **Licence :** Ce projet est distribué sous la licence [Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International (CC BY-NC-ND 4.0)](https://creativecommons.org/licenses/by-nc-nd/4.0/).