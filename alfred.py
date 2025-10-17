import os
import streamlit as st
from router import router, nlu_memory_intent
from lecturefichiersbase import lire_fichier
from llm import repondre_simple, set_runtime_model, get_model

# --- DOIT ÊTRE APPELÉ EN PREMIER ---
st.set_page_config(page_title="Alfred v2.4", page_icon="🤖", layout="wide")

# ========== 🔒 Gate par mot de passe ==========
def _get_password():
    env_pw = os.getenv("APP_PASSWORD") or os.getenv("ALFRED_PASSWORD")
    if env_pw:
        return env_pw
    try:
        return st.secrets.get("APP_PASSWORD", st.secrets.get("ALFRED_PASSWORD", ""))
    except Exception:
        return ""

APP_PASSWORD = _get_password()

if st.session_state.get("_pwd_ok"):
    with st.sidebar:
        if st.button("Se déconnecter"):
            st.session_state["_pwd_ok"] = False
            st.rerun()

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
# ===============================================================

# En-tête
st.title("🤖 Alfred — version 2.4 (pilotage mémoire)")
st.caption(f"✅ App prête — modèle actif : **{get_model()}**")

# Mémoire
from memoire_alfred import (
    get_memory,
    log_event,
    try_handle_memory_command,
    autosave_heartbeat,
    confirm_delete,
    search_contextual_memories,
    list_all_domains,
    list_all_categories,
    vote_memory_item,
)

# Sidebar : modèle
with st.sidebar:
    st.markdown("### Modèle LLM")
    model_choice = st.selectbox(
        "Sélection du modèle",
        options=["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"],
        index=0,
        help="Change à chaud le modèle de raisonnement",
    )
    set_runtime_model(model_choice)

# --- State init (UI mémoire) ---
if "v24_allowed_domains" not in st.session_state:
    st.session_state["v24_allowed_domains"] = set()   # vide = tout autorisé (sera rempli après)
if "v24_allowed_categories" not in st.session_state:
    st.session_state["v24_allowed_categories"] = set()
if "v24_pins" not in st.session_state:
    st.session_state["v24_pins"] = set()              # clés item à forcer
if "v24_masks" not in st.session_state:
    st.session_state["v24_masks"] = set()             # clés item à exclure
if "v24_feedback_pending" not in st.session_state:
    st.session_state["v24_feedback_pending"] = []     # liste (texte, up/down)

# Boîte confirmation suppression
def _render_delete_confirmation():
    payload = st.session_state.get("pending_delete")
    if not payload or payload.get("_type") != "confirm_delete":
        return
    item = payload.get("item", {}) or {}
    texte = item.get("texte", "")
    loc = payload.get("location")
    cat = payload.get("category")
    dom = payload.get("domain")

    msg = f"Confirmer la suppression du souvenir :\n\n> **{texte}**"
    if loc == "categorie" and cat:
        msg += f"\n\n(Catégorie : **{cat}**)"
    if loc == "domaine" and dom:
        msg += f"\n\n(Domaine : **{dom}**)"

    st.warning(msg)
    c1, c2 = st.columns(2)
    if c1.button("✅ Oui, supprimer"):
        res = confirm_delete(payload)
        st.success(res)
        st.session_state["pending_delete"] = None
    if c2.button("❌ Annuler"):
        st.info("Suppression annulée.")
        st.session_state["pending_delete"] = None

# ---------- Sidebar Mémoire Active ----------
def _sidebar_memory_controls():
    st.sidebar.markdown("### 🧠 Mémoire active")

    # Domaines
    domains = list_all_domains()
    if domains:
        st.sidebar.caption("Domaines autorisés")
        current_allowed = set(st.session_state["v24_allowed_domains"]) or set(domains)  # par défaut tout
        new_allowed = set()
        for d in domains:
            chk = st.sidebar.checkbox(f"{d}", value=(d in current_allowed), key=f"dom_{d}")
            if chk: new_allowed.add(d)
        st.session_state["v24_allowed_domains"] = new_allowed

    # Catégories
    cats = list_all_categories()
    if cats:
        st.sidebar.caption("Catégories autorisées")
        current_allowed_c = set(st.session_state["v24_allowed_categories"]) or set(cats)
        new_allowed_c = set()
        for c in cats:
            chk = st.sidebar.checkbox(f"{c}", value=(c in current_allowed_c), key=f"cat_{c}")
            if chk: new_allowed_c.add(c)
        st.session_state["v24_allowed_categories"] = new_allowed_c

    # Épingles / Masques (info)
    if st.session_state["v24_pins"]:
        st.sidebar.write("📌 Épinglés pour la prochaine réponse :", len(st.session_state["v24_pins"]))
    if st.session_state["v24_masks"]:
        st.sidebar.write("🙈 Masqués pour la prochaine réponse :", len(st.session_state["v24_masks"]))

# Corps
autosave_heartbeat()
_sidebar_memory_controls()

if "messages" not in st.session_state:
    st.session_state.messages = []

# Historique
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Widgets
fichier = st.file_uploader("📎 Joindre un fichier (optionnel)", type=None)
prompt = st.chat_input("Parle à Alfred…")

_render_delete_confirmation()

# ===================== 🔍 TRAITEMENT DU PROMPT =====================
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 1) Commandes mémoire explicites
    handled, payload = try_handle_memory_command(prompt)
    if handled:
        if isinstance(payload, str):
            st.success(payload); st.stop()
        if isinstance(payload, list):
            if not payload:
                st.info("Aucun souvenir correspondant."); st.stop()
            st.markdown("### 🧠 Souvenirs")
            for s in payload:
                st.write(f"- [{s.get('date','?')}] {s.get('texte','')}")
            st.stop()
        if isinstance(payload, dict) and payload.get("_type") == "confirm_delete":
            st.session_state["pending_delete"] = payload
            st.rerun()

    # 2) Sélection mémoire (pondérée, filtrée, pins/masques)
    allowed_domains = set(st.session_state["v24_allowed_domains"]) or None
    allowed_categories = set(st.session_state["v24_allowed_categories"]) or None
    pins = set(st.session_state["v24_pins"])
    masks = set(st.session_state["v24_masks"])

    context_memories = search_contextual_memories(
        prompt,
        top_k=5,
        allowed_domains=allowed_domains,
        allowed_categories=allowed_categories,
        pins=pins,
        masks=masks,
        dynamic_limit=True
    )

    # 3) UI : affichage & actions sur souvenirs utilisés
    contextual_text = ""
    if context_memories:
        st.sidebar.markdown("### 🧠 Souvenirs sélectionnés")
        for i, m in enumerate(context_memories, 1):
            src = m.get("source","libre")
            label_extra = f" · cat:{m.get('categorie')}" if src=="categorie" else (f" · dom:{m.get('domaine')}" if src=="domaine" else "")
            st.sidebar.write(f"**{i}.** {m.get('texte','')}")
            st.sidebar.caption(f"score={m.get('score',0):.2f} · {src}{label_extra}")
            cols = st.sidebar.columns(4)
            # 📌 Pin
            if cols[0].button("📌", key=f"pin_{m['key']}"):
                st.session_state["v24_pins"].add(m["key"])
                st.experimental_rerun()
            # 🙈 Mask
            if cols[1].button("🙈", key=f"mask_{m['key']}"):
                st.session_state["v24_masks"].add(m["key"])
                st.experimental_rerun()
            # 👍
            if cols[2].button("👍", key=f"up_{m['key']}"):
                vote_memory_item(m.get("texte",""), up=True)
            # 👎
            if cols[3].button("👎", key=f"down_{m['key']}"):
                vote_memory_item(m.get("texte",""), up=False)

        contextual_text = "\n".join([f"- {m.get('texte','')}" for m in context_memories if m.get("texte")])
        context_intro = (
            "Voici des éléments de mémoire (pondérés) pour t’aider à raisonner :\n"
            f"{contextual_text}\n\n"
        )
    else:
        context_intro = ""

    # 4) Routeur (outils spécialisés)
    reponse = router(prompt)

    # 5) Fallback LLM — prompt enrichi
    if reponse is None:
        if fichier:
            contenu = lire_fichier(fichier)
            prompt_final = f"{context_intro}{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = f"{context_intro}{prompt}"
        reponse = repondre_simple(prompt_final, temperature=None)

    # 6) Nettoyage (pins/masques pour prochaine requête uniquement)
    st.session_state["v24_pins"].clear()
    st.session_state["v24_masks"].clear()

    # 7) Affichage réponse
    st.session_state.messages.append({"role": "assistant", "content": reponse})
    with st.chat_message("assistant"):
        st.markdown(reponse)
