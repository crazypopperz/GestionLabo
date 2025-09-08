import tkinter as tk
from tkinter import ttk
import hashlib
import pyperclip # Librairie pour copier dans le presse-papiers

# ATTENTION : Cette clé doit être EXACTEMENT la même que dans votre app.py
CLE_PRO_SECRETE = "LABO-PRO-2025-X@v14211825!S@cha14211825!Quentin14211825!"

def generer_et_afficher_cle():
    """Récupère l'ID, génère la clé et l'affiche dans le champ de sortie."""
    instance_id = entry_id.get().strip()
    if not instance_id:
        entry_cle.delete(0, tk.END)
        entry_cle.insert(0, "Veuillez entrer un ID d'instance.")
        return

    # Le même calcul que dans app.py
    chaine_a_hasher = f"{instance_id}-{CLE_PRO_SECRETE}"
    hash_complet = hashlib.sha256(chaine_a_hasher.encode('utf-8')).hexdigest()
    cle_licence = hash_complet[:16]

    # Afficher la clé générée
    entry_cle.delete(0, tk.END)
    entry_cle.insert(0, cle_licence)
    print(f"Clé générée pour {instance_id}: {cle_licence}")

def copier_cle():
    """Copie la clé générée dans le presse-papiers."""
    cle = entry_cle.get()
    if cle and "Veuillez" not in cle:
        pyperclip.copy(cle)
        # Petit feedback visuel
        btn_copier.config(text="Copié !")
        root.after(1500, lambda: btn_copier.config(text="Copier la clé"))

# --- Création de l'interface graphique ---
root = tk.Tk()
root.title("Générateur de Clé de Licence Pro")
root.geometry("500x200")
root.resizable(False, False)

# Style
style = ttk.Style()
style.configure("TLabel", font=("Arial", 10))
style.configure("TButton", font=("Arial", 10))
style.configure("TEntry", font=("Arial", 10))

# Frame principale
main_frame = ttk.Frame(root, padding="20")
main_frame.pack(fill="both", expand=True)

# Champ d'entrée pour l'ID d'instance
lbl_id = ttk.Label(main_frame, text="Identifiant d'Instance du Client :")
lbl_id.pack(pady=(0, 5), anchor="w")
entry_id = ttk.Entry(main_frame, width=60)
entry_id.pack(fill="x")

# Bouton de génération
btn_generer = ttk.Button(main_frame, text="Générer la Clé", command=generer_et_afficher_cle)
btn_generer.pack(pady=10)

# Champ de sortie pour la clé générée
lbl_cle = ttk.Label(main_frame, text="Clé de Licence à fournir :")
lbl_cle.pack(pady=(10, 5), anchor="w")
entry_cle = ttk.Entry(main_frame, width=60, state="readonly")
entry_cle.pack(fill="x", side="left", expand=True)

# Bouton pour copier
btn_copier = ttk.Button(main_frame, text="Copier", command=copier_cle)
btn_copier.pack(fill="x", side="right", padx=(5, 0))


# Lancer l'application
root.mainloop()