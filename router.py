from connexiongoogledrive import lister_fichiers_dossier, creer_dossier, supprimer_element
from interpreteur import analyser_prompt_drive

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
