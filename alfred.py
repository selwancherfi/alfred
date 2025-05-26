import streamlit as st
from router import router
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4

# Initialisation
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

# Authentification simple
if "auth_ok" not in st.session_state:
    mot_de_passe = st.text_input("Mot de passe :", type="password")
    if mot_de_passe == st.secrets["ALFRED_PASSWORD"]:
        st.session_state.auth_ok = True
    else:
        st.stop()

# Session state
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False

# Réinitialisation
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

# Historique affiché
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Zone de prompt
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Upload de fichier
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier à analyser (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader(
            label="Fichier à analyser",
            type=["txt", "pdf", "docx", "csv"],
            label_visibility="collapsed"
        )

# Traitement du prompt
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    reponse = router(prompt)

    if reponse is None:
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt
        reponse = repondre_avec_gpt4(prompt_final)

    st.session_state.messages.append({"role": "assistant", "content": reponse})
    with st.chat_message("assistant"):
        if isinstance(reponse, str) and ("📁" in reponse or "📄" in reponse):
            st.text(reponse)
        else:
            st.markdown(reponse)
