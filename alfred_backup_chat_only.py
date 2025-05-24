import streamlit as st
import openai
import os
from dotenv import load_dotenv

# Charger la clé API OpenAI
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configuration de la page
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.write("Je suis Alfred, ton assistant personnel IA.")

# Initialisation de la mémoire de conversation
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "Tu es Alfred, l’assistant personnel bienveillant de Selwan."}
    ]

# Bouton pour réinitialiser la conversation
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = [
        {"role": "system", "content": "Tu es Alfred, l’assistant personnel bienveillant de Selwan."}
    ]
    st.rerun()

# Affichage des échanges précédents
for msg in st.session_state.messages[1:]:
    with st.chat_message("user" if msg["role"] == "user" else "assistant"):
        st.markdown(msg["content"])

# Champ de saisie (stable)
user_input = st.chat_input("Tape ici ta demande...")

# Envoi de la demande si champ rempli
if user_input:
    # Afficher message utilisateur
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})

    # Réponse d’Alfred
    with st.chat_message("assistant"):
        with st.spinner("Alfred réfléchit..."):
            try:
                response = openai.chat.completions.create(
                    model="gpt-4",
                    messages=st.session_state.messages
                )
                output = response.choices[0].message.content
                st.markdown(output)
                st.session_state.messages.append({"role": "assistant", "content": output})
            except Exception as e:
                st.error(f"Erreur GPT : {e}")

