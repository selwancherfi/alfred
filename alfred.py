# alfred.py — Interface Streamlit Alfred v2.4 (stable, épuré)
# - Sidebar : compteur + bouton "Gérer les souvenirs"
# - Panneau de gestion des souvenirs
# - Routeur intact (Drive & co)
# - Fallback LLM enrichi par la mémoire
# - Intégration email : délégue tout à gestionemails.py (intention + UI persistante)

import os
import re
import datetime
import streamlit as st

from router import router
from lecturefichiersbase import lire_fichier
from llm import set_runtime_model, get_model

# --- Brique email (UNIQUEMENT les points d’entrée) ---
from gestionemails import (
    email_flow_persist,
    maybe_bootstrap_email,
    is_email_intent,
)

# --- Mémoire ---
from memoire_alfred import (
    list_memories,
    vote_memory_item,
    confirm_delete,
    try_handle_memory_command,
    find_memory_match,
    answer_with_memories,
)

# --------------------------- Config page ---------------------------
st.set_page_config(page_title="Alfred v2.4", page_icon="🤖", layout="wide")

# --------------------------- CSS global ---------------------------
st.markdown(
    """
    <style>
    pre, code, .stMarkdown, .stText, .stAlert, .stChatMessage, .element-container {
        white-space: pre-wrap !important;
        word-wrap: break-word !important;
    }
    .stTextInput textarea, .stChatInputContainer textarea { min-height: 52px !important; }
    .stAlert { border-radius: 10px !important; }
    .mem-list li { margin-bottom: .35rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# --------------------------- Utils ---------------------------
def _push_history(role: str, content: str, subtype: str | None = None):
    st.session_state.setdefault("messages", [])
    st.session_state["messages"].append({
        "role": role,
        "content": content,
        "render": "md",
        "subtype": subtype,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    })

def _get_password():
    env_pw = os.getenv("APP_PASSWORD") or os.getenv("ALFRED_PASSWORD")
    if env_pw:
        return env_pw
    try:
        return st.secrets.get("APP_PASSWORD", st.secrets.get("ALFRED_PASSWORD", ""))
    except Exception:
        return ""

def _render_mem_list(items):
    if not items:
        return "_Aucun souvenir._"
    lines = []
    for it in items:
        if isinstance(it, dict):
            d = it.get("date") or ""
            txt = it.get("texte") or ""
            lines.append(f"- **[{d}]** {txt}" if d else f"- {txt}")
        else:
            lines.append(f"- {str(it)}")
    return "\n".join(lines)

def _preprocess_delete_command(raw: str) -> str | None:
    if not raw:
        return None
    s = raw.strip()
    low = s.lower()
    if low.startswith(("supprime", "oublie", "efface")):
        mentions_memory = any(k in low for k in ["souvenir", "souvenirs", "mémoire", "memoire"])
        verb = low.split()[0]
        cleaned = re.sub(r"\b(le|la|les|un|une)\s+souvenir(s)?\b", "souvenir", low)
        cleaned = re.sub(r"\b(le|la|les|un|une)\s+mémoire\b", "mémoire", cleaned)
        if ("souvenir" not in cleaned) and mentions_memory:
            parts = s.split(" ", 1)
            payload = parts[1] if len(parts) > 1 else ""
            cleaned = f"{verb} souvenir {payload}".strip()
        if not any(k in cleaned for k in ["souvenir", "mémoire", "memoire"]):
            return None
        cleaned = re.sub(r"\b(souvenir|mémoire|memoire)\s+(que|qui|de|du|des)\s+", r"\1 ", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned
    return None

# --------------------------- Auth simple (optionnel) ---------------------------
APP_PASSWORD = _get_password()
if APP_PASSWORD:
    if not st.session_state.get("_pwd_ok"):
        st.title("Alfred v2.4")
        pw = st.text_input("Mot de passe", type="password")
        if pw and pw == APP_PASSWORD:
            st.session_state["_pwd_ok"] = True
            st.rerun()
        st.stop()
    else:
        with st.sidebar:
            if st.button("Se déconnecter"):
                st.session_state["_pwd_ok"] = False
                st.rerun()

# --------------------------- Sidebar (modèle) ---------------------------
with st.sidebar:
    st.header("Modèle LLM")
    current = get_model() or "gpt-5"
    options = ["gpt-5", "gpt-5-mini", "gpt-4.1", "gpt-4o"]
    idx = options.index(current) if current in options else 0
    model_choice = st.selectbox("Sélection du modèle", options=options, index=idx, help="Change à chaud le modèle de raisonnement")
    set_runtime_model(model_choice)

# --------------------------- States divers ---------------------------
st.session_state.setdefault("messages", [])
st.session_state.setdefault("pending_delete", None)
st.session_state.setdefault("manage_memories", False)
st.session_state.setdefault("last_memories_snapshot", [])
st.session_state.setdefault("email_ctx", None)      # Contexte d'envoi email (géré par gestionemails)
st.session_state.setdefault("email_result", None)   # Résultat d'envoi

# --------------------------- Bannière confirmation suppression ---------------------------
def _render_delete_banner():
    payload = st.session_state.get("pending_delete")
    if not payload:
        return
    item_txt = ""
    if isinstance(payload, dict):
        item_txt = payload.get("item", {}).get("texte", "") or payload.get("texte", "")
    item_txt = item_txt or "(souvenir)"
    st.warning(f"⚠️ Tu veux supprimer ce souvenir :\n\n> {item_txt}\n\nConfirmer ?")
    c1, c2 = st.columns(2)
    if c1.button("✅ Confirmer la suppression"):
        msg = confirm_delete(payload)
        st.session_state["pending_delete"] = None
        _push_history("assistant", msg, "success")
        st.rerun()
    if c2.button("↩️ Annuler"):
        st.session_state["pending_delete"] = None
        _push_history("assistant", "Suppression annulée.", "info")
        st.rerun()

# --------------------------- Rendu historique ---------------------------
for m in st.session_state["messages"]:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant":
            content = m["content"]; subtype = m.get("subtype")
            if subtype == "success": st.success(content)
            elif subtype == "info":  st.info(content)
            elif subtype == "warning": st.warning(content)
            elif subtype == "error": st.error(content)
            else: st.markdown(content)
        else:
            st.markdown(m["content"])

# Affiche la bannière si besoin
_render_delete_banner()

# --------------------------- Sidebar Souvenirs ---------------------------
def _mem_count() -> int:
    try:
        items = list_memories(limit=9999)
    except TypeError:
        items = list_memories()
    n = len(items) if isinstance(items, list) else 0
    st.session_state["last_memories_snapshot"] = items if isinstance(items, list) else []
    return n

with st.sidebar:
    n = _mem_count()
    st.markdown(f"### 🧠 Souvenirs ({n})")
    if st.button("Gérer les souvenirs"):
        st.session_state["manage_memories"] = True
        _push_history("assistant", "🔎 J’ouvre le panneau de gestion des souvenirs.", "info")
        st.rerun()

# --------------------------- Panneau gestion souvenirs (zone principale) ---------------------------
def _render_mem_management_panel():
    st.markdown("## 🧠 Gestion des souvenirs")
    items = st.session_state.get("last_memories_snapshot") or []
    if not items:
        try:
            items = list_memories(limit=50)
        except TypeError:
            items = list_memories()
            if isinstance(items, list): items = items[:50]

    if not items:
        st.info("Aucun souvenir pour l’instant.")
        return

    for idx, it in enumerate(items, 1):
        if isinstance(it, dict):
            d = it.get("date") or ""
            txt = it.get("texte") or ""
        else:
            d = ""
            txt = str(it)

        with st.container():
            st.markdown(f"- **[{d}]** {txt}" if d else f"- {txt}", unsafe_allow_html=True)
            c1, c2, c3, _ = st.columns([0.1, 0.1, 0.1, 0.7])
            if c1.button("👍", key=f"m_up_{idx}"):
                vote_memory_item(txt, up=True)
                _push_history("assistant", f"👍 J’ai noté ce souvenir comme pertinent : “{txt}”.", "success")
                st.rerun()
            if c2.button("👎", key=f"m_down_{idx}"):
                vote_memory_item(txt, up=False)
                _push_history("assistant", f"👎 J’ai noté ce souvenir comme peu pertinent : “{txt}”.", "info")
                st.rerun()
            if c3.button("🗑️", key=f"m_del_{idx}"):
                payload = find_memory_match((txt or "").strip())
                if payload:
                    _push_history("assistant", f"⚠️ Tu me demandes d’effacer ce souvenir : “{txt}”.", "warning")
                    st.session_state["pending_delete"] = payload
                    st.rerun()

    st.divider()
    if st.button("Fermer la gestion des souvenirs"):
        st.session_state["manage_memories"] = False
        st.rerun()

# --------------------------- Uploader (optionnel) ---------------------------
with st.container():
    cols = st.columns([1, 3, 1])
    with cols[1]:
        uploaded_file = st.file_uploader("Joindre (optionnel)", type=None, label_visibility="collapsed")

# ======= PERSISTENCE UI EMAIL : déléguée à la brique métier =======
if email_flow_persist(_push_history=_push_history):
    st.stop()

# --------------------------- Prompt utilisateur ---------------------------
prompt = st.chat_input("Parle à Alfred...")

# Affiche le panneau souvenirs si demandé (indépendant de la saisie)
if st.session_state.get("manage_memories"):
    _render_mem_management_panel()

# ========================== LOGIQUE ==========================
if prompt:

    # === DEBUG TEMPORAIRE : voir la vraie valeur reçue online par Streamlit ===
    st.sidebar.caption(f"[debug] prompt={repr(prompt)}")
    st.sidebar.caption(f"[debug] is_email_intent={is_email_intent(prompt)}")
    # ==========================================================================

    # Historique : message utilisateur
    _push_history("user", prompt)
    with st.chat_message("user"):
        st.markdown(prompt)

    # Pré-traitement suppression par texte
    pre = _preprocess_delete_command(prompt)
    prompt_for_memory = pre if (pre and pre != prompt) else prompt

    # Commandes mémoire (NLU)
    result = try_handle_memory_command(prompt_for_memory)
    handled = False; mem_resp = None; mem_subtype = None; pending_payload = None
    if isinstance(result, tuple):
        if   len(result) == 4: handled, mem_resp, mem_subtype, pending_payload = result
        elif len(result) == 3: handled, mem_resp, mem_subtype = result
        elif len(result) == 2: handled, mem_resp = result

    if handled:
        if isinstance(mem_resp, dict) and mem_resp.get("_type") == "confirm_delete":
            txt_preview = mem_resp.get("item", {}).get("texte", "") or mem_resp.get("texte", "")
            _push_history("assistant", f"⚠️ Tu me demandes d’effacer ce souvenir : “{txt_preview}”.", "warning")
            st.session_state["pending_delete"] = mem_resp
            st.rerun()

        if isinstance(mem_resp, list):
            mem_resp = _render_mem_list(mem_resp)
            if mem_subtype is None: mem_subtype = "info"

        if pending_payload:
            txt_preview = pending_payload.get("item", {}).get("texte", "") or pending_payload.get("texte", "")
            _push_history("assistant", f"⚠️ Tu me demandes d’effacer ce souvenir : “{txt_preview}”.", "warning")
            st.session_state["pending_delete"] = pending_payload
            st.rerun()

        _push_history("assistant", mem_resp, mem_subtype or "info")
        with st.chat_message("assistant"):
            if (mem_subtype or "info") == "info": st.info(mem_resp)
            elif mem_subtype == "success":        st.success(mem_resp)
            elif mem_subtype == "warning":        st.warning(mem_resp)
            elif mem_subtype == "error":          st.error(mem_resp)
            else:                                  st.markdown(mem_resp)

    # ------------------- Routeur (email / Drive / mémoire) -------------------
    reponse = None
    routed = router(prompt)

    # Cas spécial : le routeur a bootstrappé l'UI email
    if isinstance(routed, dict) and routed.get("_type") == "ui_email_bootstrapped":
        # maybe_bootstrap_email() a rempli email_ctx ; email_flow_persist() en haut de page
        # va prendre la main après rerun.
        st.rerun()

    # Sinon, si une brique a produit une réponse "texte"
    if routed is not None:
        reponse = routed

    # ------------------- Fallback LLM enrichi par la mémoire -------------------
    if reponse is None:
        if uploaded_file is not None:
            contenu = lire_fichier(uploaded_file)
            prompt_final = f"{prompt}\n\nVoici le contenu du fichier :\n{contenu}"
        else:
            prompt_final = prompt
        text = answer_with_memories(prompt_final, k=7)
        reponse = {"content": text, "subtype": None}


    # ------------------- Affichage final -------------------
    if isinstance(reponse, dict):
        content = reponse.get("content", "")
        subtype = reponse.get("subtype")
    else:
        content = str(reponse); subtype = None

    _push_history("assistant", content, subtype)
    with st.chat_message("assistant"):
        if subtype == "success": st.success(content)
        elif subtype == "info":  st.info(content)
        elif subtype == "warning": st.warning(content)
        elif subtype == "error": st.error(content)
        else: st.markdown(content)
