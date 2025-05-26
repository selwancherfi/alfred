import openai
import streamlit as st
import json

openai.api_key = st.secrets["OPENAI_API_KEY"]

def analyser_prompt_drive(prompt_utilisateur):
    system_prompt = """
Tu es un assistant technique. Ta mission est de convertir une phrase en langage naturel en une commande structurée pour Google Drive.

Exemples :
- "Montre-moi ce qu’il y a dans le dossier photos" → {"action": "lister", "type": "dossier", "nom": "photos", "extension": null}
- "Quel est le contenu du dossier qu’on partage ?" → {"action": "lister", "type": "dossier", "nom": null, "extension": null}
- "Supprime le dossier test" → {"action": "supprimer", "type": "dossier", "nom": "test", "extension": null}
- "Crée un dossier nommé budget" → {"action": "creer", "type": "dossier", "nom": "budget", "extension": null}
- "Quel PDF est présent dans le dossier moto ?" → {"action": "lister", "type": "fichier", "nom": "moto", "extension": "pdf"}

Toujours répondre uniquement avec un JSON valide. Si tu ne comprends pas la requête, renvoie ceci : {"action": "fallback"}
"""

    try:
        client = openai.OpenAI()
        completion = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": prompt_utilisateur.strip()}
            ],
            temperature=0
        )
        texte = completion.choices[0].message.content.strip()
        return json.loads(texte)
    except Exception as e:
        print(f"❌ Erreur dans l'analyse du prompt Drive : {e}")
        return {"action": "fallback"}
