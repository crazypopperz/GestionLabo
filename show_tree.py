import os

# --- Configuration ---
# Répertoire de départ ('.' signifie le répertoire où se trouve le script)
START_PATH = '.'

# Éléments à ignorer (noms de dossiers et de fichiers)
# Vous pouvez personnaliser cette liste si nécessaire
IGNORE_LIST = [
    '__pycache__',
    '.git',
    '.vscode',
    'venv',
    '.venv',
    'node_modules',
    'show_tree.py',  # Pour ignorer le script lui-même
    '.gitignore',
    'schema_base.db' # On ignore la base de données
]
# --- Fin de la configuration ---

def generate_tree(startpath):
    """
    Génère une arborescence de fichiers et de dossiers.
    """
    print(f"Arborescence du projet : {os.path.abspath(startpath)}\n")
    
    for root, dirs, files in os.walk(startpath, topdown=True):
        # Modifie la liste des répertoires 'in-place' pour que os.walk les ignore
        dirs[:] = [d for d in dirs if d not in IGNORE_LIST]
        files = [f for f in files if f not in IGNORE_LIST]

        # Ne pas afficher les répertoires racines qui sont dans la liste d'ignorés
        if os.path.basename(root) in IGNORE_LIST:
            continue

        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * (level)
        
        # Affiche le nom du répertoire courant
        # On ajoute un '/' pour bien le différencier d'un fichier
        print(f'{indent}{os.path.basename(root)}/')

        sub_indent = ' ' * 4 * (level + 1)
        for f in sorted(files):
            print(f'{sub_indent}{f}')


if __name__ == '__main__':
    generate_tree(START_PATH)