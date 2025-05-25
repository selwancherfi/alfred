import streamlit as st
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4

st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

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
        fichier = st.file_uploader(
            "", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed"
        )

# Traitement
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
