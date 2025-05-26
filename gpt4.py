import openai
import streamlit as st

openai.api_key = st.secrets["OPENAI_API_KEY"]

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
