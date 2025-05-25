import streamlit as st
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4
import os
from dotenv import load_dotenv

# Charger le mot de passe depuis le .env
load_dotenv()
PASSWORD = os.getenv("ALFRED_PASSWORD")

# Authentification
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    mot_de_passe = st.text_input("Mot de passe :", type="password")
    if mot_de_passe == PASSWORD:
        st.session_state.authenticated = True
        st.rerun()
    elif mot_de_passe:
        st.error("Mot de passe incorrect")
    st.stop()

# Interface principale une fois connecté
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False

if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader("", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed")

if prompt:
    if fichier:
        contenu = lire_fichier(fichier)
        prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
    else:
        prompt_final = prompt

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    reponse_texte = repondre_avec_gpt4(prompt_final)
    st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
    with st.chat_message("assistant"):
        st.markdown(reponse_texte)
