import json
import re
from llm import repondre_chat, get_model

# -------------------------------
# Helpers de détection / slots
# -------------------------------
def _mentions_drive(u: str) -> bool:
    return bool(re.search(r"\b(google\s+)?drive\b", u))

def _mentions_fichier_ou_dossier(u: str) -> bool:
    return any(k in u for k in ["fichier", "dossier", "sous dossier", "sous-dossier"])

def _aliases_drive_vers_racine(utterance: str):
    u = (utterance or "").strip().lower()
    if re.search(r"\b(mon\s+)?(google\s+)?drive\b", u) and any(
        k in u for k in ["contenu", "dossier", "affiche", "montre", "voir", "liste"]
    ):
        return {"action": "lister", "type": "dossier", "nom": None, "extension": None}
    return None

def _extraire_parent(expr: str):
    # ... "dans <Nom de dossier>"
    m = re.search(r"\bdans\s+([a-zA-ZÀ-ÿ0-9 _\-]+)$", (expr or ""), flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None

def _detect_confirme_annule(u: str):
    u = u.strip().lower()
    if u in {"confirme", "je confirme", "oui confirme", "valide", "ok confirme"}:
        return {"action": "confirmer"}
    if u in {"annule", "j'annule", "non annule", "annuler"}:
        return {"action": "annuler"}
    return None

# -------------------------------
# Analyseur principal
# -------------------------------
def analyser_prompt_drive(prompt_utilisateur: str):
    """
    Retourne un JSON d'intention Drive **strict**.
    Pour les actions destructives (supprimer), on exige action + objet + cible claire.
    Sinon -> on renvoie une demande de clarification minimaliste.
    """
    if not prompt_utilisateur:
        return {"action": "fallback"}

    # 1) confirmations
    ca = _detect_confirme_annule(prompt_utilisateur)
    if ca:
        return ca

    # 2) alias "Drive" vers racine
    direct = _aliases_drive_vers_racine(prompt_utilisateur)
    if direct:
        return direct

    # 3) extraction parent
    parent_nom = _extraire_parent(prompt_utilisateur or "")

    u = (prompt_utilisateur or "").strip().lower()
    espace = "drive" if (_mentions_drive(u) or _mentions_fichier_ou_dossier(u)) else None

    # 4) Prompt système : on force une grammaire d'action stricte
    system_prompt = (
        "Tu es un routeur d'ordres pour Google Drive. Convertis la phrase en JSON compact.\n"
        "Réponds UNIQUEMENT avec un JSON valide.\n"
        "Champs possibles:\n"
        "- action: {lister|lire|creer|supprimer|lire_match|resumer|clarifier|confirmer|annuler}\n"
        "- type: {fichier|dossier|sous-dossier}\n"
        "- nom: string (nom fichier/dossier ciblé)\n"
        "- extension: string|null\n"
        "- parent: string|null (dossier parent si précisé par 'dans ...')\n"
        "- manque: array de champs manquants si action=clarifier\n"
        "- index: entier pour lire_match\n\n"
        "Règles:\n"
        "1) Si la phrase parle de 'fichier/dossier' (ou 'Drive'), suppose espace=Drive.\n"
        "2) Pour SUPPRIMER (action destructrice), exige au moins: action='supprimer', type, nom. Si ambigu -> action='clarifier' avec manque.\n"
        "3) 'Crée un dossier X dans Y' => {action:'creer', type:'dossier', nom:'X', parent:'Y'}\n"
        "4) 'Supprime le sous dossier X dans Y' => {action:'supprimer', type:'sous-dossier', nom:'X', parent:'Y'}\n"
        "5) 'Lis le fichier contrat.pdf' => {action:'lire', type:'fichier', nom:'contrat.pdf', extension:'pdf'}\n"
        "6) 'Choisis 2' => {action:'lire_match', index:2}\n"
        "7) 'Résume le document que tu viens de lire' => {action:'resumer'}\n"
        "8) Si incompris -> {action:'fallback'}\n"
    )

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user",    "content": (prompt_utilisateur or "").strip()},
        ]
        texte = repondre_chat(messages, temperature=0)
        data = json.loads(texte)

        # 5) injections post-parse : parent issu du 'dans ...'
        if parent_nom and isinstance(data, dict) and data.get("action") in {"creer", "supprimer"} and data.get("type") in {"dossier", "sous-dossier"}:
            data["parent"] = parent_nom

        # 6) durcissement destructif : si SUPPRIMER sans 'type' ou 'nom' -> clarifier
        if isinstance(data, dict) and data.get("action") == "supprimer":
            manque = []
            if not data.get("type"):
                manque.append("type")
            if not data.get("nom"):
                manque.append("nom")
            if manque:
                return {"action": "clarifier", "manque": manque}

        # 7) si rien d'exploitable
        if not isinstance(data, dict):
            return {"action": "fallback"}

        return data

    except Exception as e:
        print(f"❌ Erreur dans l'analyse du prompt Drive : {e}")
        return {"action": "fallback"}
