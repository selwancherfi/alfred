# memoire_alfred.py — Mémoire persistante JSON + RAM + logs + commandes
# v2.4 : domaines + règles de classement + importance + feedback + sélection pondérée dédupliquée
import os, io, json, datetime, re, time
from typing import Dict, Any, Optional, Tuple, List, Set
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# --- CONFIG ---
DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive"]
MEMOIRE_FOLDER_ID = "1pJkTfzc4r2WyGFWt4F_32vFpaXpmPb8h"
MEMOIRE_FILENAME = "memoire_persistante.json"
AUTOSAVE_INTERVAL_MIN = 5  # écriture RAM -> Drive toutes les X minutes si nécessaire

# --- Cache interne (RAM) ---
_memory_ram: Optional[Dict[str, Any]] = None
_memory_file_id: Optional[str] = None
_last_autosave_ts: float = 0.0

# ---------- Utilitaires Drive ----------
def _drive_service():
    if "GOOGLE_DRIVE_JSON" in os.environ:
        creds = Credentials.from_service_account_info(
            json.loads(os.environ["GOOGLE_DRIVE_JSON"]), scopes=DRIVE_SCOPE
        )
    else:
        creds = Credentials.from_service_account_file(
            os.environ["GOOGLE_DRIVE_JSON_PATH"], scopes=DRIVE_SCOPE
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
        "schema_version": 2,
        "profil_utilisateur": {"prenom": "Selwan", "langue": "fr", "style_reponse": "clair, précis, ton amical"},
        "parametres": {"projet_actif": None, "mappage_categories": {}, "souvenirs_rules": {}},
        "emplacements": {},
        "projets": {},
        "souvenirs": [],
        "souvenirs_par_categorie": {},   # ex: {"projet":[...]}
        "souvenirs_par_domaine": {}      # ex: {"silky_experience":[...]}
    }
    data = json.dumps(contenu_initial, indent=2, ensure_ascii=False).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/json", resumable=True)
    file_metadata = {"name": MEMOIRE_FILENAME, "parents": [MEMOIRE_FOLDER_ID]}
    newf = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    _memory_file_id = newf["id"]
    return _memory_file_id

# ---------- Migration/normalisation schéma ----------
def _ensure_schema_v2_4(mem: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(mem, dict):
        mem = {}
    mem.setdefault("schema_version", 2)
    mem.setdefault("souvenirs", [])
    mem.setdefault("souvenirs_par_categorie", {})
    mem.setdefault("souvenirs_par_domaine", {})
    param = mem.setdefault("parametres", {})
    param.setdefault("projet_actif", None)
    param.setdefault("mappage_categories", {})  # libre -> catégorie (optionnel, v2.2+)
    param.setdefault("souvenirs_rules", {})     # v2.4 : { "motcle": {"domaine":"...", "categorie":"..."} }
    return mem

# ---------- API mémoire de base ----------
def load_memory() -> Dict[str, Any]:
    global _memory_ram
    service = _drive_service()
    file_id = _ensure_memory_file_id(service)
    content = service.files().get_media(fileId=file_id).execute()
    _memory_ram = json.loads(content.decode("utf-8")) if isinstance(content, (bytes, bytearray)) else json.loads(content)
    _memory_ram = _ensure_schema_v2_4(_memory_ram)
    return _memory_ram

def get_memory() -> Dict[str, Any]:
    global _memory_ram
    if _memory_ram is None:
        return load_memory()
    _memory_ram = _ensure_schema_v2_4(_memory_ram)
    return _memory_ram

def save_memory(data: Optional[Dict[str, Any]] = None) -> None:
    global _memory_ram
    if data is not None:
        _memory_ram = _ensure_schema_v2_4(data)
    if _memory_ram is None:
        return
    service = _drive_service()
    file_id = _ensure_memory_file_id(service)
    body = json.dumps(_memory_ram, indent=2, ensure_ascii=False).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(body), mimetype="application/json", resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()

def log_event(message: str) -> None:
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

def autosave_heartbeat() -> None:
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

# ---------- Helpers ----------
def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _item_key(item: Dict[str, str]) -> str:
    return f"{item.get('date','')}|{item.get('texte','')}"

def _safe_parse_datetime(dt_str: str) -> Optional[datetime.datetime]:
    try:
        return datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None

def _similarity(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

# ---------- Règles de classement (v2.4) ----------
def add_rule(keyword: str, domaine: Optional[str] = None, categorie: Optional[str] = None) -> str:
    kw = (keyword or "").strip().lower()
    if not kw:
        return "Mot-clé vide."
    mem = get_memory()
    rules = mem["parametres"].setdefault("souvenirs_rules", {})
    rules[kw] = {}
    if domaine:   rules[kw]["domaine"] = domaine.strip().lower()
    if categorie: rules[kw]["categorie"] = categorie.strip().lower()
    save_memory(mem)
    return f"Règle ajoutée : « {kw} » -> {rules[kw]}"

def list_rules() -> Dict[str, Dict[str, str]]:
    return get_memory()["parametres"].get("souvenirs_rules", {})

def delete_rule(keyword: str) -> str:
    kw = (keyword or "").strip().lower()
    mem = get_memory()
    rules = mem["parametres"].get("souvenirs_rules", {})
    if kw in rules:
        rules.pop(kw, None)
        save_memory(mem)
        return f"Règle supprimée : « {kw} »."
    return f"Aucune règle pour « {kw} »."

def _apply_rules(texte: str) -> Tuple[Optional[str], Optional[str]]:
    """Retourne (domaine, categorie) si une règle match le texte, sinon (None, None)."""
    t = (texte or "").lower()
    rules = get_memory()["parametres"].get("souvenirs_rules", {})
    for kw, spec in (rules or {}).items():
        if kw and kw in t:
            return spec.get("domaine"), spec.get("categorie")
    return None, None

# ---------- CRUD souvenirs ----------
def remember_freeform(souvenir: str) -> str:
    """Ajoute un souvenir libre OU le redirige via règle vers domaine/catégorie."""
    texte = (souvenir or "").strip()
    if not texte:
        return "Souvenir vide."
    dom, cat = _apply_rules(texte)
    if dom:
        return remember_in_domain(dom, texte)
    if cat:
        return remember_categorized(cat, texte)
    mem = get_memory()
    mem["souvenirs"].append({"date": _now_str(), "texte": texte, "importance": 0.0, "fb": 0.0})
    save_memory(mem)
    log_event(f"Souvenir ajouté (libre) : {texte}")
    return "🧠 C’est noté, je m’en souviendrai."

def remember_categorized(categorie: str, texte: str) -> str:
    mem = get_memory()
    cat = (categorie or "").strip().lower()
    mem["souvenirs_par_categorie"].setdefault(cat, [])
    mem["souvenirs_par_categorie"][cat].append({"date": _now_str(), "texte": (texte or '').strip(), "importance": 0.0, "fb": 0.0})
    save_memory(mem)
    log_event(f"Souvenir (cat='{cat}') ajouté : {(texte or '').strip()}")
    return f"🧠 C’est noté dans la catégorie **{cat}**."

def remember_in_domain(domaine: str, texte: str) -> str:
    mem = get_memory()
    dom = (domaine or "").strip().lower()
    if not dom:
        return remember_freeform(texte)
    mem["souvenirs_par_domaine"].setdefault(dom, [])
    mem["souvenirs_par_domaine"][dom].append({"date": _now_str(), "texte": (texte or "").strip(), "importance": 0.0, "fb": 0.0})
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

def list_all_domains() -> List[str]:
    return list((get_memory().get("souvenirs_par_domaine", {}) or {}).keys())

def list_all_categories() -> List[str]:
    return list((get_memory().get("souvenirs_par_categorie", {}) or {}).keys())

# ---------- Suppression ciblée ----------
def find_memory_match(text: str):
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

    # catégories
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

# ---------- Importance & Feedback (v2.4) ----------
def set_importance(match_text: str, value: float) -> str:
    """Ajuste importance (0..1) du premier souvenir contenant match_text."""
    try:
        v = max(0.0, min(1.0, float(value)))
    except Exception:
        return "Valeur d'importance invalide."
    mem = get_memory()

    def _set_on_list(lst):
        for it in lst:
            if match_text.lower() in it.get("texte", "").lower():
                it["importance"] = v
                return True
        return False

    if _set_on_list(mem.get("souvenirs", [])):
        save_memory(mem); return f"Importance définie à {v}."
    for lst in mem.get("souvenirs_par_categorie", {}).values():
        if _set_on_list(lst):
            save_memory(mem); return f"Importance définie à {v}."
    for lst in mem.get("souvenirs_par_domaine", {}).values():
        if _set_on_list(lst):
            save_memory(mem); return f"Importance définie à {v}."
    return "Souvenir non trouvé."

def vote_memory_item(match_text: str, up: bool = True) -> str:
    """Ajuste un score de feedback local 'fb' ∈ [-1, 1]."""
    delta = 0.1 if up else -0.1
    mem = get_memory()

    def _vote_on_list(lst):
        for it in lst:
            if match_text.lower() in it.get("texte", "").lower():
                it["fb"] = max(-1.0, min(1.0, float(it.get("fb", 0.0)) + delta))
                return it["fb"]
        return None

    res = _vote_on_list(mem.get("souvenirs", []))
    if res is None:
        for lst in mem.get("souvenirs_par_categorie", {}).values():
            res = _vote_on_list(lst)
            if res is not None: break
    if res is None:
        for lst in mem.get("souvenirs_par_domaine", {}).values():
            res = _vote_on_list(lst)
            if res is not None: break

    if res is None:
        return "Souvenir non trouvé."
    save_memory(mem)
    return f"Feedback appliqué. Score fb={res:.2f}"

# ---------- Dispatcheur de commandes (texte) ----------
def import_memories_bulk(texte: str, categorie: Optional[str] = None) -> str:
    lignes = [l.strip() for l in (texte or "").splitlines() if l.strip()]
    if not lignes:
        return "Le texte à intégrer est vide."
    if categorie:
        for l in lignes: remember_categorized(categorie, l)
        return f"🧠 {len(lignes)} souvenirs ajoutés dans **{categorie}**."
    else:
        for l in lignes: remember_freeform(l)
        return f"🧠 {len(lignes)} souvenirs ajoutés."

def try_handle_memory_command(user_input: str) -> Tuple[bool, Optional[object]]:
    if not user_input: return False, None
    txt = user_input.strip()
    lower = txt.lower()

    # Règle: 'règle: "mot" -> domaine=x [catégorie=y]'
    m = re.match(r'^règle\s*:\s*"(.*?)"\s*->\s*domaine\s*=\s*([a-z0-9_\-]+)(?:\s+catégorie\s*=\s*([a-z0-9_\- ]+))?$', lower, flags=re.IGNORECASE)
    if m:
        kw, dom, cat = m.group(1), m.group(2), m.group(3)
        return True, add_rule(kw, dom, cat)

    if lower.startswith("liste règles"):
        return True, list_rules()

    m = re.match(r'^supprime règle\s*"(.*?)"\s*$', lower, flags=re.IGNORECASE)
    if m:
        return True, delete_rule(m.group(1))

    # Importance : importance: "texte" = 0.8
    m = re.match(r'^importance\s*:\s*"(.*?)"\s*=\s*([0-9]*\.?[0-9]+)\s*$', lower, flags=re.IGNORECASE)
    if m:
        return True, set_importance(m.group(1), float(m.group(2)))

    # Import massif
    if lower.startswith("intègre ceci"):
        parts = re.split(r"intègre ceci\s*[:\-]\s*", txt, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) == 2: return True, import_memories_bulk(parts[1], None)
        return True, "Ajoute le texte après « intègre ceci : »."

    # Ajout catégorisé : "souviens-toi de <cat> : <texte>"
    m = re.match(r"^souviens(?:-toi)?\s+de\s+([a-zA-ZÀ-ÿ0-9_ -]+)\s*:\s*(.+)$", txt, flags=re.IGNORECASE)
    if m:
        return True, remember_categorized(m.group(1).strip(), m.group(2).strip())

    # Ajout libre
    m = re.match(r"^souviens(?:-|\s)?toi\s*(?:que\s*)?(.*)$", txt, flags=re.IGNORECASE)
    if m:
        payload = (m.group(1) or "").strip()
        if not payload: return True, "Que dois-je retenir exactement ?"
        return True, remember_freeform(payload)

    for trig in ["souviens", "note ça", "note ca", "garde en mémoire", "garde cela en mémoire"]:
        if lower.startswith(trig):
            payload = txt[len(trig):].strip()
            if not payload: return True, "Que dois-je retenir exactement ?"
            return True, remember_freeform(payload)

    # Lecture
    for trig in ["rappelle-toi", "rappelle", "liste mes souvenirs", "liste souvenirs"]:
        if lower.startswith(trig):
            mcat = re.match(r"^rappelle\s+([a-zA-ZÀ-ÿ0-9_ -]+)$", lower)
            if mcat and mcat.group(1) not in ["toi"]:
                cat = mcat.group(1)
                items = list_memories_by_category(cat, limit=10)
                if not items: return True, f"Aucun souvenir dans la catégorie **{cat}**."
                return True, items
            items = list_memories(limit=10)
            if not items: return True, "Je n’ai encore aucun souvenir enregistré."
            return True, items

    # Suppression (avec confirmation)
    for trig in ["oublie", "oublies", "efface", "supprime"]:
        if lower.startswith(trig):
            payload_txt = txt[len(trig):].strip()
            if not payload_txt: return True, "Précise ce que je dois oublier (texte à chercher)."
            match = find_memory_match(payload_txt)
            if not match: return True, "Je n’ai trouvé aucun souvenir correspondant."
            return True, match

    return False, None

# ---------- Recherche mémoire — v2.4 (pondérée, filtrable, dédupliquée) ----------
def _detect_domain_from_prompt(prompt: str, mem: Dict[str, Any]) -> Optional[str]:
    p = (prompt or "").strip().lower()
    if not p: return None
    proj = (mem.get("parametres", {}) or {}).get("projet_actif")
    if isinstance(proj, str) and proj.strip():
        return proj.strip().lower()
    for dom in (mem.get("souvenirs_par_domaine", {}) or {}).keys():
        d = (dom or "").strip().lower()
        if d and d in p:
            return d
    return None

def _dedupe_selected(items: List[Dict[str, str]], sim_threshold: float = 0.9) -> List[Dict[str, str]]:
    """Supprime les quasi-doublons par similarité du texte."""
    selected: List[Dict[str, str]] = []
    for cand in items:
        t = cand.get("texte", "")
        keep = True
        for it in selected:
            if _similarity(t.lower(), it.get("texte","").lower()) >= sim_threshold:
                keep = False
                break
        if keep:
            selected.append(cand)
    return selected

def search_contextual_memories(
    prompt: str,
    top_k: int = 5,
    min_ratio: float = 0.25,
    enable_domains: bool = True,
    enable_categories: bool = True,
    allowed_domains: Optional[Set[str]] = None,
    allowed_categories: Optional[Set[str]] = None,
    pins: Optional[Set[str]] = None,
    masks: Optional[Set[str]] = None,
    dynamic_limit: bool = True
) -> List[Dict[str, Any]]:
    """
    score = sim_texte
            + 0.35 * bonus_domaine
            + 0.20 * bonus_categorie
            + 0.15 * recence
            + 0.25 * importance
            + 0.10 * fb
    - Dédoublonnage anti-redondance
    - Filtres par domaines/catégories autorisés
    - Pins forcés / masks exclus
    - Limite dynamique : 3..7 selon longueur prompt (si dynamic_limit=True)
    """
    if not isinstance(prompt, str) or not prompt.strip():
        return []

    q = prompt.lower().strip()
    mem = get_memory()

    # Limite dynamique
    if dynamic_limit:
        L = len(prompt)
        if L < 120: top_k = 3
        elif L < 300: top_k = 5
        else: top_k = 7

    pool: List[Tuple[str, Dict[str, Any], str]] = []  # (source, item, tag)

    # Libres
    for it in mem.get("souvenirs", []) or []:
        if isinstance(it, dict) and it.get("texte"):
            item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "libre"}
            pool.append(("libre", item, ""))

    # Catégories
    cats = mem.get("souvenirs_par_categorie", {}) or {}
    for cat, lst in cats.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "categorie", "categorie": cat}
                if allowed_categories and (cat not in allowed_categories):  # filtre UI
                    continue
                pool.append(("categorie", item, str(cat)))

    # Domaines
    doms = mem.get("souvenirs_par_domaine", {}) or {}
    for dom, lst in doms.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "domaine", "domaine": dom}
                if allowed_domains and (dom not in allowed_domains):  # filtre UI
                    continue
                pool.append(("domaine", item, str(dom)))

    if not pool:
        return []

    # Domaine actif
    active_domain = _detect_domain_from_prompt(q, mem) if enable_domains else None

    now = datetime.datetime.now()
    pins = pins or set()
    masks = masks or set()

    scored: List[Tuple[float, Dict[str, Any]]] = []
    for source, item, tag in pool:
        texte = str(item.get("texte", "")).strip()
        if not texte:
            continue

        key = _item_key(item)
        if key in masks:
            continue

        # 1) similarité
        sim = _similarity(q, texte.lower())
        if sim < min_ratio and key not in pins:
            continue

        # 2) bonus domaine
        bonus_dom = 0.0
        if enable_domains and active_domain and (source == "domaine") and (item.get("domaine","").lower() == active_domain):
            bonus_dom = 1.0

        # 3) bonus catégorie
        bonus_cat = 0.0
        if enable_categories and source == "categorie":
            cat_name = str(item.get("categorie","")).strip().lower()
            if cat_name and cat_name in q:
                bonus_cat = 1.0

        # 4) récence
        rec = 0.0
        dt = _safe_parse_datetime(item.get("date", ""))
        if dt:
            days = (now - dt).days
            if days <= 0: rec = 1.0
            else: rec = max(0.0, 1.0 - min(days, 365) / 365.0)

        # 5) importance + feedback
        imp = float(item.get("importance", 0.0) or 0.0)
        fb  = float(item.get("fb", 0.0) or 0.0)

        score = sim + 0.35*bonus_dom + 0.20*bonus_cat + 0.15*rec + 0.25*imp + 0.10*fb
        # Pin prioritaire
        if key in pins:
            score += 1.5

        item["score"] = round(score, 4)
        item["key"] = key
        scored.append((score, item))

    if not scored:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [it for _, it in scored]

    # Dédoublonnage anti-redondance
    ranked = _dedupe_selected(ranked, sim_threshold=0.90)

    return ranked[:max(1, int(top_k))]
