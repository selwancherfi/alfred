import streamlit as st
from dotenv import load_dotenv
import os
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4
from connexiongoogledrive import lister_fichiers_dossier, creer_dossier

# Chargement des variables d’environnement
load_dotenv()

# Configuration Streamlit
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

# Authentification
if "auth_ok" not in st.session_state:
    mot_de_passe = st.text_input("Mot de passe :", type="password")
    if mot_de_passe == os.getenv("ALFRED_PASSWORD"):
        st.session_state.auth_ok = True
    else:
        st.stop()

# Initialisation de session
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False

# Bouton reset
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

# Historique affiché
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Prompt + pièce jointe
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Upload
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader("", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed")

# Traitement
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Commande spéciale : /drive liste
    if prompt.startswith("/drive liste"):
        nom = prompt.replace("/drive liste", "").strip()
        reponse_texte = lister_fichiers_dossier(nom if nom else None)
        st.text(reponse_texte)
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})

    # Commande spéciale : /drive creer
    elif prompt.startswith("/drive creer"):
        nom = prompt.replace("/drive creer", "").strip()
        if not nom:
            reponse_texte = "❌ Merci d’indiquer un nom de dossier. Exemple : `/drive creer Budget2025`"
        else:
            reponse_texte = creer_dossier(nom)
        st.text(reponse_texte)
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})

    # Traitement classique avec GPT
    else:
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt
        reponse_texte = repondre_avec_gpt4(prompt_final)
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
        with st.chat_message("assistant"):
            st.markdown(reponse_texte)
