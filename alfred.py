import os
import streamlit as st
from router import router, nlu_memory_intent
from lecturefichiersbase import lire_fichier
from llm import repondre_simple, set_runtime_model, get_model

# --- DOIT ÊTRE APPELÉ EN PREMIER ---
st.set_page_config(page_title="Alfred v2.1", page_icon="🤖", layout="wide")

# ========== 🔒 Gate par mot de passe (compatible local + cloud) ==========
def _get_password():
    env_pw = os.getenv("APP_PASSWORD") or os.getenv("ALFRED_PASSWORD")
    if env_pw:
        return env_pw
    try:
        return st.secrets.get("APP_PASSWORD", st.secrets.get("ALFRED_PASSWORD", ""))
    except Exception:
        return ""

APP_PASSWORD = _get_password()

# Bouton "Déconnexion" si déjà authentifié
if st.session_state.get("_pwd_ok"):
    with st.sidebar:
        if st.button("Se déconnecter"):
            st.session_state["_pwd_ok"] = False
            st.rerun()

# Si un mot de passe est défini et qu'on n'est pas encore authentifié → afficher le gate
if APP_PASSWORD and not st.session_state.get("_pwd_ok", False):
    with st.sidebar:
        st.markdown("### 🔒 Accès")
        pwd = st.text_input("Mot de passe", type="password")
        if st.button("Valider"):
            if pwd == APP_PASSWORD:
                st.session_state["_pwd_ok"] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
    st.stop()
# ==========================================================================

# En-tête
st.title("🤖 Alfred — version 2.1 (mémoire persistante + modèle configurable)")
st.caption(f"✅ App prête — modèle actif : **{get_model()}**")

# Mémoire & logs
from memoire_alfred import (
    get_memory,
    log_event,
    try_handle_memory_command,
    autosave_heartbeat,
    confirm_delete,
)

# Sidebar : sélecteur de modèle
with st.sidebar:
    st.markdown("### Modèle LLM")
    model_choice = st.selectbox(
        "Sélection du modèle",
        options=["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
        index=0,
        help="Change à chaud le modèle de raisonnement",
    )
    set_runtime_model(model_choice)

# Boîte de confirmation de suppression
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

# Corps
autosave_heartbeat()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Historique
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Widgets
fichier = st.file_uploader("📎 Joindre un fichier (optionnel)", type=None)
prompt = st.chat_input("Parle à Alfred…")

# UI suppression si besoin
_render_delete_confirmation()

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 1) Commandes mémoire
    handled, payload = try_handle_memory_command(prompt)
    if handled:
        if isinstance(payload, str):
            st.success(payload)
            st.stop()
        if isinstance(payload, list):
            if not payload:
                st.info("Aucun souvenir correspondant.")
                st.stop()
            st.markdown("### 🧠 Souvenirs")
            for s in payload:
                st.write(f"- [{s['date']}] {s['texte']}")
            st.stop()
        if isinstance(payload, dict) and payload.get("_type") == "confirm_delete":
            st.session_state["pending_delete"] = payload
            st.rerun()

    # 2) Routeur (Drive…)
    reponse = router(prompt)
    if reponse is None:
        # 3) Fallback LLM (⚠️ pas de temperature)
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt
        reponse = repondre_simple(prompt_final, temperature=None)

    # Affichage réponse
    st.session_state.messages.append({"role": "assistant", "content": reponse})
    with st.chat_message("assistant"):
        st.markdown(reponse)
