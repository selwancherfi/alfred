import os
import io
import json
from typing import List, Dict, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from lecturefichiersbase import (
    lire_txt_bytes, lire_pdf_bytes, lire_docx_bytes, lire_csv_bytes, PDF_MAX_PAGES_DEFAULT
)

SERVICE_ACCOUNT_INFO = json.loads(os.getenv("GOOGLE_DRIVE_JSON"))
SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER_ID = "1stVsLUW4HUDAU8O7GgAqHbASf0DlzQNI"

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
DEFAULT_PDF_MAX_PAGES = PDF_MAX_PAGES_DEFAULT

credentials = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO, scopes=SCOPES
)
service = build("drive", "v3", credentials=credentials)

def chercher_id_par_nom(nom_dossier, parent_id=FOLDER_ID):
    nom_dossier = (nom_dossier or "").lower()
    results = service.files().list(
        q=f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    dossiers = results.get("files", [])
    for d in dossiers:
        if (d.get("name", "").lower() == nom_dossier):
            return d["id"]
    return None

def _iter_dossier_recursif(parent_id: str):
    try:
        res = service.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            fields="files(id,name,mimeType,size)"
        ).execute()
    except HttpError:
        res = {"files": []}
    for f in res.get("files", []):
        yield f
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            yield from _iter_dossier_recursif(f.get("id"))

def trouver_id_dossier_recursif(nom_dossier: str, parent_id: str = FOLDER_ID) -> Optional[str]:
    nom = (nom_dossier or "").strip().lower()
    if not nom:
        return parent_id
    # recherche par nom exact (casse insensible) dans tout l'arbre
    for f in _iter_dossier_recursif(parent_id):
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            if (f.get("name","").strip().lower() == nom):
                return f.get("id")
    return None

def lister_fichiers_dossier(nom_dossier=None, parent_id=FOLDER_ID, niveau=0):
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

def supprimer_element(nom, parent_id: Optional[str] = None):
    """Suppression (corbeille) par nom ; si parent_id None, on cherche récursivement dans tout l'arbre."""
    try:
        if parent_id:
            query = f"'{parent_id}' in parents and name='{nom}' and trashed=false"
            results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
            fichiers = results.get("files", [])
        else:
            # recherche récursive : on prend le premier match rencontré
            fichiers = []
            for f in _iter_dossier_recursif(FOLDER_ID):
                if f.get("name") == nom:
                    fichiers = [f]; break

        if not fichiers:
            return f"❌ Aucun élément nommé « {nom} » n’a été trouvé."
        file_id = fichiers[0]['id']
        service.files().update(fileId=file_id, body={"trashed": True}).execute()
        return f"🗑️ L’élément « {nom} » a été déplacé dans la corbeille."
    except Exception as e:
        return f"❌ Erreur lors de la suppression : {str(e)}"

MIME_GOOGLE_DOC = "application/vnd.google-apps.document"
MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
MIME_GOOGLE_SLIDES = "application/vnd.google-apps.presentation"

EXPORT_MIME = {
    MIME_GOOGLE_DOC: "text/plain",
    MIME_GOOGLE_SHEET: "text/csv",
    MIME_GOOGLE_SLIDES: "application/pdf"
}

def rechercher_fichiers(nom: Optional[str] = None, extension: Optional[str] = None, parent_id: str = FOLDER_ID) -> List[Dict[str, str]]:
    nom = (nom or "").strip().lower()
    ext = (extension or "").strip().lower().lstrip('.') or None
    matches: List[Dict[str, str]] = []
    for f in _iter_dossier_recursif(parent_id):
        mt = f.get("mimeType", "")
        if mt == "application/vnd.google-apps.folder":
            continue
        fname = f.get("name", "")
        if nom and (nom not in fname.lower()):
            continue
        if ext:
            if "." in fname:
                if not fname.lower().endswith("." + ext):
                    continue
        matches.append({
            "id": f.get("id"),
            "name": fname,
            "mimeType": mt,
            "size": f.get("size")
        })
    return matches

def telecharger_fichier(file_id: str, mimeType: Optional[str] = None) -> Tuple[bytes, str]:
    meta = service.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
    mt = meta.get("mimeType")

    if mt in EXPORT_MIME:
        export_mt = EXPORT_MIME[mt]
        data = service.files().export_media(fileId=file_id, mimeType=export_mt).execute()
        return (data, export_mt)

    data = service.files().get_media(fileId=file_id).execute()
    effective = mt or "application/octet-stream"
    return (data, effective)

def _check_size_allowed(meta: Dict[str, str]) -> Optional[str]:
    size_str = meta.get("size")
    if not size_str:
        return None
    try:
        sz = int(size_str)
        if sz > MAX_FILE_SIZE_BYTES:
            return f"⚠️ Fichier volumineux ({sz // (1024*1024)} Mo). Lecture bloquée (>10 Mo)."
    except Exception:
        pass
    return None

def lire_contenu_fichier(
    nom_fichier: Optional[str] = None,
    file_id: Optional[str] = None,
    extension: Optional[str] = None,
    parent_id: str = FOLDER_ID,
    pdf_max_pages: int = DEFAULT_PDF_MAX_PAGES
) -> str:
    try:
        if not file_id:
            candidats = rechercher_fichiers(nom=nom_fichier, extension=extension, parent_id=parent_id)
            if not candidats:
                return "❌ Fichier introuvable dans le dossier partagé. Précise le nom ou le sous-dossier."
            meta = candidats[0]
            note = f"[Plusieurs correspondances : je lis le premier match « {meta['name']} » parmi {len(candidats)}.]\n\n" if len(candidats) > 1 else ""
        else:
            meta = service.files().get(fileId=file_id, fields="id,name,mimeType,size").execute()
            note = ""

        err = _check_size_allowed(meta)
        if err:
            return err

        data, effective_mime = telecharger_fichier(meta["id"])

        mt = effective_mime
        out = ""
        if mt == "text/plain":
            out = lire_txt_bytes(data)
        elif mt == "application/pdf":
            out = lire_pdf_bytes(data, max_pages=pdf_max_pages)
        elif mt == "text/csv":
            out = lire_csv_bytes(data)
        elif mt in ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"):
            out = lire_docx_bytes(data)
        elif mt in ("application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
            import pandas as pd, io as _io
            df = pd.read_excel(_io.BytesIO(data))
            out = df.head(50).to_string(index=False)
            if len(df) >= 50:
                out += "\n\n---\n[Affichage partiel : premières 50 lignes]"
        else:
            out = "Format non pris en charge pour la lecture texte."

        out = (note + out).strip()
        return out if out else "(Fichier vide ou non lisible en texte)"
    except Exception as e:
        return f"❌ Erreur lors de la lecture : {e}"
