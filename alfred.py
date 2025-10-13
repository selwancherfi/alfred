import streamlit as st
from router import router, nlu_memory_intent
from lecturefichiersbase import lire_fichier
from gpt4 import repondre_avec_gpt4

# --- Mémoire & logs ---
from memoire_alfred import (
    get_memory,
    log_event,
    try_handle_memory_command,
    autosave_heartbeat,
    confirm_delete,
)

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


# ========================================
# Initialisation de l’application
# ========================================
st.set_page_config(page_title="Alfred", page_icon="🤖")
st.title("Bienvenue, Selwan 👋")
st.markdown("Je suis Alfred, ton assistant personnel IA.")

# Mémoire en RAM + logs
_ = get_memory()
log_event("Session Alfred démarrée.")
autosave_heartbeat()

# Session state
if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "messages" not in st.session_state:
    st.session_state.messages = []
if "show_uploader" not in st.session_state:
    st.session_state.show_uploader = False
if "pending_delete" not in st.session_state:
    st.session_state["pending_delete"] = None

# =========================
# Authentification
# =========================
if not st.session_state.auth_ok:
    mot_de_passe = st.text_input("Mot de passe :", type="password")
    if mot_de_passe == st.secrets["ALFRED_PASSWORD"]:
        st.session_state.auth_ok = True
        st.rerun()  # recharge l’UI après login
    else:
        st.stop()

# Afficher une éventuelle confirmation de suppression (après login)
_render_delete_confirmation()

# =====================
# Interface principale
# =====================
if st.button("🔄 Réinitialiser la conversation"):
    st.session_state.messages = []
    st.rerun()

# Historique
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Zone de saisie + toggle uploader
with st.container():
    col1, col2 = st.columns([20, 1])
    prompt = col1.chat_input("Tape ici ta demande…")
    if col2.button("📎"):
        st.session_state.show_uploader = not st.session_state.show_uploader

# Uploader
fichier = None
if st.session_state.show_uploader:
    with st.expander("Choisir un fichier à analyser (.txt, .pdf, .docx, .csv)", expanded=True):
        fichier = st.file_uploader(
            label="Fichier à analyser",
            type=["txt", "pdf", "docx", "csv"],
            label_visibility="collapsed",
        )

# ==================================
# Traitement du prompt utilisateur
# ==================================
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Étape 1 : NLU mémoire (comprendre toutes les formulations)
    nlu = nlu_memory_intent(prompt)
    if nlu:
        intent = nlu.get("intent")
        cat = (nlu.get("category") or "").strip()
        txt = (nlu.get("text") or "").strip()

        # Normalisation en commande comprise par la brique mémoire
        if intent == "remember" and txt:
            prompt = f"souviens-toi {txt}"
        elif intent == "remember_category" and cat and txt:
            prompt = f"souviens-toi de {cat} : {txt}"
        elif intent == "recall":
            prompt = "rappelle-toi"
        elif intent == "recall_category" and cat:
            prompt = f"rappelle {cat}"
        elif intent == "forget" and txt:
            prompt = f"oublie {txt}"
        elif intent == "import" and txt:
            prompt = f"intègre ceci : {txt}"
        # sinon on garde le prompt tel quel

    # Étape 2 : Délégation à la brique mémoire
    handled, payload = try_handle_memory_command(prompt)
    if handled:
        # Cas 1 : message simple (ex: "🧠 C’est noté...")
        if isinstance(payload, str):
            st.success(payload)
            st.stop()

        # Cas 2 : liste de souvenirs
        elif isinstance(payload, list):
            st.info("🧠 Derniers souvenirs :")
            for s in payload:
                st.write(f"- [{s['date']}] {s['texte']}")
            st.stop()

        # Cas 3 : suppression — poser le payload puis relancer pour afficher les boutons
        elif isinstance(payload, dict) and payload.get("_type") == "confirm_delete":
            st.session_state["pending_delete"] = payload
            st.rerun()  # affiche immédiatement la boîte Oui/Non

    # Étape 3 : Routage général (autres briques)
    reponse = router(prompt)
    if reponse is None:
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt
        reponse = repondre_avec_gpt4(prompt_final)

    # Affichage de la réponse
    st.session_state.messages.append({"role": "assistant", "content": reponse})
    with st.chat_message("assistant"):
        if isinstance(reponse, str) and ("📁" in reponse or "📄" in reponse):
            st.text(reponse)
        else:
            st.markdown(reponse)
