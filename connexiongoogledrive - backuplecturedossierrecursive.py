from google.oauth2 import service_account
from googleapiclient.discovery import build
import os

# Charger les infos d’identification
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1stVsLUW4HUDAU8O7GgAqHbASf0DlzQNI"

# Connexion à l’API
credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)

def chercher_id_par_nom(nom_dossier, parent_id=FOLDER_ID):
    """Trouve l’ID du sous-dossier dont le nom correspond (peu importe la casse)."""
    nom_dossier = nom_dossier.lower()
    results = service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    dossiers = results.get("files", [])
    for d in dossiers:
        if d["name"].lower() == nom_dossier:
            return d["id"]
    return None

def lister_fichiers_dossier(nom_dossier=None, parent_id=FOLDER_ID, niveau=0):
    """Liste les fichiers du dossier (et sous-dossiers) avec indentation."""
    if nom_dossier:
        id_cible = chercher_id_par_nom(nom_dossier, parent_id)
        if not id_cible:
            return f"❌ Le sous-dossier « {nom_dossier} » est introuvable."
        parent_id = id_cible

    results = service.files().list(
        q=f"'{parent_id}' in parents and trashed=false",
        fields="files(id, name, mimeType)"
    ).execute()

    fichiers = results.get("files", [])
    lignes = []
    for f in fichiers:
        indent = "    " * niveau
        if f["mimeType"] == "application/vnd.google-apps.folder":
            lignes.append(f"{indent}📁 {f['name']}")
            contenu_sous_dossier = lister_fichiers_dossier(None, f["id"], niveau + 1)
            lignes.append(contenu_sous_dossier)
        else:
            lignes.append(f"{indent}📄 {f['name']}")

    return "\n".join(lignes) if lignes else "📂 Ce dossier est vide."
