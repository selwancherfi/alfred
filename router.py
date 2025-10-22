# router.py — Orchestrateur des briques (Drive / Mémoire / etc.)
# RÈGLE D’OR :
# - Si aucune brique ne prend en charge -> retourner None (le LLM répondra).
# - Ne renvoyer "error" que si une action reconnue a ÉCHOUÉ en exécution.
# - Drive : confirmations destructives, suppression par NOM (alignée avec connexiongoogledrive.py).

from __future__ import annotations
import streamlit as st

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

# petit alias, au cas où on en ait besoin plus tard
def _llm(prompt: str) -> str:
    return _llm_repondre_simple(prompt, temperature=None)

# Helpers de réponse standardisées
def _ok(msg: str)   -> dict: return {"content": msg, "subtype": "success"}
def _info(msg: str) -> dict: return {"content": msg, "subtype": "info"}
def _warn(msg: str) -> dict: return {"content": msg, "subtype": "warning"}
def _err(msg: str)  -> dict: return {"content": msg, "subtype": "error"}

def _fmt_liste(items: list[dict], maxn: int = 100) -> str:
    """Formate une liste de résultats Drive en puces lisibles."""
    if not items: return "Ce dossier est vide."
    out = []
    for i, it in enumerate(items[:maxn], 1):
        name = it.get("name") or it.get("nom") or it.get("id", "?")
        mt = (it.get("mimeType") or "").lower()
        prefix = "📁" if "folder" in mt else "📄"
        out.append(f"{i}. {prefix} {name}")
    return "\n".join(out)

def router(prompt: str) -> dict | None:
    """
    Retourne :
      - None quand aucune brique n’a pris en charge (=> fallback LLM dans alfred.py)
      - dict {content, subtype} quand une brique a répondu (Drive, etc.)
    """
    if not prompt or not isinstance(prompt, str):
        return None

    # --- Interprétation Drive (brique) ---
    try:
        intent = analyser_prompt_drive(prompt)
    except Exception:
        # En cas de souci d'analyse : ne bloque pas la conversation
        return None

    if not isinstance(intent, dict):
        return None

    action = intent.get("action")
    if action in (None, "fallback"):
        # Rien reconnu côté Drive -> laisser le LLM répondre
        return None

    # --------- CONFIRMATIONS / ANNULATIONS ---------
    # On mémorise l'ordre destructif dans l'état; ce routeur utilise la session Streamlit.
    pending = st.session_state.get("pending_drive")

    if action == "confirmer":
        if not pending:
            return _warn("Je n’ai aucune action en attente à confirmer.")
        if pending.get("action") == "supprimer":
            try:
                # parent_id si fourni
                parent_name = pending.get("parent") or ""
                parent_id = trouver_id_dossier_recursif(parent_name) if parent_name else None

                # suppression PAR NOM (alignée avec connexiongoogledrive.supprimer_element)
                nom = pending.get("nom") or ""
                if not nom:
                    st.session_state["pending_drive"] = None
                    return _err("Suppression impossible : nom de l’élément manquant.")
                msg = supprimer_element(nom, parent_id=parent_id)
                st.session_state["pending_drive"] = None
                # Les helpers Drive renvoient déjà un message prêt à afficher
                # mais on garde un cadre "success" pour cohérence UI
                if msg.strip().startswith("❌"):
                    return _err(msg)
                if msg.strip().startswith("🗑️") or msg.strip().startswith("✅"):
                    return _ok(msg)
                return _ok(msg or "Élément supprimé.")
            except Exception as e:
                st.session_state["pending_drive"] = None
                return _err(f"Erreur lors de la suppression : {e}")
        # autre ordre en attente non géré ici
        st.session_state["pending_drive"] = None
        return _warn("Rien à confirmer.")

    if action == "annuler":
        if pending:
            st.session_state["pending_drive"] = None
            return _info("Suppression annulée.")
        return _info("Aucune action en attente.")

    # --------- CLARIFICATIONS DEMANDÉES PAR L’INTERPRÉTEUR ---------
    if action == "clarifier":
        manque = intent.get("manque") or []
        if "type" in manque and "nom" in manque:
            return _warn("Précise **l’action**, le **type** (fichier/dossier) et le **nom**.")
        if "type" in manque:
            return _warn("Précise le **type** (fichier/dossier).")
        if "nom" in manque:
            return _warn("Précise le **nom** de l’élément.")
        return _warn("Ta demande est ambiguë. Donne : action + type + nom (+ parent si nécessaire).")

    # --------- ACTIONS DRIVE RECONNUES ---------
    try:
        parent_name = intent.get("parent") or ""
        parent_id = trouver_id_dossier_recursif(parent_name) if parent_name else FOLDER_ID

        # LISTER / AFFICHER
        if action in {"lister", "afficher"}:
            listing = lister_fichiers_dossier(None, parent_id)
            return _info(listing)

        # RECHERCHER
        if action == "rechercher":
            terme = intent.get("nom") or intent.get("terme") or ""
            if not terme:
                return _warn("Dis-moi ce que tu veux chercher.")
            res = rechercher_fichiers(terme, parent_id=parent_id)
            if not res:
                res = rechercher_fichiers(terme)  # secours global
            if not res:
                return _info("Aucun élément trouvé.")
            return _info(_fmt_liste(res))

        # LIRE / OUVRIR
        if action in {"lire", "ouvrir"}:
            nom = intent.get("nom") or ""
            if not nom:
                return _warn("Précise le nom du fichier à lire.")
            candidats = rechercher_fichiers(nom, parent_id=parent_id) or rechercher_fichiers(nom)
            if not candidats:
                return _info("Je n’ai trouvé aucun fichier correspondant.")
            file_id = candidats[0]["id"]
            contenu = lire_contenu_fichier(file_id)
            return _info(contenu)

        # CRÉER DOSSIER
        if action in {"creer_dossier", "créer_dossier", "creer", "créer"}:
            nom = intent.get("nom") or ""
            if not nom:
                return _warn("Donne le nom du dossier à créer.")
            msg = creer_dossier(nom, parent_id=parent_id)
            # la brique Drive renvoie déjà un message prêt à afficher
            if msg.strip().startswith("❌"):
                return _err(msg)
            return _ok(msg)

        # SUPPRIMER (→ demande de confirmation, pas d’exécution directe)
        if action in {"supprimer", "effacer"}:
            typ = intent.get("type")  # "fichier"/"dossier" (info pour le message)
            nom = intent.get("nom") or ""
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

        # action inconnue pour la brique Drive -> laisser le LLM
        return None

    except Exception as e:
        # Une action reconnue a échoué pendant l'exécution -> ERREUR
        return _err(f"Erreur Drive : {e}")
