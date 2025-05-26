import os
import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Charger les variables d’environnement (.env)
load_dotenv()
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
DOSSIER_ALFRED_ID = "1stVsLUW4HUDAU8O7GgAqHbASf0DlzQNI"

# Créer le client Google Drive
def creer_client_drive():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=credentials)

# Lister les fichiers dans le dossier partagé
def lister_fichiers_dossier():
    drive_service = creer_client_drive()
    results = drive_service.files().list(
        q=f"'{DOSSIER_ALFRED_ID}' in parents and trashed = false",
        fields="files(id, name, mimeType)"
    ).execute()

    fichiers = results.get("files", [])
    if not fichiers:
        return "📂 Aucun fichier trouvé dans le dossier partagé."
    
    liste = "📄 Fichiers trouvés :\n"
    for f in fichiers:
        liste += f"- {f['name']} ({f['mimeType']})\n"
    return liste
