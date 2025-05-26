import streamlit as st
from dotenv import load_dotenv
import os
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4
from connexiongoogledrive import lister_fichiers_dossier

# Charger les variables d'environnement
load_dotenv()

# Vérifier mot de passe
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

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

# Affichage de l’historique
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Prompt + bouton pièce jointe
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Upload de fichiers
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader("", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed")

# Traitement
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Commande spéciale Google Drive
    if prompt.startswith("/drive liste"):
        nom_sous_dossier = prompt.replace("/drive liste", "").strip()
        reponse_texte = lister_fichiers_dossier(nom_sous_dossier if nom_sous_dossier else None)
        st.text(reponse_texte)
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
    else:
        # Traitement normal
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt

        reponse_texte = repondre_avec_gpt4(prompt_final)
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
        with st.chat_message("assistant"):
            st.markdown(reponse_texte)
