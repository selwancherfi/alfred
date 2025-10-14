import streamlit as st
from router import router, nlu_memory_intent
from lecturefichiersbase import lire_fichier
from llm import repondre_simple, set_runtime_model, get_model

# --- DOIT ÊTRE APPELÉ EN PREMIER ---
st.set_page_config(page_title="Alfred v2.1", page_icon="🤖", layout="wide")

# =========================================================
# En-tête (affiché avant tout pour éviter toute page "vide")
# =========================================================
st.title("🤖 Alfred — version 2.1 (mémoire persistante + modèle configurable)")
st.caption(f"✅ App prête — modèle actif: **{get_model()}**")

# --- Mémoire & logs ---
from memoire_alfred import (
    get_memory,
    log_event,
    try_handle_memory_command,
    autosave_heartbeat,
    confirm_delete,
)

# --- Sélecteur de modèle (optionnel) ---
with st.sidebar:
    st.markdown("### Modèle LLM")
    model_choice = st.selectbox(
        "Sélection du modèle",
        options=["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
        index=0,
        help="Change à chaud le modèle de raisonnement"
    )
    set_runtime_model(model_choice)

# =========================================================
# Boîte de confirmation de suppression (UI)
# =========================================================
def _render_delete_confirmation():
    payload = st.session_state.get("pending_delete")
    if not payload or payload.get("_type") != "confirm_delete":
        return

    item = payload.get("item", {})
    texte = item.get("texte", "")
    loc = payload.get("location")
    cat = payload.get("category")

    msg = f"Confirmer la suppression du souvenir :\n\n> **{texte}**"
    if loc == "categorie" and cat:
        msg += f"\n\n(Catégorie : **{cat}**)"

    st.warning(msg)
    c1, c2 = st.columns(2)
    if c1.button("✅ Oui, supprimer"):
        res = confirm_delete(payload)
        st.success(res)
        st.session_state["pending_delete"] = None
    if c2.button("❌ Annuler"):
        st.info("Suppression annulée.")
        st.session_state["pending_delete"] = None

# =========================================================
# Corps de l'app
# =========================================================

# Heartbeat autosave (RAM -> Drive périodique)
autosave_heartbeat()

# Historique de chat en session
if "messages" not in st.session_state:
    st.session_state.messages = []

# Afficher l'historique
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if isinstance(m["content"], str) and ("📁" in m["content"] or "📄" in m["content"]):
            st.text(m["content"])
        else:
            st.markdown(m["content"])

# Zone de saisie utilisateur (footer)
prompt = st.chat_input("Parle à Alfred…")

# Uploader (dans le corps)
fichier = st.file_uploader("📎 Joindre un fichier (optionnel)", type=None)

# Rendre la boîte de confirmation si besoin
_render_delete_confirmation()

if prompt:
    # Afficher le message utilisateur dans le chat
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Étape 1 : intents mémoire (ajout, rappel, suppression, import…)
    handled, payload = try_handle_memory_command(prompt)
    if handled:
        # Cas 1 : message simple (ex: "🧠 C’est noté...")
        if isinstance(payload, str):
            st.success(payload)
            st.stop()

        # Cas 2 : rappel (liste)
        if isinstance(payload, list):
            if not payload:
                st.info("Aucun souvenir correspondant.")
                st.stop()
            st.markdown("### 🧠 Souvenirs")
            for s in payload:
                st.write(f"- [{s['date']}] {s['texte']}")
            st.stop()

        # Cas 3 : suppression — poser le payload puis relancer pour afficher les boutons
        elif isinstance(payload, dict) and payload.get("_type") == "confirm_delete":
            st.session_state["pending_delete"] = payload
            st.rerun()  # affiche immédiatement la boîte Oui/Non

    # Étape 2 : Routage Drive & co (briques spécialisées)
    reponse = router(prompt)
    if reponse is None:
        # Étape 3 : Appel LLM "par défaut"
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt

        # 🔁 Appel au LLM via couche générique (modèle défini par l’UI/ENV)
        reponse = repondre_simple(prompt_final)

    # Affichage de la réponse
    st.session_state.messages.append({"role": "assistant", "content": reponse})
    with st.chat_message("assistant"):
        if isinstance(reponse, str) and ("📁" in reponse or "📄" in reponse):
            st.text(reponse)
        else:
            st.markdown(reponse)
