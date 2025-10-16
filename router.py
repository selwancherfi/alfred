# router.py

from connexiongoogledrive import lister_fichiers_dossier, creer_dossier, supprimer_element
from interpreteur import analyser_prompt_drive

# 🔵 LLM (alias) — on force temperature=None dans notre wrapper local
import json
from llm import repondre_simple as _llm_repondre_simple

def repondre_avec_gpt4(prompt: str) -> str:
    # Compat historique : appel LLM sans temperature explicite
    return _llm_repondre_simple(prompt, temperature=None)


def router(prompt):
    data = analyser_prompt_drive(prompt)

    if not data or data.get("action") == "fallback":
        return None  # Signal pour GPT normal

    action = data.get("action")
    nom = data.get("nom")
    extension = data.get("extension")

    if action == "lister":
        return lister_fichiers_dossier(nom)
    elif action == "creer":
        return creer_dossier(nom)
    elif action == "supprimer":
        return supprimer_element(nom)
    else:
        return "❌ Action non reconnue dans la commande interprétée."


# ============================== 🔵 NLU MÉMOIRE ==============================
def nlu_memory_intent(utterance: str):
    """
    Détecte si la phrase concerne la mémoire et renvoie un dict ou None.
    Intents possibles: remember, remember_category, recall, recall_category, forget, import
    """
    if not utterance or not utterance.strip():
        return None

    prompt = f"""
Tu es un routeur NLU. Extrait l'intention liée à la mémoire si elle existe.
Réponds UNIQUEMENT en JSON compact, SANS commentaire.

Exemples:
- "peux-tu te souvenir que je vis à Paris ?" -> {{"intent":"remember","text":"je vis à Paris"}}
- "rappelle-toi" -> {{"intent":"recall"}}
- "rappelle projet" -> {{"intent":"recall_category","category":"projet"}}
- "oublie le souvenir sur les lasagnes" -> {{"intent":"forget","text":"les lasagnes"}}
- "intègre ceci :\\nligne 1\\nligne 2" -> {{"intent":"import","text":"ligne 1\\nligne 2"}}
- "souviens-toi de projet : Silky Experience est prioritaire" -> {{"intent":"remember_category","category":"projet","text":"Silky Experience est prioritaire"}}

Si la phrase NE concerne PAS la mémoire, réponds null (sans guillemets).

Phrase: {utterance}
"""
    raw = repondre_avec_gpt4(prompt).strip()
    try:
        data = json.loads(raw) if raw and raw != "null" else None
        if isinstance(data, dict) and data.get("intent") in {
            "remember", "remember_category", "recall", "recall_category", "forget", "import"
        }:
            data["text"] = (data.get("text") or "").strip()
            data["category"] = (data.get("category") or "").strip()
            return data
    except Exception:
        pass
    return None
# ============================ FIN 🔵 NLU MÉMOIRE ============================
