# router.py — Orchestrateur des briques (Email / Drive / Mémoire)
# RÈGLES :
# - Si aucune brique ne prend en charge -> retourner None (le LLM répondra dans alfred.py).
# - Ne renvoyer "error" que si une action reconnue a ÉCHOUÉ en exécution.
# - On tente d'abord l'orchestration générale (intents via LLM + regex),
#   puis on retombe sur le routeur Drive existant (compatibilité).

from __future__ import annotations

import re
import json
import streamlit as st
from typing import Dict, Any

# === Orchestration générale ===
from skills.registry import get_executor
from llm import repondre_chat as _llm_chat  # on l'utilise pour obtenir un JSON strict

# === Fallback / compat Drive existant ===
from interpreteur import analyser_prompt_drive
from llm import repondre_simple as _llm_repondre_simple
from connexiongoogledrive import (
    lister_fichiers_dossier,
    creer_dossier,
    supprimer_element,              # ⚠️ supprime PAR NOM (et parent_id optionnel)
    lire_contenu_fichier,
    rechercher_fichiers,
    trouver_id_dossier_recursif,
    FOLDER_ID,
)

def _llm(prompt: str) -> str:
    return _llm_repondre_simple(prompt, temperature=None)

def _ok(msg: str)   -> dict: return {"content": msg, "subtype": "success"}
def _info(msg: str) -> dict: return {"content": msg, "subtype": "info"}
def _warn(msg: str) -> dict: return {"content": msg, "subtype": "warning"}
def _err(msg: str)  -> dict: return {"content": msg, "subtype": "error"}

def _fmt_liste(items: list[dict], maxn: int = 100) -> str:
    if not items:
        return "Ce dossier est vide."
    out = []
    for i, it in enumerate(items[:maxn], 1):
        name = it.get("name") or it.get("nom") or it.get("id", "?")
        mt = (it.get("mimeType") or "").lower()
        prefix = "📁" if "folder" in mt else "📄"
        out.append(f"{i}. {prefix} {name}")
    return "\n".join(out)

# ---------------- Orchestration v2.5 : routeur d’intent ----------------

_DEF_EMAIL_RE = re.compile(
    r"\b(envoi[sezr]?|envoy(?:er|e|ez|ons|es|e))\b.*\b(mail|email|courriel|m[èe]l)\b", re.I
)

def _normalize(text: str) -> str:
    import unicodedata, re as _re
    t = (text or "").strip().lower()
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return _re.sub(r"\s+", " ", t)

def _route_intent(user_text: str) -> Dict[str, Any]:
    t = _normalize(user_text or "")

    # 1) Raccourci regex tolérant pour l'email (capte "envois", "envoi", "mèl", etc.)
    if _DEF_EMAIL_RE.search(t):
        # On garde le raw pour la brique email
        return {"intent": "email.compose", "confidence": 0.65, "slots": {"raw_text": user_text}}

    # 2) Tentative LLM (JSON STRICT)
    prompt = f"""
Tu es un routeur d'intentions en français. Réponds UNIQUEMENT par un JSON strict :
{{"intent": "...", "confidence": 0.xx, "slots": {{...}}}}
Texte : {user_text}
Intents possibles : email.compose, email.reply, email.forward,
                    drive.find, drive.export, drive.share,
                    memory.save, memory.find
Ne rends AUCUN autre texte.
"""
    try:
        messages = [
            {"role": "system", "content": "Tu renvoies exclusivement du JSON strict conforme."},
            {"role": "user", "content": prompt},
        ]
        raw_text = _llm_chat(messages, temperature=0.1)
        data = json.loads(raw_text)

        intent = data.get("intent", "unknown")
        conf = float(data.get("confidence", 0.0))
        slots = data.get("slots", {})

        if intent not in (
            "email.compose","email.reply","email.forward",
            "drive.find","drive.export","drive.share",
            "memory.save","memory.find"
        ):
            intent = "unknown"

        # On injecte aussi le texte brut dans les slots pour les briques qui en ont besoin
        if isinstance(slots, dict):
            slots.setdefault("raw_text", user_text)

        return {"intent": intent, "confidence": conf, "slots": slots}
    except Exception:
        return {"intent": "unknown", "confidence": 0.0, "slots": {}}

# ---------------------------- Routeur principal ----------------------------

def router(prompt: str) -> dict | None:
    if not prompt or not isinstance(prompt, str):
        return None

    # 1) Orchestration générale
    try:
        parsed = _route_intent(prompt)
        intent = parsed.get("intent")
        slots = parsed.get("slots", {}) if isinstance(parsed, dict) else {}

        if intent and intent != "unknown":
            exec_info = get_executor(intent)
            if exec_info:
                exec_func, is_ui_intent = exec_info

                # 🔴 CAS SPÉCIAL : email.compose -> on appelle directement la brique email
                # avec le texte brut, et on renvoie un marqueur spécial pour Alfred.
                if intent == "email.compose":
                    raw = slots.get("raw_text", prompt)
                    # la brique email gère le contexte + st.session_state, on ignore son retour
                    exec_func(raw)
                    return {"_type": "ui_email_bootstrapped"}

                # Autres briques : exécution "normale"
                try:
                    if is_ui_intent:
                        return exec_func(slots)   # UI (ex: future brique Drive avec UI)
                    return exec_func(**slots) if isinstance(slots, dict) else exec_func(slots)
                except TypeError:
                    return exec_func(slots)
    except Exception:
        pass

    # 2) Fallback : routeur Drive existant (compat)
    try:
        intent_drive = analyser_prompt_drive(prompt)
    except Exception:
        return None

    if not isinstance(intent_drive, dict):
        return None

    action = intent_drive.get("action")
    if action in (None, "fallback"):
        return None

    pending = st.session_state.get("pending_drive")

    if action == "confirmer":
        if not pending:
            return _warn("Je n’ai aucune action en attente à confirmer.")
        if pending.get("action") == "supprimer":
            try:
                parent_name = pending.get("parent") or ""
                parent_id = trouver_id_dossier_recursif(parent_name) if parent_name else None
                nom = pending.get("nom") or ""
                if not nom:
                    st.session_state["pending_drive"] = None
                    return _err("Suppression impossible : nom de l’élément manquant.")
                msg = supprimer_element(nom, parent_id=parent_id)
                st.session_state["pending_drive"] = None
                if msg.strip().startswith("❌"):
                    return _err(msg)
                if msg.strip().startswith(("🗑️", "✅")):
                    return _ok(msg)
                return _ok(msg or "Élément supprimé.")
            except Exception as e:
                st.session_state["pending_drive"] = None
                return _err(f"Erreur lors de la suppression : {e}")
        st.session_state["pending_drive"] = None
        return _warn("Rien à confirmer.")

    if action == "annuler":
        if pending:
            st.session_state["pending_drive"] = None
            return _info("Suppression annulée.")
        return _info("Aucune action en attente.")

    if action == "clarifier":
        manque = intent_drive.get("manque") or []
        if "type" in manque and "nom" in manque:
            return _warn("Précise **l’action**, le **type** (fichier/dossier) et le **nom**.")
        if "type" in manque:
            return _warn("Précise le **type** (fichier/dossier).")
        if "nom" in manque:
            return _warn("Précise le **nom** de l’élément.")
        return _warn("Ta demande est ambiguë. Donne : action + type + nom (+ parent si nécessaire).")

    try:
        parent_name = intent_drive.get("parent") or ""
        parent_id = trouver_id_dossier_recursif(parent_name) if parent_name else FOLDER_ID

        if action in {"lister", "afficher"}:
            listing = lister_fichiers_dossier(None, parent_id)
            return _info(listing)

        if action == "rechercher":
            terme = intent_drive.get("nom") or intent_drive.get("terme") or ""
            if not terme:
                return _warn("Dis-moi ce que tu veux chercher.")
            res = rechercher_fichiers(terme, parent_id=parent_id)
            if not res:
                res = rechercher_fichiers(terme)
            if not res:
                return _info("Aucun élément trouvé.")
            return _info(_fmt_liste(res))

        if action in {"lire", "ouvrir"}:
            nom = intent_drive.get("nom") or ""
            if not nom:
                return _warn("Précise le nom du fichier à lire.")
            candidats = rechercher_fichiers(nom, parent_id=parent_id) or rechercher_fichiers(nom)
            if not candidats:
                return _info("Je n’ai trouvé aucun fichier correspondant.")
            file_id = candidats[0]["id"]
            contenu = lire_contenu_fichier(file_id)
            return _info(contenu)

        if action in {"creer_dossier", "créer_dossier", "creer", "créer"}:
            nom = intent_drive.get("nom") or ""
            if not nom:
                return _warn("Donne le nom du dossier à créer.")
            msg = creer_dossier(nom, parent_id=parent_id)
            if msg.strip().startswith("❌"):
                return _err(msg)
            return _ok(msg)

        if action in {"supprimer", "effacer"}:
            typ = intent_drive.get("type")
            nom = intent_drive.get("nom") or ""
            if not typ or not nom:
                return _warn("Pour supprimer : précise **type** (fichier/dossier) et **nom**.")
            st.session_state["pending_drive"] = {
                "action": "supprimer",
                "type": typ,
                "nom": nom,
                "parent": parent_name or "",
            }
            where = f" dans « {parent_name} »" if parent_name else ""
            return _warn(
                f"⚠️ Tu me demandes de **supprimer** le **{typ}** « {nom} »{where} sur Drive.\n"
                f"Confirme avec **« confirme »** ou annule avec **« annule »**."
            )

        return None

    except Exception as e:
        return _err(f"Erreur Drive : {e}")
