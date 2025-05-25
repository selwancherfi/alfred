import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def repondre_avec_gpt4(prompt_utilisateur):
    try:
        reponse = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant utile et concis."},
                {"role": "user", "content": prompt_utilisateur}
            ]
        )
        return reponse.choices[0].message.content
    except Exception as e:
        return f"Erreur GPT : {str(e)}"
