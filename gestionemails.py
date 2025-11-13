# gestionemails.py — brique "Email" (UI persistente + envoi via Gmail) — COMPATIBLE v2.4
from __future__ import annotations

import re
import io
import html
import mimetypes
import tempfile
import shutil
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

import unicodedata  # <-- ajouté pour la normalisation du texte

import streamlit as st
from googleapiclient.http import MediaIoBaseDownload

from memoire_alfred import answer_with_memories
from connexiongmail import get_gmail_service, list_send_as, send_email
from connexiongoogledrive import service as DRIVE_SERVICE  # client Drive global (peut être None)

# ========================= Intention =========================

TRIGGERS = [
    "envoie un mail","envois un mail","envoyer un mail","envoi un mail","envoi d'un mail",
    "envoie un email","envois un email","envoyer un email","envoi un email","envoi d'un email",
    "écris un mail","ecris un mail","écris un email","ecris un email",
    "écrire un mail","écrire un email","mail à","email à","/mail","/email"
]

# Nouvelle détection plus tolérante : accents, fautes légères, "envoie mail", etc.
_EMAIL_RE = re.compile(
    r"\b(envoi[sezr]?|envoy(?:er|e|ez|ons|es|e)|ecris|écris|ecrire|écrire)\b.*\b(mail|email|courriel|m[èe]l)\b",
    re.I,
)

def _norm_email_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s)
    return s

def is_email_intent(text: str) -> bool:
    low = _norm_email_text(text)
    # 1) Ancienne logique (compat TB)
    if any(t in low for t in TRIGGERS):
        return True
    # 2) Nouvelle logique plus large : "envoie/envois/envoyer/écris… + mail/email/mèl…"
    return bool(_EMAIL_RE.search(low))

# ========================= Helpers rendu / parsing =========================

def _extract_to_address(user_text: str, contacts: Dict[str, str]) -> Optional[str]:
    if not user_text:
        return None
    m = re.search(r"([a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-.]+\.[a-zA-Z]{2,})", user_text)
    if m:
        return m.group(1)
    low = user_text.lower()
    for k, v in contacts.items():
        if k.lower() in low:
            return v
    return None

def _plain_to_html(text: str) -> str:
    from html import escape
    if not text:
        return "<p></p>"
    lines = []
    for line in text.splitlines():
        lines.append(f"<p>{escape(line)}</p>" if line.strip() else "<br>")
    return "".join(lines)

def _llm_write_email(user_text: str, signature: str = "— Selwan") -> dict:
    prompt_sys = (
        "Tu es Alfred. Rédige un courriel clair et concis en HTML très simple."
        "\nFormat attendu:\nOBJET: <une ligne>\nHTML:\n<p>…</p>\n"
    )
    raw = answer_with_memories(f"{prompt_sys}\n\nINSTRUCTION:\n{user_text}\n", k=6)

    subj = "Message"
    html_out = f"<p>{user_text}</p>"

    m_subj = re.search(r"^OBJET:\s*(.+)$", raw, flags=re.MULTILINE)
    if m_subj:
        subj = m_subj.group(1).strip()
    m_html = re.search(r"HTML:\s*(.*)$", raw, flags=re.DOTALL | re.IGNORECASE)
    if m_html:
        html_out = m_html.group(1).strip()

    html_out = html_out.replace("&nbsp;", " ").replace("\u00A0", " ")
    if signature and signature not in html_out:
        html_out = html_out.rstrip() + f"\n<p>{signature}</p>"

    # version texte (fallback)
    text = re.sub(r"(?i)<br\s*/?>", "\n", html_out)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip()

    return {"subject": subj, "html": html_out, "text": text}

def _guess_mime(path_or_name: str) -> str:
    mime, _ = mimetypes.guess_type(path_or_name)
    return mime or "application/octet-stream"

# ========================= PJ : export Google & téléchargement =========================

GOOGLE_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "application/vnd.google-apps.document":
        ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet":
        ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation":
        ("application/vnd.openxmlformats-officedocument.presentationml.presentation", ".pptx"),
    "application/vnd.google-apps.drawing":
        ("application/pdf", ".pdf"),
    "DEFAULT_GOOGLE":
        ("application/pdf", ".pdf"),
}

def _drive_find_first_by_snippet(service, snippet: str) -> Optional[Dict[str, Any]]:
    safe = (snippet or "").replace("'", "\\'")
    q = f"name contains '{safe}' and trashed=false"
    res = service.files().list(
        q=q, spaces="drive",
        fields="files(id,name,mimeType,modifiedTime,size,parents)",
        pageSize=10
    ).execute()
    files = res.get("files", []) if isinstance(res, dict) else []
    return files[0] if files else None

def _drive_download_or_export(service, file_id: str, name: str, mime_type: str) -> Tuple[bytes, str, str]:
    if mime_type.startswith("application/vnd.google-apps."):
        exp_mime, ext = GOOGLE_EXPORT_MAP.get(
            mime_type, GOOGLE_EXPORT_MAP["DEFAULT_GOOGLE"]
        )
        request = service.files().export_media(fileId=file_id, mimeType=exp_mime)
        final_name = (Path(name).stem or "document") + ext
        final_mime = exp_mime
    else:
        request = service.files().get_media(fileId=file_id)
        final_name = name
        final_mime = mime_type or _guess_mime(name)
        if not Path(final_name).suffix:
            guessed = mimetypes.guess_extension(final_mime) or ".bin"
            final_name = final_name + guessed

    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    data = fh.getvalue()
    return data, final_mime, final_name

# ========================= Gestion des fichiers temporaires =========================

def _tmp_root() -> Path:
    # Répertoire temp système (portable : Windows/Mac/Linux/Streamlit Cloud)
    root = Path(tempfile.gettempdir()) / "alfred_tmp"
    root.mkdir(parents=True, exist_ok=True)
    return root

def _save_tmp(data: bytes, filename: str) -> Path:
    root = _tmp_root()
    safe = (filename or "piece_jointe.bin").replace("/", "_").replace("\\", "_")
    p = root / safe
    with open(p, "wb") as f:
        f.write(data)
    # garde la trace pour nettoyage post-envoi
    st.session_state.setdefault("email_tmp_created", set())
    st.session_state["email_tmp_created"].add(str(p))
    return p

def _cleanup_tmp_paths(paths: List[str]):
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass
    try:
        root = _tmp_root()
        if root.exists() and not any(root.iterdir()):
            shutil.rmtree(root, ignore_errors=True)
    except Exception:
        pass

def _resolve_drive_to_tmp(snippet: str) -> Tuple[Optional[Path], Optional[str]]:
    if DRIVE_SERVICE is None:
        return None, "Service Drive indisponible (vérifie les identifiants/permissions)."
    meta = _drive_find_first_by_snippet(DRIVE_SERVICE, snippet.strip())
    if not meta:
        return None, "Fichier introuvable dans le dossier partagé. Précise le nom ou le sous-dossier."
    try:
        data, _, name = _drive_download_or_export(
            DRIVE_SERVICE,
            meta["id"],
            meta.get("name", "fichier"),
            meta.get("mimeType", "application/octet-stream"),
        )
    except Exception as e:
        return None, f"Erreur Drive : {e}"
    tmp = _save_tmp(data, name)
    return tmp, None

# ========================= Vérification post-envoi =========================

def _verify_gmail_persisted(service, msg_id: str, expected_attachments: int, timeout_s: int = 6) -> dict:
    """Attend que Gmail ait persisté le message et renvoie meta + diagnostics."""
    t0 = time.time()
    last_meta: Dict[str, Any] = {}
    while time.time() - t0 < timeout_s:
        try:
            meta = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            last_meta = meta or {}
            labels = set(meta.get("labelIds", []))
            # Compte des pièces jointes vues par Gmail
            parts = (meta.get("payload") or {}).get("parts") or []
            att_count = sum(1 for p in parts if p.get("filename"))
            if "SENT" in labels and att_count >= expected_attachments:
                return {"ok": True, "meta": meta, "attachments_seen": att_count}
        except Exception:
            pass
        time.sleep(0.4)
    return {"ok": False, "meta": last_meta, "attachments_seen": None}

# ========================= Contexte / UI persistente =========================

def maybe_bootstrap_email(user_prompt: str) -> bool:
    if not is_email_intent(user_prompt):
        return False

    st.session_state.setdefault("email_ctx", None)
    st.session_state.setdefault("email_result", None)

    contacts = {
        "guillaume": "guillaume@exemple.com",
        "selwan": "selwan@selwancirque.com",
    }
    draft = _llm_write_email(user_prompt)
    from_candidates = _list_possible_from_safe()

    ctx = {
        "from_address": _prefer_alfred(from_candidates),
        "to_address": _extract_to_address(user_prompt, contacts),
        "subject": draft["subject"],
        "html": draft["html"],
        "text": draft["text"],
        "attachments": [],
    }
    st.session_state["email_ctx"] = ctx
    st.session_state["email_local_files"] = []
    st.session_state["email_drive_added"] = []
    return True

def _list_possible_from_safe() -> List[str]:
    try:
        svc = get_gmail_service()
        return list_send_as(svc)
    except Exception:
        return ["alfred@selwancirque.com"]

def _prefer_alfred(cands: List[str]) -> Optional[str]:
    for a in cands:
        if a and a.lower().startswith("alfred@"):
            return a
    return cands[0] if cands else None

def email_flow_persist(_push_history=None) -> bool:
    ctx = st.session_state.get("email_ctx")
    res = st.session_state.get("email_result")
    if ctx is None and res is None:
        return False

    with st.chat_message("assistant"):
        st.info("✉️ Préparation de l’envoi d’email")

        if res is not None:
            st.success("Message envoyé ✅")
            st.write(f"**De :** {ctx['from_address']}")
            st.write(f"**À :** {ctx['to_address']}")
            st.write(f"**Objet :** {ctx['subject']}")
            if ctx.get("attachments"):
                st.write("**Pièces jointes :**")
                for p in ctx["attachments"]:
                    st.write(f"• {Path(p).name}")

            # Lien Gmail générique (toujours dispo)
            st.link_button("Ouvrir Gmail (boîte d’envoi)", "https://mail.google.com/mail/u/0/#sent")

            # Diagnostics / lien direct si on récupère les métadonnées du message
            if isinstance(res, dict) and res.get("id"):
                try:
                    svc = get_gmail_service()
                    meta = svc.users().messages().get(userId="me", id=res["id"], format="metadata").execute()
                    thread_id = meta.get("threadId")
                    labels = ", ".join(meta.get("labelIds", []))
                    snippet = meta.get("snippet", "")
                    if thread_id:
                        url = f"https://mail.google.com/mail/u/0/#all/{thread_id}"
                        st.link_button("Ouvrir dans Gmail", url)
                    if labels:
                        st.caption(f"Labels Gmail : {labels}")
                    if snippet:
                        st.caption(f"Aperçu Gmail : {snippet}")
                except Exception as e:
                    st.caption(f"(Impossible de récupérer le lien Gmail : {e})")

            # Résultat de la vérification auto (si dispo)
            chk = st.session_state.get("email_result_check")
            if isinstance(chk, dict):
                if chk.get("ok"):
                    seen = chk.get("attachments_seen")
                    st.caption(f"Vérification : message présent dans SENT et {seen} PJ détectée(s) ✅")
                else:
                    st.caption("Vérification : persistance/PJ non confirmées (probable délai Gmail).")

            st.markdown("---")
            st.markdown(ctx["html"], unsafe_allow_html=True)
            if st.button("Terminer"):
                if _push_history:
                    _push_history("assistant", f"✉️ Email envoyé à {ctx['to_address']} depuis {ctx['from_address']}", "action")
                st.session_state["email_ctx"] = None
                st.session_state["email_result"] = None
                st.session_state["email_result_check"] = None
                st.session_state["email_local_files"] = []
                st.session_state["email_drive_added"] = []
                st.rerun()
            st.stop()

        from_choices = _list_possible_from_safe()
        current_from = ctx.get("from_address") or _prefer_alfred(from_choices)
        try:
            idx = max(0, from_choices.index(current_from))
        except ValueError:
            from_choices = [current_from] + [a for a in from_choices if a != current_from]
            idx = 0

        with st.expander("Expéditeur (alias)"):
            chosen = st.selectbox("Envoyer depuis :", options=from_choices, index=idx)
            ctx["from_address"] = chosen

        c1, c2 = st.columns([1, 1])
        with c1:
            ctx["to_address"] = st.text_input("À", value=ctx.get("to_address", ""))
        with c2:
            ctx["subject"] = st.text_input("Objet", value=ctx.get("subject", ""))

        body_md = st.text_area("Corps du message (texte / Markdown léger)",
                               value=ctx.get("text", ""), height=260)
        ctx["html"] = _plain_to_html(body_md)

        st.markdown("---")
        st.markdown("#### Pièces jointes (optionnel)")

        uploads = st.file_uploader("Ajouter depuis cet appareil", accept_multiple_files=True)
        if uploads:
            st.session_state["email_local_files"] = uploads

        col_q, col_btn = st.columns([3, 1])
        with col_q:
            drive_query = st.text_input("Ajouter depuis Drive (nom ou extrait)")
        with col_btn:
            if st.button("Ajouter depuis Drive", use_container_width=True):
                if not drive_query.strip():
                    st.warning("Saisis un nom ou un extrait.")
                else:
                    tmp, err = _resolve_drive_to_tmp(drive_query.strip())
                    if err:
                        st.error(f"Impossible d’exporter la pièce jointe Google : {err}")
                    elif tmp:
                        st.session_state["email_drive_added"].append(tmp)
                        st.success(f"Pièce jointe ajoutée depuis Drive : {tmp.name}")

        recaps: List[str] = []
        for up in st.session_state.get("email_local_files", []):
            try:
                size = len(up.getvalue())
            except Exception:
                size = "?"
            recaps.append(f"• {up.name} ({size} octets)")
        for p in st.session_state.get("email_drive_added", []):
            try:
                size = p.stat().st_size
            except Exception:
                size = "?"
            recaps.append(f"• {p.name} ({size} octets)")
        if recaps:
            st.markdown("**Pièces jointes sélectionnées :**\n" + "\n".join(recaps))

        # Boutons Envoyer / Annuler
        col_send, col_cancel = st.columns([1, 1])
        with col_send:
            if st.button("✅ Envoyer"):
                _do_send_now()
        with col_cancel:
            if st.button("Annuler"):
                # Reset complet du contexte email
                st.session_state["email_ctx"] = None
                st.session_state["email_result"] = None
                st.session_state["email_result_check"] = None
                st.session_state["email_local_files"] = []
                st.session_state["email_drive_added"] = []
                st.rerun()

    return True

# ========================= Envoi =========================

def _materialize_all_tmp() -> List[Path]:
    tmp_paths: List[Path] = []
    for up in st.session_state.get("email_local_files", []):
        data = up.getvalue()
        name = up.name or "piece_jointe"
        suffix = Path(name).suffix or ".bin"
        p = _save_tmp(data, name if suffix else name + suffix)
        tmp_paths.append(p)
    tmp_paths.extend(st.session_state.get("email_drive_added", []))
    return tmp_paths

def _do_send_now():
    ctx = st.session_state.get("email_ctx") or {}
    to_addr = (ctx.get("to_address") or "").strip()
    if not to_addr:
        st.warning("Renseigne un destinataire.")
        return

    svc = get_gmail_service()
    paths = [str(p) for p in _materialize_all_tmp()]

    try:
        resp = send_email(
            service=svc,
            to=to_addr,
            subject=ctx.get("subject") or "(sans objet)",
            html_body=ctx.get("html") or "<p></p>",
            from_address=ctx.get("from_address") or "alfred@selwancirque.com",
            attachments=paths if paths else None,
            headers={"X-Alfred": "v2.4"},
        )
    except Exception as e:
        st.error(f"Échec de l’envoi : {e}")
        return

    # Vérification auto : Gmail a bien persisté le message + PJ vues
    expected_att = len(paths)
    try:
        check = _verify_gmail_persisted(svc, resp["id"], expected_att)
    except Exception:
        check = {"ok": False, "meta": {}, "attachments_seen": None}
    st.session_state["email_result_check"] = check

    # Nettoyage des fichiers temporaires créés pendant cette session
    tmp_created = list(st.session_state.get("email_tmp_created", []))
    _cleanup_tmp_paths(tmp_created)
    st.session_state["email_tmp_created"] = set()

    st.session_state["email_ctx"]["attachments"] = paths
    st.session_state["email_result"] = resp
    st.rerun()
