import streamlit as st
import openai
import os
from dotenv import load_dotenv
import fitz  # PyMuPDF
import docx
import pandas as pd

# Charger les variables d'environnement
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

# Initialiser la session
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False

# Bouton reset
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

# Fonction lecture fichier
def lire_fichier(fichier):
    if fichier.type == "text/plain":
        return fichier.read().decode("utf-8")
    elif fichier.type == "application/pdf":
        with fitz.open(stream=fichier.read(), filetype="pdf") as doc:
            return "\n".join([page.get_text() for page in doc])
    elif fichier.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = docx.Document(fichier)
        return "\n".join([para.text for para in doc.paragraphs])
    elif fichier.type == "text/csv":
        df = pd.read_csv(fichier)
        return df.to_string(index=False)
    else:
        return "Format de fichier non pris en charge."

# Affichage des anciens messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Champ de prompt + bouton en dessous du fil de messages
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Upload visible si déclenché
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader("", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed")

# Traitement du prompt
if prompt:
    if fichier:
        contenu = lire_fichier(fichier)
        prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
    else:
        prompt_final = prompt

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        reponse = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant utile et concis."},
                {"role": "user", "content": prompt_final}
            ]
        )
        reponse_texte = reponse.choices[0].message.content
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
        with st.chat_message("assistant"):
            st.markdown(reponse_texte)
    except Exception as e:
        erreur = f"Erreur GPT : {str(e)}"
        st.session_state.messages.append({"role": "assistant", "content": erreur})
        with st.chat_message("assistant"):
            st.markdown(erreur)
