"""
connexiongmail.py — OAuth Gmail + envoi d'e-mails pour Alfred

Fonctions principales :
- get_gmail_service() : retourne un client Gmail authentifié (créé/rafraîchi au besoin)
- list_send_as()      : liste les identités "Envoyer des e-mails en tant que" disponibles
- send_email(...)     : envoie un e-mail (HTML), avec from_address dynamique, reply-to, cc/bcc, PJ

Prérequis (pip) :
    pip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib

Fichiers attendus :
- credentials.json (ton fichier OAuth téléchargé) — chemin via env GMAIL_CREDENTIALS_FILE
- token.json (sera créé automatiquement au premier login) — chemin via env GMAIL_TOKEN_FILE

Variables d'environnement (avec valeurs par défaut raisonnables) :
- GMAIL_CREDENTIALS_FILE : chemin du credentials.json
- GMAIL_TOKEN_FILE       : chemin du token.json (sera créé)
- GMAIL_SCOPES           : scopes OAuth, séparés par des espaces
- GMAIL_DEFAULT_FROM     : expéditeur par défaut (ex : "alfred@selwancirque.com")

Exemples d'utilisation en bas (if __name__ == "__main__":).
"""

from __future__ import annotations

import os
import sys
import base64
import mimetypes
from pathlib import Path
from typing import Iterable, List, Optional, Dict

from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


# -------------------------
# Config & constantes
# -------------------------

DEFAULT_CREDENTIALS = r"C:\Users\User\Documents\automatisationavecchatgpt\Clefs API et clefs JSON\gmail\gmailsecrets.json"
DEFAULT_TOKEN       = r"C:\Users\User\Documents\automatisationavecchatgpt\Clefs API et clefs JSON\gmail\token.json"

DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",  # utile si tu veux lire les réponses plus tard
    # "https://www.googleapis.com/auth/gmail.modify",  # décommente si tu veux taguer/archiver ensuite
]

def _env(key: str, fallback: Optional[str] = None) -> Optional[str]:
    v = os.getenv(key)
    return v if (v and v.strip()) else fallback

GMAIL_CREDENTIALS_FILE = _env("GMAIL_CREDENTIALS_FILE", DEFAULT_CREDENTIALS)
GMAIL_TOKEN_FILE       = _env("GMAIL_TOKEN_FILE",       DEFAULT_TOKEN)
GMAIL_DEFAULT_FROM     = _env("GMAIL_DEFAULT_FROM",     "alfred@selwancirque.com")

_scopes_env = _env("GMAIL_SCOPES")
if _scopes_env:
    SCOPES = _scopes_env.split()
else:
    SCOPES = DEFAULT_SCOPES


# -------------------------
# Auth / Service
# -------------------------

def get_gmail_service():
    """
    Retourne un client Gmail authentifié.
    - Utilise GMAIL_CREDENTIALS_FILE & GMAIL_TOKEN_FILE
    - Ouvre le flux OAuth dans le navigateur au premier run, puis rafraîchit automatiquement.
    """
    cred_path = Path(GMAIL_CREDENTIALS_FILE)
    tok_path  = Path(GMAIL_TOKEN_FILE)

    if not cred_path.exists():
        raise FileNotFoundError(
            f"credentials.json introuvable : {cred_path}\n"
            f"Place ton fichier OAuth ici ou définis GMAIL_CREDENTIALS_FILE."
        )

    creds: Optional[Credentials] = None
    if tok_path.exists():
        creds = Credentials.from_authorized_user_file(str(tok_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            # rafraîchit automatiquement
            creds.refresh(Request())
        else:
            # premier run : lance le flow OAuth (navigateur)
            flow = InstalledAppFlow.from_client_secrets_file(str(cred_path), SCOPES)
            creds = flow.run_local_server(port=0)  # ouvre http://localhost:xxxx pour capter le code

        # persiste le token
        tok_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tok_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    service = build("gmail", "v1", credentials=creds)
    return service


# -------------------------
# Utilitaires
# -------------------------

def list_send_as(service) -> List[str]:
    """
    Retourne les adresses "Envoyer en tant que" autorisées sur ce compte.
    (Nécessaire si tu veux vérifier que 'alfred@...' est bien utilisable.)
    """
    resp = service.users().settings().sendAs().list(userId="me").execute()
    addrs = [entry.get("sendAsEmail") for entry in resp.get("sendAs", [])]
    return [a for a in addrs if a]


def _assert_from_allowed(service, from_address: str):
    allowed = list_send_as(service)
    if from_address not in allowed:
        raise ValueError(
            f"L'adresse From '{from_address}' n'est pas autorisée sur ce compte.\n"
            f"Autorisé(e)s : {allowed}\n"
            f"Vérifie Gmail > Paramètres > Comptes et importation > Envoyer des e-mails en tant que."
        )


def _guess_mime_type(path: Path) -> str:
    mtype, _ = mimetypes.guess_type(str(path))
    return mtype or "application/octet-stream"


# -------------------------
# Envoi d'e-mail
# -------------------------

def send_email(
    service,
    to: str | Iterable[str],
    subject: str,
    html_body: str,
    from_address: Optional[str] = None,
    reply_to: Optional[str] = None,
    cc: Optional[Iterable[str]] = None,
    bcc: Optional[Iterable[str]] = None,
    attachments: Optional[Iterable[str]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict:
    """
    Envoie un e-mail via l'API Gmail.

    - from_address : l'expéditeur voulu (doit être dans "Envoyer des e-mails en tant que").
                     par défaut = GMAIL_DEFAULT_FROM
    - reply_to     : si défini, force l'adresse de réponse
    - attachments  : liste de chemins de fichiers à joindre
    - headers      : dict d'en-têtes additionnels (ex : {"List-ID": "..."} )

    Retourne la réponse de l'API Gmail (dict).
    """
    from_address = from_address or GMAIL_DEFAULT_FROM

    # Vérifie que l'adresse "From" est bien autorisée
    _assert_from_allowed(service, from_address)

    # Normalise destinataires
    if isinstance(to, str):
        to_list = [to]
    else:
        to_list = list(to)

    cc_list  = list(cc) if cc else []
    bcc_list = list(bcc) if bcc else []

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = from_address
    msg["To"]      = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to

    # Corps HTML (et texte brut minimal fallback)
    msg.set_content("Version texte : ouvrez ce message en HTML pour une meilleure mise en forme.")
    msg.add_alternative(html_body, subtype="html")

    # Pièces jointes
    if attachments:
        for p in attachments:
            pth = Path(p)
            if not pth.exists():
                raise FileNotFoundError(f"Pièce jointe introuvable : {pth}")
            mtype = _guess_mime_type(pth)
            maintype, _, subtype = mtype.partition("/")
            with open(pth, "rb") as f:
                data = f.read()
            msg.add_attachment(data, maintype=maintype, subtype=subtype or "octet-stream", filename=pth.name)

    # En-têtes additionnels
    if headers:
        for k, v in headers.items():
            msg[k] = v

    # Encodage base64url
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    sent = service.users().messages().send(
        userId="me",
        body={"raw": raw}
    ).execute()

    return sent


# -------------------------
# CLI / Test rapide
# -------------------------

def _demo():
    """
    Test simple :
      - Auth si besoin (ouvre le navigateur)
      - Affiche les adresses 'Envoyer en tant que'
      - Envoie un message de test à toi-même
    """
    print("Initialisation du service Gmail…")
    service = get_gmail_service()

    allowed = list_send_as(service)
    print("Adresses 'Envoyer en tant que' autorisées :", allowed)

    # Choisis ici l'expéditeur voulu
    from_addr = os.getenv("DEMO_FROM", GMAIL_DEFAULT_FROM)

    # Destinataire de test (toi-même)
    to_addr = os.getenv("DEMO_TO", "selwancirque@selwancirque.com")

    html = """
    <div style="font-family:Inter,Arial,sans-serif;font-size:15px">
      <p>Bonjour Selwan,</p>
      <p>Ceci est un <b>test d'envoi via l'API Gmail</b> depuis Alfred.</p>
      <p>Expéditeur sélectionné : <code>{from_addr}</code></p>
      <p>Si tu vois ce message, la connexion OAuth et l'envoi fonctionnent ✅</p>
      <hr>
      <small>Alfred • Test Gmail API</small>
    </div>
    """.format(from_addr=from_addr)

    print(f"Envoi d'un test à {to_addr} depuis {from_addr}…")
    resp = send_email(
        service=service,
        to=to_addr,
        subject="Alfred • Test Gmail API",
        html_body=html,
        from_address=from_addr,
        reply_to="selwan@selwancirque.com",  # met ce que tu veux
    )
    print("OK, message envoyé. ID :", resp.get("id"))

if __name__ == "__main__":
    try:
        _demo()
    except Exception as e:
        print("\n❌ Erreur :", e, file=sys.stderr)
        sys.exit(1)