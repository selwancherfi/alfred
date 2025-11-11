# connexiongmail.py — Auth Gmail unifiée (local & cloud) + envoi d'e-mails pour Alfred

import os
import sys
import json
import base64
import logging
import mimetypes
from datetime import datetime
from typing import List, Optional, Dict

from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# -------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

# -------------------------------------------------------------------
# SCOPES — IMPORTANT : sendAs.list nécessite gmail.settings.basic
# -------------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.settings.basic",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# -------------------------------------------------------------------
# Defaults (fallback local dev uniquement)
# -------------------------------------------------------------------
DEFAULT_CREDENTIALS_FILE = os.environ.get(
    "GMAIL_CREDENTIALS_FILE",
    r"C:\Users\User\Documents\projetAlfred\Clefs API et clefs JSON\gmail\gmailsecrets.json",
)
DEFAULT_TOKEN_FILE = os.environ.get(
    "GMAIL_TOKEN_FILE",
    r"C:\Users\User\Documents\projetAlfred\Clefs API et clefs JSON\gmail\token.json",
)

# -------------------------------------------------------------------
# Helpers de lecture des secrets (streamlit OU env), JSON ou Base64
# -------------------------------------------------------------------
def _get_secret_text(key: str) -> Optional[str]:
    """Récupère un secret depuis streamlit.secrets (si dispo) ou depuis os.environ."""
    try:
        import streamlit as st  # type: ignore
        if key in st.secrets:
            val = st.secrets[key]
            if isinstance(val, (dict, list)):
                return json.dumps(val)
            return str(val)
    except Exception:
        pass
    return os.environ.get(key)

def _load_json_secret(key_json: str, key_b64: Optional[str] = None) -> Optional[dict]:
    """
    Charge un JSON depuis :
      - KEY_JSON (texte JSON brut ou triple-quoted)
      - sinon KEY_B64 (contenu Base64 d'un JSON)
    """
    raw = _get_secret_text(key_json)
    if raw:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                cleaned = raw.replace("\n", "").replace("\r", "").strip()
                return json.loads(cleaned)
            except Exception:
                logger.error("Secret %s présent mais illisible en JSON.", key_json)
                return None

    if key_b64:
        b64 = _get_secret_text(key_b64)
        if b64:
            try:
                decoded = base64.b64decode(b64).decode("utf-8")
                return json.loads(decoded)
            except Exception:
                logger.error("Secret %s présent mais Base64/JSON invalide.", key_b64)
                return None
    return None

def _build_creds_from_authorized_info(authorized_info: dict, scopes: List[str]) -> Credentials:
    """
    Construit des Credentials à partir d'un authorized_user_info (token.json complet).
    Exige refresh_token, client_id, client_secret, token_uri.
    """
    # Utilisation positionnelle pour éviter l'erreur d'argument nommé.
    creds = Credentials.from_authorized_user_info(authorized_info, scopes)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
    return creds

def _headless_mode_detected() -> bool:
    """
    Headless si :
      - STREAMLIT_RUNTIME présent OU
      - secrets JSON présents OU
      - FORBID_OAUTH_INTERACTIVE=1
    """
    if os.environ.get("STREAMLIT_RUNTIME"):
        return True
    if _get_secret_text("GMAIL_CREDENTIALS_JSON") or _get_secret_text("GMAIL_CREDENTIALS_B64"):
        return True
    if _get_secret_text("GMAIL_TOKEN_JSON") or _get_secret_text("GMAIL_TOKEN_B64"):
        return True
    if os.environ.get("FORBID_OAUTH_INTERACTIVE") == "1":
        return True
    return False

# -------------------------------------------------------------------
# Auth principale : secrets -> fichiers -> (optionnel) OAuth interactif en local
# -------------------------------------------------------------------
def get_gmail_service() -> "googleapiclient.discovery.Resource":
    """
    Retourne un client Gmail authentifié. Priorité aux secrets JSON.
    - Prod/cloud : JAMAIS d'OAuth interactif ni d'écriture disque.
    - Local : fallback fichiers + OAuth interactif possible pour régénérer un token.
    """
    headless = _headless_mode_detected()

    # 1) Secrets JSON (prod / simulation prod)
    creds_json = _load_json_secret("GMAIL_CREDENTIALS_JSON", "GMAIL_CREDENTIALS_B64")
    token_json = _load_json_secret("GMAIL_TOKEN_JSON", "GMAIL_TOKEN_B64")

    if creds_json and token_json:
        logger.info("Auth Gmail : utilisation des secrets JSON (headless=%s).", headless)
        creds = _build_creds_from_authorized_info(token_json, SCOPES)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # 2) Fichiers (local dev)
    if os.path.exists(DEFAULT_TOKEN_FILE):
        try:
            with open(DEFAULT_TOKEN_FILE, "r", encoding="utf-8") as f:
                token_info = json.load(f)
            creds = _build_creds_from_authorized_info(token_info, SCOPES)
            logger.info("Auth Gmail : token fichier local.")
            return build("gmail", "v1", credentials=creds, cache_discovery=False)
        except Exception as e:
            logger.warning("Token local illisible/expiré : %s", e)

    if os.path.exists(DEFAULT_CREDENTIALS_FILE):
        if headless:
            raise RuntimeError(
                "Auth Gmail : credentials présents mais environnement headless.\n"
                "Fournis GMAIL_CREDENTIALS_JSON et GMAIL_TOKEN_JSON dans les secrets,"
                " ou exécute la réauth en local puis colle le token dans les secrets."
            )
        # OAuth interactif (LOCAL UNIQUEMENT)
        logger.info("Auth Gmail : OAuth interactif local (run_local_server).")
        flow = InstalledAppFlow.from_client_secrets_file(DEFAULT_CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
        # Persistance locale du token pour les prochains lancements
        try:
            with open(DEFAULT_TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
            logger.info("Token local sauvegardé : %s", DEFAULT_TOKEN_FILE)
        except Exception as e:
            logger.warning("Impossible d'écrire le token local : %s", e)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    # 3) Rien de disponible
    raise RuntimeError(
        "Auth Gmail : aucun secret JSON ni fichier disponible.\n"
        "→ Ajoute GMAIL_CREDENTIALS_JSON et GMAIL_TOKEN_JSON aux secrets (prod),\n"
        "  ou fournis GMAIL_CREDENTIALS_FILE / GMAIL_TOKEN_FILE en local."
    )

# -------------------------------------------------------------------
# Utilitaires
# -------------------------------------------------------------------
def who_am_i(service) -> str:
    """Retourne l'adresse principale du compte authentifié."""
    profile = service.users().getProfile(userId="me").execute()
    return profile.get("emailAddress")

def list_send_as(service) -> List[str]:
    """
    Retourne la liste des adresses utilisables (strings).
    Requiert le scope gmail.settings.basic.
    """
    try:
        resp = service.users().settings().sendAs().list(userId="me").execute()
        return [s.get("sendAsEmail") for s in resp.get("sendAs", []) if s.get("sendAsEmail")]
    except HttpError as e:
        if e.resp.status == 403:
            raise PermissionError(
                "Permissions insuffisantes pour lister les alias (sendAs). "
                "Ajoute le scope 'gmail.settings.basic' au token et régénère-le."
            ) from e
        raise

def _build_mime_message(
    to: str,
    subject: str,
    html_body: str,
    from_address: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    attachments: Optional[List[Dict]] = None,
) -> EmailMessage:
    """
    Construit un EmailMessage (HTML + PJ).
    attachments : [{"path": "...", "filename": "..."}] ou {"bytes": b"...", "filename": "...", "mimetype": "..."}
    """
    msg = EmailMessage()
    if from_address:
        msg["From"] = from_address
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    if reply_to:
        msg["Reply-To"] = reply_to

    # Corps HTML
    msg.set_content("Version texte non fournie.")
    msg.add_alternative(html_body or "", subtype="html")

    # Pièces jointes
    if attachments:
        for att in attachments:
            if "bytes" in att:
                data = att["bytes"]
                filename = att.get("filename", "attachment")
                maintype, subtype = ("application", "octet-stream")
                if att.get("mimetype"):
                    maintype, subtype = att["mimetype"].split("/", 1)
                msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
            elif "path" in att:
                path = att["path"]
                filename = att.get("filename") or os.path.basename(path)
                ctype, _ = mimetypes.guess_type(filename)
                if ctype is None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)
                with open(path, "rb") as f:
                    msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=filename)
            else:
                raise ValueError("Attachment invalide : fournir 'bytes' ou 'path'.")

    return msg

def send_email(
    service,
    to: str,
    subject: str,
    html_body: str,
    from_address: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    attachments: Optional[List[Dict]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict:
    """
    Envoie un e-mail via Gmail API.
    - Vérifie que 'from_address' est autorisé si fourni.
    - Ajoute des headers personnalisés si fournis.
    """
    if from_address:
        allowed = list_send_as(service)
        if from_address not in allowed:
            raise ValueError(
                f"L'adresse d'expédition '{from_address}' n'est pas autorisée sur ce compte. "
                f"Aliases disponibles : {allowed}"
            )

    # Construction du message
    msg = _build_mime_message(
        to=to,
        subject=subject,
        html_body=html_body,
        from_address=from_address,
        reply_to=reply_to,
        cc=cc,
        bcc=bcc,
        attachments=attachments,
    )

    # Ajout éventuel des headers personnalisés
    if headers:
        for key, value in headers.items():
            msg[key] = value

    import base64 as _b64
    raw = _b64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    try:
        sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return sent
    except HttpError as e:
        if e.resp.status == 403:
            raise PermissionError(
                "Envoi refusé (403). Vérifie les scopes du token et/ou l'alias 'From:'."
            ) from e
        raise


# -------------------------------------------------------------------
# Utilitaire CLI : régénérer un token local avec les SCOPES ci-dessus
# -------------------------------------------------------------------
def _reauth_local() -> None:
    """
    Ouvre un navigateur EN LOCAL pour consentir aux SCOPES et
    écrit le token.json sur disque + affiche son contenu JSON (à copier dans les secrets).
    """
    if not os.path.exists(DEFAULT_CREDENTIALS_FILE):
        raise FileNotFoundError(
            f"credentials/client OAuth introuvable : {DEFAULT_CREDENTIALS_FILE}\n"
            "→ Télécharge le fichier client (type 'Desktop') et mets-le à cet emplacement "
            "ou passe GMAIL_CREDENTIALS_FILE dans l'environnement."
        )
    flow = InstalledAppFlow.from_client_secrets_file(DEFAULT_CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    try:
        with open(DEFAULT_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        logger.info("Nouveau token écrit : %s", DEFAULT_TOKEN_FILE)
    except Exception as e:
        logger.warning("Impossible d'écrire le token local : %s", e)
    print("\n=== TOKEN.JSON À COLLER DANS GMAIL_TOKEN_JSON (secrets) ===\n")
    print(creds.to_json())
    print("\n===========================================================\n")

# -------------------------------------------------------------------
# Demo / CLI
# -------------------------------------------------------------------
def _demo():
    svc = get_gmail_service()
    me = who_am_i(svc)
    logger.info("Connecté en tant que : %s", me)

    try:
        send_as = list_send_as(svc)
        logger.info("Aliases disponibles : %s", send_as)
    except PermissionError as e:
        logger.warning(str(e))

    if os.environ.get("GMAIL_SEND_TEST") == "1":
        default_from = _get_secret_text("GMAIL_DEFAULT_FROM")
        to_addr = os.environ.get("GMAIL_TEST_TO", me)
        html = f"<p>Test Alfred • {datetime.now().isoformat()}</p>"
        resp = send_email(
            service=svc,
            to=to_addr,
            subject="Alfred • Test Gmail API",
            html_body=html,
            from_address=default_from,
            reply_to=None,
        )
        logger.info("Message envoyé. ID : %s", resp.get("id"))

if __name__ == "__main__":
    if "--reauth" in sys.argv:
        _reauth_local()
        sys.exit(0)
    _demo()
