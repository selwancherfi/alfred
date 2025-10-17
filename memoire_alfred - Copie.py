# memoire_alfred.py — Mémoire persistante JSON + RAM + logs + commandes avec confirmation
# v2.3 : ajout "souvenirs_par_domaine" + recherche contextuelle/pondérée
import os, io, json, datetime, re, time
from typing import Dict, Any, Optional, Tuple, List
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# --- CONFIG ---
DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive"]
MEMOIRE_FOLDER_ID = "1pJkTfzc4r2WyGFWt4F_32vFpaXpmPb8h"
MEMOIRE_FILENAME = "memoire_persistante.json"

# Autosave : écriture RAM -> Drive toutes les X minutes si nécessaire
AUTOSAVE_INTERVAL_MIN = 5  # ajuste librement (2..10 recommandé)

# --- Cache interne (RAM) ---
_memory_ram: Optional[Dict[str, Any]] = None
_memory_file_id: Optional[str] = None
_last_autosave_ts: float = 0.0

# ---------- Utilitaires Drive ----------
def _drive_service():
    if "GOOGLE_DRIVE_JSON" in os.environ:
        creds = Credentials.from_service_account_info(
            json.loads(os.environ["GOOGLE_DRIVE_JSON"]),
            scopes=DRIVE_SCOPE
        )
    else:
        creds = Credentials.from_service_account_file(
            os.environ["GOOGLE_DRIVE_JSON_PATH"],
            scopes=DRIVE_SCOPE
        )
    return build("drive", "v3", credentials=creds)

def _ensure_memory_file_id(service) -> str:
    global _memory_file_id
    if _memory_file_id:
        return _memory_file_id
    res = service.files().list(
        q=f"'{MEMOIRE_FOLDER_ID}' in parents and name='{MEMOIRE_FILENAME}' and trashed=false",
        fields="files(id,name)"
    ).execute()
    files = res.get("files", [])
    if files:
        _memory_file_id = files[0]["id"]
        return _memory_file_id
    # créer si absent (propriété = compte de service)
    contenu_initial = {
        "schema_version": 1,
        "profil_utilisateur": {
            "prenom": "Selwan", "langue": "fr",
            "style_reponse": "clair, précis, ton amical"
        },
        "parametres": {"projet_actif": None},
        "emplacements": {},
        "projets": {},
        "souvenirs": [],
        "souvenirs_par_categorie": {},   # ex: {"projet":[...], "contact":[...]}
        # v2.3 : nouveaux domaines (sera présent après migration au chargement)
        # "souvenirs_par_domaine": {}
    }
    data = json.dumps(contenu_initial, indent=2, ensure_ascii=False).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/json", resumable=True)
    file_metadata = {"name": MEMOIRE_FILENAME, "parents": [MEMOIRE_FOLDER_ID]}
    newf = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    _memory_file_id = newf["id"]
    return _memory_file_id

# ---------- Migration/normalisation schéma ----------
def _ensure_schema_v2_3(mem: Dict[str, Any]) -> Dict[str, Any]:
    """
    Garantit la présence des clés nécessaires à v2.3 sans casser l'existant.
    - Ajoute souvenirs_par_domaine si absent
    - Met à jour schema_version >= 2
    """
    if not isinstance(mem, dict):
        mem = {}
    mem.setdefault("souvenirs", [])
    mem.setdefault("souvenirs_par_categorie", {})
    mem.setdefault("parametres", {"projet_actif": None})
    # Nouvelle clé v2.3
    mem.setdefault("souvenirs_par_domaine", {})
    # Bump de version non intrusif
    try:
        sv = int(mem.get("schema_version", 1))
    except Exception:
        sv = 1
    if sv < 2:
        mem["schema_version"] = 2
    return mem

# ---------- API mémoire de base ----------
def load_memory() -> Dict[str, Any]:
    """Charge la mémoire persistante depuis Drive et la garde en RAM (avec normalisation schéma)."""
    global _memory_ram
    service = _drive_service()
    file_id = _ensure_memory_file_id(service)
    content = service.files().get_media(fileId=file_id).execute()
    _memory_ram = json.loads(content.decode("utf-8")) if isinstance(content, (bytes, bytearray)) else json.loads(content)
    _memory_ram = _ensure_schema_v2_3(_memory_ram)
    return _memory_ram

def get_memory() -> Dict[str, Any]:
    global _memory_ram
    if _memory_ram is None:
        return load_memory()
    # garde le cache normalisé
    _ensure_schema_v2_3(_memory_ram)
    return _memory_ram

def save_memory(data: Optional[Dict[str, Any]] = None) -> None:
    """Sauvegarde immédiate RAM -> JSON Drive (synchronisation complète)."""
    global _memory_ram
    if data is not None:
        _memory_ram = _ensure_schema_v2_3(data)
    if _memory_ram is None:
        return
    service = _drive_service()
    file_id = _ensure_memory_file_id(service)
    body = json.dumps(_memory_ram, indent=2, ensure_ascii=False).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(body), mimetype="application/json", resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()

def log_event(message: str) -> None:
    """Append d’une ligne horodatée dans un log quotidien (créé si absent)."""
    try:
        service = _drive_service()
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        log_name = f"{day}.log"
        res = service.files().list(
            q=f"'{MEMOIRE_FOLDER_ID}' in parents and name='{log_name}' and trashed=false",
            fields="files(id,name)"
        ).execute()
        files = res.get("files", [])
        line = f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
        if files:
            log_id = files[0]["id"]
            existing = service.files().get_media(fileId=log_id).execute()
            if isinstance(existing, (bytes, bytearray)):
                existing = existing.decode("utf-8", errors="ignore")
            new_body = (existing or "") + line
            media = MediaIoBaseUpload(io.BytesIO(new_body.encode("utf-8")), mimetype="text/plain", resumable=True)
            service.files().update(fileId=log_id, media_body=media).execute()
        else:
            media = MediaIoBaseUpload(io.BytesIO(line.encode("utf-8")), mimetype="text/plain", resumable=True)
            meta = {"name": log_name, "parents": [MEMOIRE_FOLDER_ID]}
            service.files().create(body=meta, media_body=media, fields="id").execute()
    except HttpError as e:
        print("Log error:", e)

# ---------- Autosave (heartbeat déclenché par l’app) ----------
def autosave_heartbeat() -> None:
    """
    À appeler périodiquement (ex : à chaque run Streamlit).
    Si AUTOSAVE_INTERVAL_MIN est écoulé, force une écriture RAM -> Drive.
    """
    global _last_autosave_ts
    now = time.time()
    if (now - _last_autosave_ts) >= AUTOSAVE_INTERVAL_MIN * 60:
        if _memory_ram is not None:
            try:
                save_memory(_memory_ram)
                log_event("Autosave périodique effectué.")
            except Exception as e:
                print("Autosave error:", e)
        _last_autosave_ts = now

# ---------- Commandes mémoire ----------
def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def remember_freeform(souvenir: str) -> str:
    mem = get_memory()
    mem["souvenirs"].append({"date": _now_str(), "texte": (souvenir or "").strip()})
    save_memory(mem)
    log_event(f"Souvenir ajouté : {(souvenir or '').strip()}")
    return "🧠 C’est noté, je m’en souviendrai."

def remember_categorized(categorie: str, texte: str) -> str:
    """Ajoute un souvenir dans une catégorie (ex: 'projet', 'contact')."""
    mem = get_memory()
    cat = (categorie or "").strip().lower()
    mem["souvenirs_par_categorie"].setdefault(cat, [])
    mem["souvenirs_par_categorie"][cat].append({"date": _now_str(), "texte": (texte or '').strip()})
    save_memory(mem)
    log_event(f"Souvenir (cat='{cat}') ajouté : {(texte or '').strip()}")
    return f"🧠 C’est noté dans la catégorie **{cat}**."

# v2.3 : souvenirs par domaine
def remember_in_domain(domaine: str, texte: str) -> str:
    """Ajoute un souvenir dans un domaine (ex: 'silky_experience', 'urbsex', 'alfred')."""
    mem = get_memory()
    dom = (domaine or "").strip().lower()
    if not dom:
        return remember_freeform(texte)
    mem.setdefault("souvenirs_par_domaine", {})
    mem["souvenirs_par_domaine"].setdefault(dom, [])
    mem["souvenirs_par_domaine"][dom].append({"date": _now_str(), "texte": (texte or "").strip()})
    save_memory(mem)
    log_event(f"Souvenir (domaine='{dom}') ajouté : {(texte or '').strip()}")
    return f"🧠 C’est noté dans le domaine **{dom}**."

def list_memories(limit: int = 10) -> List[Dict[str, str]]:
    items = get_memory().get("souvenirs", [])
    return items[-limit:] if items else []

def list_memories_by_category(categorie: str, limit: int = 10) -> List[Dict[str, str]]:
    mem = get_memory()
    cat = (categorie or "").strip().lower()
    items = mem.get("souvenirs_par_categorie", {}).get(cat, [])
    return items[-limit:] if items else []

def list_memories_by_domain(domaine: str, limit: int = 10) -> List[Dict[str, str]]:
    mem = get_memory()
    dom = (domaine or "").strip().lower()
    items = mem.get("souvenirs_par_domaine", {}).get(dom, [])
    return items[-limit:] if items else []

# ----- Recherche et confirmation de suppression -----
def find_memory_match(text: str):
    """
    Retourne un payload décrivant le 1er souvenir qui contient 'text' (case-insensitive),
    soit dans 'souvenirs' (libres), soit dans une catégorie, soit dans un domaine.
    Format:
      {"_type":"confirm_delete","location":"souvenirs","index":i,"item":{...}}
      {"_type":"confirm_delete","location":"categorie","category":"projet","index":i,"item":{...}}
      {"_type":"confirm_delete","location":"domaine","domain":"silky_experience","index":i,"item":{...}}
    """
    s = (text or "").strip()
    if not s:
        return None
    s_low = s.lower()
    mem = get_memory()

    # libres
    arr = mem.get("souvenirs", [])
    for i, it in enumerate(arr):
        if s_low in (it.get("texte", "").lower()):
            return {"_type": "confirm_delete", "location": "souvenirs", "index": i, "item": it}

    # catégorisés
    cats = mem.get("souvenirs_par_categorie", {})
    for cat, lst in cats.items():
        for i, it in enumerate(lst):
            if s_low in (it.get("texte", "").lower()):
                return {"_type": "confirm_delete", "location": "categorie", "category": cat, "index": i, "item": it}

    # domaines
    doms = mem.get("souvenirs_par_domaine", {})
    for dom, lst in doms.items():
        for i, it in enumerate(lst):
            if s_low in (it.get("texte", "").lower()):
                return {"_type": "confirm_delete", "location": "domaine", "domain": dom, "index": i, "item": it}

    return None

def confirm_delete(payload: dict) -> str:
    """Effectue la suppression à partir du payload retourné par find_memory_match()."""
    mem = get_memory()
    if not payload or payload.get("_type") != "confirm_delete":
        return "Aucune suppression effectuée."

    if payload["location"] == "souvenirs":
        arr = mem.get("souvenirs", [])
        if 0 <= payload["index"] < len(arr):
            removed = arr.pop(payload["index"])
            save_memory(mem)
            log_event(f"Souvenir supprimé: {removed.get('texte','')}")
            return "🧽 Souvenir effacé."
        return "Le souvenir n’existe plus."

    if payload["location"] == "categorie":
        cat = payload.get("category")
        lst = mem.get("souvenirs_par_categorie", {}).get(cat, [])
        if 0 <= payload["index"] < len(lst):
            removed = lst.pop(payload["index"])
            save_memory(mem)
            log_event(f"Souvenir supprimé (cat={cat}): {removed.get('texte','')}")
            return f"🧽 Souvenir effacé dans la catégorie **{cat}**."
        return "Le souvenir n’existe plus."

    if payload["location"] == "domaine":
        dom = payload.get("domain")
        lst = mem.get("souvenirs_par_domaine", {}).get(dom, [])
        if 0 <= payload["index"] < len(lst):
            removed = lst.pop(payload["index"])
            save_memory(mem)
            log_event(f"Souvenir supprimé (domaine={dom}): {removed.get('texte','')}")
            return f"🧽 Souvenir effacé dans le domaine **{dom}**."
        return "Le souvenir n’existe plus."

    return "Aucune suppression effectuée."

def import_memories_bulk(texte: str, categorie: Optional[str] = None) -> str:
    """
    Importe plusieurs lignes en souvenirs.
    - Si 'categorie' est fournie -> enregistre dans cette catégorie.
    - Sinon -> souvenirs libres.
    Séparateur: retour à la ligne (ignore lignes vides).
    """
    lignes = [l.strip() for l in (texte or "").splitlines() if l.strip()]
    if not lignes:
        return "Le texte à intégrer est vide."
    if categorie:
        for l in lignes:
            remember_categorized(categorie, l)
        return f"🧠 {len(lignes)} souvenirs ajoutés dans **{categorie}**."
    else:
        for l in lignes:
            remember_freeform(l)
        return f"🧠 {len(lignes)} souvenirs ajoutés."

# ---------- Dispatcheur de commandes ----------
def try_handle_memory_command(user_input: str) -> Tuple[bool, Optional[object]]:
    """
    Détecte et exécute :
      - Ajout libre (variantes): "souviens-toi", "souviens", "note ça", "garde en mémoire"
      - Ajout catégorisé: "souviens(-toi)? de <categorie> : <texte>"
      - Lecture (variantes): "rappelle-toi", "rappelle", "liste souvenirs", "rappelle <categorie>"
      - Suppression par texte (avec confirmation): "oublie/efface/supprime <texte>"
      - Import en vrac: "intègre ceci : <lignes>"
      - v2.3 (optionnel via UI plus tard) : domaines
    """
    if not user_input:
        return False, None

    txt = user_input.strip()
    lower = txt.lower()

    # Import massif : "intègre ceci : ..."
    if lower.startswith("intègre ceci"):
        parts = re.split(r"intègre ceci\s*[:\-]\s*", txt, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) == 2:
            res = import_memories_bulk(parts[1], None)
            return True, res
        return True, "Ajoute le texte après « intègre ceci : »."

    # Ajout catégorisé : "souviens(-toi)? de <cat> : <texte>"
    m = re.match(r"^souviens(?:-toi)?\s+de\s+([a-zA-ZÀ-ÿ0-9_ -]+)\s*:\s*(.+)$", txt, flags=re.IGNORECASE)
    if m:
        cat = m.group(1).strip()
        payload = m.group(2).strip()
        msg = remember_categorized(cat, payload)
        return True, msg

    # Ajout libre — capture d'abord les variantes de "souviens-toi / souviens toi / souvenstoi"
    m = re.match(r"^souviens(?:-|\s)?toi\s*(?:que\s*)?(.*)$", txt, flags=re.IGNORECASE)
    if m:
        payload = (m.group(1) or "").strip()
        if not payload:
            return True, "Que dois-je retenir exactement ?"
        msg = remember_freeform(payload)
        return True, msg

    # Autres variantes d'ajout libre
    for trig in ["souviens", "note ça", "note ca", "garde en mémoire", "garde cela en mémoire"]:
        if lower.startswith(trig):
            payload = txt[len(trig):].strip()
            if not payload:
                return True, "Que dois-je retenir exactement ?"
            msg = remember_freeform(payload)
            return True, msg

    # Lecture (variantes)
    for trig in ["rappelle-toi", "rappelle", "liste mes souvenirs", "liste souvenirs"]:
        if lower.startswith(trig):
            # "rappelle projet" -> catégorie
            mcat = re.match(r"^rappelle\s+([a-zA-ZÀ-ÿ0-9_ -]+)$", lower)
            if mcat and mcat.group(1) not in ["toi"]:
                cat = mcat.group(1)
                items = list_memories_by_category(cat, limit=10)
                if not items:
                    return True, f"Aucun souvenir dans la catégorie **{cat}**."
                return True, items
            items = list_memories(limit=10)
            if not items:
                return True, "Je n’ai encore aucun souvenir enregistré."
            return True, items

    # Suppression (uniquement par texte + confirmation UI)
    for trig in ["oublie", "oublies", "efface", "supprime"]:
        if lower.startswith(trig):
            payload_txt = txt[len(trig):].strip()
            if not payload_txt:
                return True, "Précise ce que je dois oublier (texte à chercher)."
            match = find_memory_match(payload_txt)
            if not match:
                return True, "Je n’ai trouvé aucun souvenir correspondant."
            # renvoie un payload spécial : l’UI demandera confirmation
            return True, match

    return False, None

# ---------- Recherche mémoire : v2.2 (simple) ----------
def search_relevant_memories(prompt: str, top_k: int = 5, min_ratio: float = 0.25) -> List[Dict[str, str]]:
    """
    v2.2 — Conservation pour compatibilité : similarité textuelle simple.
    Redirigée vers la v2.3 avec des pondérations neutres (domain/category = 0).
    """
    return search_contextual_memories(prompt, top_k=top_k, min_ratio=min_ratio, enable_domains=False, enable_categories=False)

# ---------- Recherche mémoire : v2.3 (pondérée & contextuelle) ----------
def _safe_parse_datetime(dt_str: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def _similarity(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

def _detect_domain_from_prompt(prompt: str, mem: Dict[str, Any]) -> Optional[str]:
    """
    Détection légère du domaine :
    1) parametres.projet_actif si présent
    2) sinon, match du nom de domaine dans le prompt
    """
    p = (prompt or "").strip().lower()
    if not p:
        return None
    # 1) projet actif
    try:
        proj = (mem.get("parametres", {}) or {}).get("projet_actif")
        if isinstance(proj, str) and proj.strip():
            return proj.strip().lower()
    except Exception:
        pass
    # 2) domaine mentionné dans le prompt
    for dom in (mem.get("souvenirs_par_domaine", {}) or {}).keys():
        d = (dom or "").strip().lower()
        if d and d in p:
            return d
    return None

def search_contextual_memories(
    prompt: str,
    top_k: int = 5,
    min_ratio: float = 0.25,
    enable_domains: bool = True,
    enable_categories: bool = True
) -> List[Dict[str, str]]:
    """
    v2.3 — Retourne 3 à 5 souvenirs pondérés :
    score = sim_texte
            + 0.35 * bonus_domaine
            + 0.20 * bonus_categorie
            + 0.15 * score_recence
    - sim_texte: similarité difflib (0..1)
    - bonus_domaine: 1 si le souvenir vient du domaine détecté/actif
    - bonus_categorie: 1 si la clé de catégorie est mentionnée dans le prompt
    - score_recence: clampé [0..1] sur 365 jours ( > 1 an => ~0 )
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return []

    q = prompt.lower()
    mem = get_memory()
    pool: List[Tuple[str, Dict[str, str], str]] = []  # (source, item, tag) => tag=categorie|domaine|libre

    # Souvenirs libres
    for it in mem.get("souvenirs", []) or []:
        if isinstance(it, dict) and it.get("texte"):
            pool.append(("libre", {"date": it.get("date", ""), "texte": it.get("texte", "")}, ""))

    # Souvenirs catégorisés
    cats = mem.get("souvenirs_par_categorie", {}) or {}
    for cat, lst in cats.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                pool.append(("categorie", {"date": it.get("date", ""), "texte": it.get("texte", ""), "categorie": cat}, str(cat)))

    # Souvenirs par domaine (nouveau)
    doms = mem.get("souvenirs_par_domaine", {}) or {}
    for dom, lst in doms.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                pool.append(("domaine", {"date": it.get("date", ""), "texte": it.get("texte", ""), "domaine": dom}, str(dom)))

    if not pool:
        return []

    # Détection du domaine "actif" (projet_actif ou mention explicite)
    active_domain = _detect_domain_from_prompt(q, mem) if enable_domains else None

    # Pré-calculs
    now = datetime.datetime.now()

    scored: List[Tuple[float, Dict[str, str]]] = []
    for source, item, tag in pool:
        texte = str(item.get("texte", "")).strip()
        if not texte:
            continue

        # 1) similarité texte
        sim = _similarity(q, texte.lower())
        if sim < min_ratio:
            continue

        # 2) bonus domaine
        bonus_dom = 0.0
        if enable_domains and active_domain:
            if (source == "domaine") and (item.get("domaine", "").lower() == active_domain):
                bonus_dom = 1.0

        # 3) bonus catégorie (si le nom de catégorie est évoqué dans le prompt)
        bonus_cat = 0.0
        if enable_categories and source == "categorie":
            cat_name = str(item.get("categorie", "")).strip().lower()
            if cat_name and cat_name in q:
                bonus_cat = 1.0

        # 4) récence (0..1, clampée sur 365 jours)
        recence = 0.0
        dt = _safe_parse_datetime(item.get("date", ""))
        if dt:
            days = (now - dt).days
            if days <= 0:
                recence = 1.0
            else:
                recence = max(0.0, 1.0 - min(days, 365) / 365.0)

        # Score pondéré
        score = (
            sim
            + 0.35 * bonus_dom
            + 0.20 * bonus_cat
            + 0.15 * recence
        )
        scored.append((score, item))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    return [it for _, it in scored[:max(1, int(top_k))]]
