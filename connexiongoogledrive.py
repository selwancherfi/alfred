import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Charger les infos d’identification depuis les secrets Streamlit
SERVICE_ACCOUNT_INFO = json.loads(os.getenv("GOOGLE_DRIVE_JSON"))
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1stVsLUW4HUDAU8O7GgAqHbASf0DlzQNI"

# Connexion à l’API Google Drive
credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)

def chercher_id_par_nom(nom_dossier, parent_id=FOLDER_ID):
    """Trouve l’ID d’un sous-dossier par nom (casse ignorée)."""
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
    """Liste les fichiers du dossier et sous-dossiers (avec indentation)."""
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
            contenu = lister_fichiers_dossier(None, f["id"], niveau + 1)
            lignes.append(contenu)
        else:
            lignes.append(f"{indent}📄 {f['name']}")
    return "\n".join(lignes) if lignes else "📂 Ce dossier est vide."

def creer_dossier(nom_dossier, parent_id=FOLDER_ID):
    """Crée un nouveau dossier s’il n’existe pas déjà dans le dossier parent."""
    if chercher_id_par_nom(nom_dossier, parent_id):
        return f"⚠️ Le dossier « {nom_dossier} » existe déjà."
    try:
        metadata = {
            "name": nom_dossier,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }
        service.files().create(body=metadata, fields="id").execute()
        return f"✅ Dossier « {nom_dossier} » créé avec succès."
    except Exception as e:
        return f"❌ Erreur lors de la création : {str(e)}"

def supprimer_element(nom, parent_id=FOLDER_ID):
    """Met dans la corbeille un fichier ou dossier portant ce nom (dans le parent donné)."""
    try:
        results = service.files().list(
            q=f"'{parent_id}' in parents and name='{nom}' and trashed=false",
            fields="files(id, name, mimeType)"
        ).execute()
        fichiers = results.get("files", [])
        if not fichiers:
            return f"❌ Aucun élément nommé « {nom} » n’a été trouvé dans ce dossier."

        file_id = fichiers[0]['id']
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
        return f"🗑️ L’élément « {nom} » a été déplacé dans la corbeille."
    except Exception as e:
        return f"❌ Erreur lors de la suppression : {str(e)}"
