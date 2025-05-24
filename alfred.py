import streamlit as st
import openai
import os
import fitz  # PyMuPDF
import pandas as pd
from docx import Document
from dotenv import load_dotenv

# Configuration Streamlit
st.set_page_config(page_title="Alfred", page_icon="🤖")

# Clé API
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Mémoire conversationnelle
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": "Tu es Alfred, l’assistant personnel bienveillant de Selwan."}
    ]

if "last_uploaded_filename" not in st.session_state:
    st.session_state.last_uploaded_filename = None

# Réinitialisation
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = [
        {"role": "system", "content": "Tu es Alfred, l’assistant personnel bienveillant de Selwan."}
    ]
    st.session_state.last_uploaded_filename = None

# Interface
st.title("Bienvenue, Selwan 👋")
st.write("Je suis Alfred, ton assistant personnel IA.")
st.markdown("---")

# Fonctions de lecture
def read_pdf(file) -> str:
    with fitz.open(stream=file.read(), filetype="pdf") as doc:
        return "".join([page.get_text() for page in doc])

def read_docx(file) -> str:
    document = Document(file)
    return "\n".join([para.text for para in document.paragraphs])

def read_csv(file) -> str:
    df = pd.read_csv(file)
    return df.to_string(index=False)

# Upload fichier + instruction
st.subheader("📎 Envoie un fichier + une instruction personnalisée")
uploaded_file = st.file_uploader("Fichier (.txt, .pdf, .docx ou .csv)", type=["txt", "pdf", "docx", "csv"])
custom_instruction = st.text_area("Quelle tâche Alfred doit-il effectuer sur ce fichier ?", "")

if uploaded_file and custom_instruction.strip():
    current_filename = uploaded_file.name

    if current_filename != st.session_state.last_uploaded_filename:
        # Lecture selon le type de fichier
        if current_filename.endswith(".txt"):
            content = uploaded_file.read().decode("utf-8")
        elif current_filename.endswith(".pdf"):
            content = read_pdf(uploaded_file)
        elif current_filename.endswith(".docx"):
            content = read_docx(uploaded_file)
        elif current_filename.endswith(".csv"):
            content = read_csv(uploaded_file)
        else:
            content = ""

        with st.spinner("Alfred réfléchit à ta demande..."):
            try:
                response = openai.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "Tu es Alfred, assistant personnel de Selwan."},
                        {"role": "user", "content": f"Voici une tâche : {custom_instruction}\n\nVoici le contenu du fichier :\n{content}"}
                    ]
                )
                output = response.choices[0].message.content

                st.session_state.messages.append({
                    "role": "user",
                    "content": f"(Fichier : {current_filename}) {custom_instruction}"
                })
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": output
                })

                st.session_state.last_uploaded_filename = current_filename

            except Exception as e:
                st.error(f"Erreur GPT : {e}")

# Affichage du chat
for msg in st.session_state.messages[1:]:
    with st.chat_message("user" if msg["role"] == "user" else "assistant"):
        st.markdown(msg["content"])

# Entrée chat libre
user_input = st.chat_input("Tape ici ta demande...")

if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})

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
