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

# Initialiser la session pour la mémoire
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False

# Bouton pour réinitialiser la conversation
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

# Fonction pour lire les fichiers
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

# Afficher les messages précédents
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Interface chat + bouton fichier
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Afficher uploader si demandé
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader("", type=["txt", "pdf", "docx", "csv"], label_visibility="collapsed")

# Si prompt envoyé
if prompt:
    # Lecture du fichier si présent
    if fichier:
        contenu = lire_fichier(fichier)
        prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
    else:
        prompt_final = prompt

    # Ajouter la demande de l’utilisateur à la mémoire
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    try:
        # Appel à l’API OpenAI
        reponse = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Tu es un assistant utile et concis."},
                {"role": "user", "content": prompt_final}
            ]
        )
        reponse_texte = reponse.choices[0].message.content

        # Afficher la réponse
        st.session_state.messages.append({"role": "assistant", "content": reponse_texte})
        with st.chat_message("assistant"):
            st.markdown(reponse_texte)

    except Exception as e:
        erreur = f"Erreur GPT : {str(e)}"
        st.session_state.messages.append({"role": "assistant", "content": erreur})
        with st.chat_message("assistant"):
            st.markdown(erreur)
