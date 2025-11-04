# memoire_alfred.py — Drive-first memory with multi-location lookup (root + "Mémoire Alfred"),
# automatic legacy migration, and full API compatibility with Alfred v2.4+.

from __future__ import annotations
import json, os, re, time, datetime, io
from typing import Dict, Any, Optional, Tuple, List, Set

# ====================== Réglages ======================
LOCAL_MEMORY_FILE = "memoire_persistante.json"
AUTOSAVE_INTERVAL_MIN = 5
MEMORY_DRIVE_NAME = "memoire_persistante.json"
MEMORY_FOLDER_HINT = "Mémoire Alfred"  # sous-dossier historique

# ================== Intégration Drive =================
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_OK = True
except Exception:
    GOOGLE_OK = False

try:
    # Dossier partagé racine (celui que tu appelles “Google Drive” dans Alfred)
    from connexiongoogledrive import FOLDER_ID
except Exception:
    FOLDER_ID = None

DRIVE_SCOPE = ["https://www.googleapis.com/auth/drive"]

def _drive_service():
    if not GOOGLE_OK:
        return None
    try:
        if "GOOGLE_DRIVE_JSON" in os.environ:
            creds = Credentials.from_service_account_info(
                json.loads(os.environ["GOOGLE_DRIVE_JSON"]), scopes=DRIVE_SCOPE
            )
        else:
            creds = Credentials.from_service_account_file(
                os.environ["GOOGLE_DRIVE_JSON_PATH"], scopes=DRIVE_SCOPE
            )
        return build("drive", "v3", credentials=creds)
    except Exception:
        return None

def _drive_find_folder_by_name(service, parent_id: str, name: str) -> Optional[str]:
    """Retourne l'id d'un sous-dossier 'name' sous parent_id (sans créer)."""
    if not service or not parent_id or not name:
        return None
    try:
        res = service.files().list(
            q=(
                f"'{parent_id}' in parents and "
                "mimeType='application/vnd.google-apps.folder' and "
                f"name='{name}' and trashed=false"
            ),
            fields="files(id,name)", pageSize=10
        ).execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None
    except Exception:
        return None

def _drive_list_files_named(service, parent_id: str, name: str) -> List[Dict[str, Any]]:
    """Liste les fichiers portant 'name' directement sous parent_id."""
    if not service or not parent_id or not name:
        return []
    try:
        res = service.files().list(
            q=f"'{parent_id}' in parents and name='{name}' and trashed=false",
            fields="files(id,name,modifiedTime,size,mimeType,parents)", pageSize=10
        ).execute()
        return res.get("files", []) or []
    except Exception:
        return []

def _drive_get_bytes(service, file_id: str) -> Optional[bytes]:
    try:
        data = service.files().get_media(fileId=file_id).execute()
        return data if isinstance(data, (bytes, bytearray)) else str(data).encode("utf-8", "ignore")
    except Exception:
        return None

def _drive_write_json(service, parent_id: str, file_id: Optional[str], obj: Dict[str, Any]) -> bool:
    try:
        body = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(io.BytesIO(body), mimetype="application/json", resumable=True)
        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
        else:
            meta = {"name": MEMORY_DRIVE_NAME, "parents": [parent_id]}
            service.files().create(body=meta, media_body=media, fields="id").execute()
        return True
    except Exception:
        return False

# =============== RAM, Temp, Logs ======================
_memory_ram: Optional[Dict[str, Any]] = None
_last_autosave_ts: float = 0.0

# Memo temporaire partagé (utilisé par router.py pour Drive & confirmations)
memo_temp: Dict[str, Any] = {}

# Conserve l’emplacement sélectionné pour les sauvegardes
_SELECTED_PARENT_ID: Optional[str] = None
_SELECTED_FILE_ID: Optional[str] = None

def _now_str() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def log_event(message: str) -> None:
    try:
        day = datetime.datetime.now().strftime("%Y-%m-%d")
        with open(f"{day}.log", "a", encoding="utf-8") as f:
            f.write(f"[{_now_str()}] {message}\n")
    except Exception:
        pass

# =============== Schéma & migration ===================
def _ensure_schema(mem_any: Optional[Any]) -> Dict[str, Any]:
    """
    Normalise + MIGRE si besoin.
    - Si mem_any est une LISTE (format legacy) => enrobe dans le nouveau schéma.
    - Si mem_any est un DICT => garantit la présence des clés.
    """
    if isinstance(mem_any, list):
        return {
            "schema_version": 2,
            "profil_utilisateur": {},
            "parametres": {"projet_actif": None, "mappage_categories": {}, "souvenirs_rules": {}},
            "souvenirs": list(mem_any),
            "souvenirs_par_categorie": {},
            "souvenirs_par_domaine": {},
        }
    mem = mem_any if isinstance(mem_any, dict) else {}
    mem.setdefault("schema_version", 2)
    mem.setdefault("profil_utilisateur", {})
    mem.setdefault("parametres", {"projet_actif": None, "mappage_categories": {}, "souvenirs_rules": {}})
    mem.setdefault("souvenirs", [])
    mem.setdefault("souvenirs_par_categorie", {})
    mem.setdefault("souvenirs_par_domaine", {})
    return mem

def _count_items(mem: Dict[str, Any]) -> int:
    n = len(mem.get("souvenirs", []) or [])
    for lst in (mem.get("souvenirs_par_categorie", {}) or {}).values():
        n += len(lst or [])
    for lst in (mem.get("souvenirs_par_domaine", {}) or {}).values():
        n += len(lst or [])
    return n

# =============== Local fallback =======================
def _load_local_raw() -> Optional[Any]:
    if not os.path.exists(LOCAL_MEMORY_FILE):
        return None
    try:
        with open(LOCAL_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_local(mem: Dict[str, Any]) -> None:
    with open(LOCAL_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, ensure_ascii=False, indent=2)

# =============== Sélection du bon fichier Drive =======
def _pick_drive_memory() -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]], bool]:
    """
    Retourne (parent_id, file_id, mem_dict, migrated)
    Stratégie :
      - cherche à la racine (FOLDER_ID) + dans le sous-dossier 'Mémoire Alfred' s'il existe
      - lit tous les candidats MEMOIRE_DRIVE_NAME
      - choisit celui avec le PLUS d'entrées (souvenirs) ; égalité => préférer sous-dossier
    """
    service = _drive_service()
    if not service or not FOLDER_ID:
        return None, None, None, False

    # Candidats à la racine
    root_files = _drive_list_files_named(service, FOLDER_ID, MEMORY_DRIVE_NAME)

    # Candidats dans le sous-dossier "Mémoire Alfred" (si présent)
    mem_folder_id = _drive_find_folder_by_name(service, FOLDER_ID, MEMORY_FOLDER_HINT)
    folder_files = _drive_list_files_named(service, mem_folder_id, MEMORY_DRIVE_NAME) if mem_folder_id else []

    candidates: List[Tuple[str, str, Dict[str, Any], bool, bool]] = []
    # (parent_id, file_id, mem_dict, migrated, is_in_hint_folder)

    def _read_and_normalize(parent_id: str, file_meta: Dict[str, Any], is_hint: bool):
        file_id = file_meta.get("id")
        raw_bytes = _drive_get_bytes(service, file_id)
        if raw_bytes is None:
            return
        try:
            raw = json.loads(raw_bytes.decode("utf-8", "ignore"))
        except Exception:
            return
        migrated = isinstance(raw, list)
        mem = _ensure_schema(raw)
        candidates.append((parent_id, file_id, mem, migrated, is_hint))

    for f in root_files:
        _read_and_normalize(FOLDER_ID, f, False)
    if mem_folder_id:
        for f in folder_files:
            _read_and_normalize(mem_folder_id, f, True)

    if not candidates:
        return None, None, None, False

    # Choix : max(nombre d’items), tie-breaker = dans le dossier “Mémoire Alfred”
    candidates.sort(key=lambda t: (_count_items(t[2]), 1 if t[4] else 0), reverse=True)
    parent_id, file_id, mem, migrated, _is_hint = candidates[0]
    return parent_id, file_id, mem, migrated

# =============== API publique =========================
def load_memory() -> Dict[str, Any]:
    """Charge depuis Drive (choix intelligent entre racine et 'Mémoire Alfred'), sinon local."""
    global _memory_ram, _SELECTED_PARENT_ID, _SELECTED_FILE_ID
    migrated = False
    parent_id = file_id = None
    mem = None

    # 1) Drive (meilleur candidat)
    parent_id, file_id, mem, migrated = _pick_drive_memory()

    # 2) Fallback local
    if mem is None:
        raw = _load_local_raw()
        mem = _ensure_schema(raw)

    _memory_ram = mem

    # Si on vient de choisir un fichier Drive, mémoriser pour les prochains save()
    _SELECTED_PARENT_ID = parent_id
    _SELECTED_FILE_ID = file_id

    # Si c'était un legacy (LISTE) ➜ écrire au bon endroit (Drive si sélectionné, sinon local)
    if migrated:
        if _SELECTED_PARENT_ID:
            svc = _drive_service()
            _drive_write_json(svc, _SELECTED_PARENT_ID, _SELECTED_FILE_ID, _memory_ram)
        else:
            _save_local(_memory_ram)
        log_event("Migration mémoire legacy ➜ nouveau schéma effectuée.")

    return _memory_ram

def get_memory() -> Dict[str, Any]:
    global _memory_ram
    if _memory_ram is None:
        return load_memory()
    _memory_ram = _ensure_schema(_memory_ram)
    return _memory_ram

def save_memory(data: Optional[Dict[str, Any]] = None) -> None:
    """Sauvegarde dans l’emplacement sélectionné (Drive si dispo, sinon local)."""
    global _memory_ram, _SELECTED_PARENT_ID, _SELECTED_FILE_ID
    if data is not None:
        _memory_ram = _ensure_schema(data)
    if _memory_ram is None:
        _memory_ram = _ensure_schema({})

    # Si on n’a pas encore choisi (ex. premier save direct), tenter la sélection maintenant
    if _SELECTED_PARENT_ID is None and FOLDER_ID:
        p, f, m, _migr = _pick_drive_memory()
        if p and m:
            _SELECTED_PARENT_ID, _SELECTED_FILE_ID = p, f

    if _SELECTED_PARENT_ID:
        svc = _drive_service()
        ok = _drive_write_json(svc, _SELECTED_PARENT_ID, _SELECTED_FILE_ID, _memory_ram)
        if ok:
            # si on vient de créer, on n'avait pas d'id fichier : on le retrouve
            if not _SELECTED_FILE_ID:
                # relookup pour fixer l'id, évite un second "create"
                files = _drive_list_files_named(svc, _SELECTED_PARENT_ID, MEMORY_DRIVE_NAME)
                if files:
                    _SELECTED_FILE_ID = files[0]["id"]
            return

    # fallback local
    _save_local(_memory_ram)

def autosave_heartbeat() -> None:
    global _last_autosave_ts
    now = time.time()
    if (now - _last_autosave_ts) >= AUTOSAVE_INTERVAL_MIN * 60:
        try:
            save_memory(get_memory())
            log_event("Autosave périodique effectué.")
        except Exception:
            pass
        _last_autosave_ts = now

# ================= CRUD Souvenirs =====================
def _apply_rules(texte: str):
    t = (texte or "").lower()
    rules = get_memory()["parametres"].get("souvenirs_rules", {})
    for kw, spec in (rules or {}).items():
        if kw and kw in t:
            return spec.get("domaine"), spec.get("categorie")
    return None, None

def _now_item(texte: str) -> Dict[str, Any]:
    return {"date": _now_str(), "texte": (texte or "").strip(), "importance": 0.0, "fb": 0.0}

def remember_freeform(souvenir: str) -> str:
    texte = (souvenir or "").strip()
    if not texte:
        return "Souvenir vide."
    dom, cat = _apply_rules(texte)
    if dom:
        return remember_in_domain(dom, texte)
    if cat:
        return remember_categorized(cat, texte)
    mem = get_memory()
    mem["souvenirs"].append(_now_item(texte))
    save_memory(mem); log_event(f"Souvenir ajouté (libre) : {texte}")
    return "🧠 C’est noté, je m’en souviendrai."

def remember_categorized(categorie: str, texte: str) -> str:
    mem = get_memory()
    cat = (categorie or "général").strip().lower()
    mem["souvenirs_par_categorie"].setdefault(cat, [])
    mem["souvenirs_par_categorie"][cat].append(_now_item(texte))
    save_memory(mem); log_event(f"Souvenir (cat='{cat}') ajouté.")
    return f"🧠 C’est noté dans la catégorie **{cat}**."

def remember_in_domain(domaine: str, texte: str) -> str:
    mem = get_memory()
    dom = (domaine or "").strip().lower()
    mem["souvenirs_par_domaine"].setdefault(dom, [])
    mem["souvenirs_par_domaine"][dom].append(_now_item(texte))
    save_memory(mem); log_event(f"Souvenir (domaine='{dom}') ajouté.")
    return f"🧠 C’est noté dans le domaine **{dom}**."

def list_memories(limit: int = 10) -> List[Dict[str, Any]]:
    items = get_memory().get("souvenirs", [])
    return items[-limit:] if items else []

def list_memories_by_category(categorie: str, limit: int = 10) -> List[Dict[str, Any]]:
    cat = (categorie or "").strip().lower()
    items = get_memory().get("souvenirs_par_categorie", {}).get(cat, [])
    return items[-limit:] if items else []

def list_memories_by_domain(domaine: str, limit: int = 10) -> List[Dict[str, Any]]:
    dom = (domaine or "").strip().lower()
    items = get_memory().get("souvenirs_par_domaine", {}).get(dom, [])
    return items[-limit:] if items else []

def list_all_domains() -> List[str]:
    return list((get_memory().get("souvenirs_par_domaine", {}) or {}).keys())

def list_all_categories() -> List[str]:
    return list((get_memory().get("souvenirs_par_categorie", {}) or {}).keys())

def find_memory_match(text: str):
    s = (text or "").strip().lower()
    if not s: return None
    mem = get_memory()
    for i, it in enumerate(mem.get("souvenirs", [])):
        if s in (it.get("texte","").lower()):
            return {"_type":"confirm_delete","location":"souvenirs","index":i,"item":it}
    for cat, lst in (mem.get("souvenirs_par_categorie", {}) or {}).items():
        for i, it in enumerate(lst):
            if s in (it.get("texte","").lower()):
                return {"_type":"confirm_delete","location":"categorie","category":cat,"index":i,"item":it}
    for dom, lst in (mem.get("souvenirs_par_domaine", {}) or {}).items():
        for i, it in enumerate(lst):
            if s in (it.get("texte","").lower()):
                return {"_type":"confirm_delete","location":"domaine","domain":dom,"index":i,"item":it}
    return None

def confirm_delete(payload: dict) -> str:
    mem = get_memory()
    if not payload or payload.get("_type") != "confirm_delete":
        return "Aucune suppression effectuée."
    if payload["location"] == "souvenirs":
        arr = mem.get("souvenirs", [])
        if 0 <= payload["index"] < len(arr):
            removed = arr.pop(payload["index"])
            save_memory(mem); log_event(f"Souvenir supprimé: {removed.get('texte','')}")
            return "🧽 Souvenir effacé."
        return "Le souvenir n’existe plus."
    if payload["location"] == "categorie":
        cat = payload.get("category")
        lst = mem.get("souvenirs_par_categorie", {}).get(cat, [])
        if 0 <= payload["index"] < len(lst):
            removed = lst.pop(payload["index"])
            save_memory(mem); log_event(f"Souvenir supprimé (cat={cat})")
            return f"🧽 Souvenir effacé dans la catégorie **{cat}**."
        return "Le souvenir n’existe plus."
    if payload["location"] == "domaine":
        dom = payload.get("domain")
        lst = mem.get("souvenirs_par_domaine", {}).get(dom, [])
        if 0 <= payload["index"] < len(lst):
            removed = lst.pop(payload["index"])
            save_memory(mem); log_event(f"Souvenir supprimé (domaine={dom})")
            return f"🧽 Souvenir effacé dans le domaine **{dom}**."
        return "Le souvenir n’existe plus."
    return "Aucune suppression effectuée."

def set_importance(match_text: str, value: float) -> str:
    try:
        v = max(0.0, min(1.0, float(value)))
    except Exception:
        return "Valeur d'importance invalide."
    mem = get_memory()
    def _set_on_list(lst):
        for it in lst:
            if match_text.lower() in it.get("texte","").lower():
                it["importance"] = v; return True
        return False
    if _set_on_list(mem.get("souvenirs", [])): save_memory(mem); return f"Importance définie à {v}."
    for lst in mem.get("souvenirs_par_categorie", {}).values():
        if _set_on_list(lst): save_memory(mem); return f"Importance définie à {v}."
    for lst in mem.get("souvenirs_par_domaine", {}).values():
        if _set_on_list(lst): save_memory(mem); return f"Importance définie à {v}."
    return "Souvenir non trouvé."

def vote_memory_item(match_text: str, up: bool = True) -> str:
    delta = 0.1 if up else -0.1
    mem = get_memory()
    def _vote(lst):
        for it in lst:
            if match_text.lower() in it.get("texte","").lower():
                it["fb"] = max(-1.0, min(1.0, float(it.get("fb",0.0)) + delta))
                return it["fb"]
        return None
    res = _vote(mem.get("souvenirs", []))
    if res is None:
        for lst in mem.get("souvenirs_par_categorie", {}).values():
            res = _vote(lst); 
            if res is not None: break
    if res is None:
        for lst in mem.get("souvenirs_par_domaine", {}).values():
            res = _vote(lst); 
            if res is not None: break
    if res is None: return "Souvenir non trouvé."
    save_memory(mem); return f"Feedback appliqué. Score fb={res:.2f}"

def add_rule(keyword: str, domaine: Optional[str] = None, categorie: Optional[str] = None) -> str:
    kw = (keyword or "").strip().lower()
    if not kw: return "Mot-clé vide."
    mem = get_memory()
    rules = mem["parametres"].setdefault("souvenirs_rules", {})
    rules[kw] = {}
    if domaine:   rules[kw]["domaine"] = (domaine or "").strip().lower()
    if categorie: rules[kw]["categorie"] = (categorie or "").strip().lower()
    save_memory(mem)
    return f"Règle ajoutée : « {kw} » -> {rules[kw]}"

def list_rules() -> Dict[str, Dict[str, str]]:
    return get_memory()["parametres"].get("souvenirs_rules", {})

def delete_rule(keyword: str) -> str:
    kw = (keyword or "").strip().lower()
    mem = get_memory()
    rules = mem.get("parametres", {}).get("souvenirs_rules", {})
    if kw in rules:
        rules.pop(kw, None); save_memory(mem); return f"Règle supprimée : « {kw} »."
    return f"Aucune règle pour « {kw} »."

def import_memories_bulk(texte: str, categorie: Optional[str] = None) -> str:
    lignes = [l.strip() for l in (texte or "").splitlines() if l.strip()]
    if not lignes: return "Le texte à intégrer est vide."
    if categorie:
        for l in lignes: remember_categorized(categorie, l)
        return f"🧠 {len(lignes)} souvenirs ajoutés dans **{categorie}**."
    else:
        for l in lignes: remember_freeform(l)
        return f"🧠 {len(lignes)} souvenirs ajoutés."

# =========== Recherche contextuelle (inchangé) =========
def _similarity(a: str, b: str) -> float:
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()

def search_contextual_memories(
    prompt: str, top_k: int = 5, min_ratio: float = 0.25,
    enable_domains: bool = True, enable_categories: bool = True,
    allowed_domains: Optional[Set[str]] = None, allowed_categories: Optional[Set[str]] = None,
    pins: Optional[Set[str]] = None, masks: Optional[Set[str]] = None, dynamic_limit: bool = True
) -> List[Dict[str, Any]]:
    import difflib
    if not isinstance(prompt, str) or not prompt.strip():
        return []
    q = prompt.lower().strip()
    mem = get_memory()
    if dynamic_limit:
        L = len(prompt)
        if L < 120: top_k = 3
        elif L < 300: top_k = 5
        else: top_k = 7

    pool: List[Tuple[str, Dict[str, Any], str]] = []
    for it in mem.get("souvenirs", []) or []:
        if isinstance(it, dict) and it.get("texte"):
            item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "libre"}
            pool.append(("libre", item, ""))
    cats = mem.get("souvenirs_par_categorie", {}) or {}
    for cat, lst in cats.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                if allowed_categories and (cat not in allowed_categories): continue
                item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "categorie", "categorie": cat}
                pool.append(("categorie", item, str(cat)))
    doms = mem.get("souvenirs_par_domaine", {}) or {}
    for dom, lst in doms.items():
        for it in lst or []:
            if isinstance(it, dict) and it.get("texte"):
                if allowed_domains and (dom not in allowed_domains): continue
                item = {"date": it.get("date",""), "texte": it.get("texte",""), "importance": it.get("importance",0.0), "fb": it.get("fb",0.0), "source": "domaine", "domaine": dom}
                pool.append(("domaine", item, str(dom)))

    if not pool:
        return []

    scored: List[Tuple[float, Dict[str, Any]]] = []
    now = datetime.datetime.now()
    for source, item, tag in pool:
        texte = str(item.get("texte", "")).strip()
        if not texte: continue
        sim = difflib.SequenceMatcher(None, q, texte.lower()).ratio()
        if sim < min_ratio: continue
        rec = 0.0
        try:
            dt = datetime.datetime.strptime(item.get("date",""), "%Y-%m-%d %H:%M:%S")
            days = (now - dt).days
            rec = 1.0 if days <= 0 else max(0.0, 1.0 - min(days, 365)/365.0)
        except Exception:
            rec = 0.0
        imp = float(item.get("importance", 0.0) or 0.0)
        fb  = float(item.get("fb", 0.0) or 0.0)
        score = sim + 0.15*rec + 0.25*imp + 0.10*fb
        item["score"] = round(score, 4)
        item["key"] = f"{item.get('date','')}|{texte}"
        scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    ranked = [it for _, it in scored]
    result: List[Dict[str, Any]] = []
    for cand in ranked:
        if not any(_similarity(cand.get("texte",""), x.get("texte","")) >= 0.9 for x in result):
            result.append(cand)
        if len(result) >= top_k:
            break
    return result

# =========== NLU mémoire (pare-feu Drive) =============
def try_handle_memory_command(user_input: str) -> Tuple[bool, Optional[object]]:
    if not user_input:
        return False, None

    txt = user_input.strip()
    lower = txt.lower()

    # Pare-feu : si on parle de Drive / fichiers / dossiers, on laisse le routeur Drive gérer
    if any(t in lower for t in ["drive", "google drive", "dossier", "sous dossier", "sous-dossier", "fichier"]):
        return False, None

    # ---------- RÈGLES ----------
    m = re.match(
        r'^règle\s*:\s*"(.*?)"\s*->\s*domaine\s*=\s*([a-z0-9_\-]+)(?:\s+catégorie\s*=\s*([a-z0-9_\- ]+))?$',
        lower, flags=re.IGNORECASE
    )
    if m:
        return True, add_rule(m.group(1), m.group(2), m.group(3))
    if lower.startswith("liste règles"):
        return True, list_rules()
    m = re.match(r'^supprime règle\s*"(.*?)"\s*$', lower, flags=re.IGNORECASE)
    if m:
        return True, delete_rule(m.group(1))

    # ---------- IMPORTANCE ----------
    m = re.match(r'^importance\s*:\s*"(.*?)"\s*=\s*([0-9]*\.?[0-9]+)\s*$', lower, flags=re.IGNORECASE)
    if m:
        try:
            return True, set_importance(m.group(1), float(m.group(2)))
        except Exception:
            return True, "Valeur d'importance invalide."

    # ---------- IMPORT BULK ----------
    if lower.startswith("intègre ceci"):
        parts = re.split(r"intègre ceci\s*[:\-]\s*", txt, flags=re.IGNORECASE, maxsplit=1)
        if len(parts) == 2:
            return True, import_memories_bulk(parts[1], None)
        return True, "Ajoute le texte après « intègre ceci : »."

    # ---------- AJOUT CATÉGORISÉ ----------
    m = re.match(r"^souviens(?:-toi)?\s+de\s+([a-zA-ZÀ-ÿ0-9_ \-]+)\s*:\s*(.+)$", txt, flags=re.IGNORECASE)
    if m:
        return True, remember_categorized(m.group(1).strip(), m.group(2).strip())

    # ---------- AJOUT FREEFORM ----------
    m = re.match(r"^souviens(?:-|\s)?toi\s*(?:que\s*)?(.*)$", txt, flags=re.IGNORECASE)
    if m:
        payload = (m.group(1) or "").strip()
        if not payload:
            return True, "Que dois-je retenir exactement ?"
        return True, remember_freeform(payload)

    for trig in ["souviens", "note ça", "note ca", "garde en mémoire", "garde cela en mémoire"]:
        if lower.startswith(trig):
            payload = txt[len(trig):].strip()
            if not payload:
                return True, "Que dois-je retenir exactement ?"
            return True, remember_freeform(payload)

    # ---------- LISTES / RAPPEL ----------
    if re.fullmatch(r"\s*rappelle(?:\s|-)?toi\s*", lower):
        return True, list_memories(limit=10)
    if re.fullmatch(r"\s*liste(?:\s+mes)?\s+souvenirs\s*", lower):
        return True, list_memories(limit=10)

    m = re.fullmatch(r"\s*rappelle\s+([a-zA-ZÀ-ÿ0-9_ \-]+)\s*", lower)
    if m and m.group(1).strip() not in {"toi"}:
        return True, list_memories_by_category(m.group(1).strip(), limit=10)

    # ---------- SUPPRESSION (FIX : nettoyage du libellé "souvenir ...") ----------
    if lower.startswith(("oublie", "oublies", "efface", "supprime")):
        # On n'agit que si on parle explicitement de mémoire/souvenir
        if not any(k in lower for k in ["souvenir", "souvenirs", "mémoire", "memoire"]):
            return False, None

        # Récupère le texte après le verbe
        payload_txt = txt.split(" ", 1)[1].strip() if " " in txt else ""
        if not payload_txt:
            return True, "Précise ce que je dois oublier (texte à chercher)."

        # Nettoyage : enlève déterminants + 'souvenir(s)/mémoire' en tête
        # ex. "le souvenir ma grand mère..." -> "ma grand mère..."
        cleaned = payload_txt
        cleaned = re.sub(
            r"\b(le|la|les|un|une)\s+(souvenir|souvenirs|mémoire|memoire)\b",
            r"\2", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(
            r"^(souvenir|souvenirs|mémoire|memoire)\s*[:,-]?\s*",
            "", cleaned, flags=re.IGNORECASE
        )
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

        # 1ère passe : version nettoyée
        match = find_memory_match(cleaned) if cleaned else None
        # 2e passe : version originale (au cas où)
        if not match:
            match = find_memory_match(payload_txt)

        if not match:
            return True, "Je n’ai trouvé aucun souvenir correspondant."

        # Renvoie le payload de confirmation attendu par alfred.py
        return True, match

    # Rien de géré
    return False, None

# ================================================================
# Réponse enrichie par les souvenirs pertinents (API publique)
# ================================================================
def answer_with_memories(user_prompt: str, k: int = 7) -> str:
    """
    Prend le prompt utilisateur, récupère jusqu'à k souvenirs pertinents,
    construit un petit contexte propre, et appelle le LLM.
    - Si aucun souvenir n'est pertinent, on laisse le prompt tel quel.
    - Ne modifie rien d'autre (pas d'écriture mémoire).
    """
    # Import local pour éviter les dépendances circulaires au chargement du module
    try:
        from llm import repondre_simple
    except Exception:
        # Fallback défensif : si jamais l'import échoue, on répond directement
        def repondre_simple(txt, temperature=None):
            return txt

    # Récupère k souvenirs pertinents pour ce prompt
    try:
        mems = search_contextual_memories(user_prompt, k=k)
    except TypeError:
        # compat : certaines versions n'acceptent pas k
        mems = search_contextual_memories(user_prompt)
        if isinstance(mems, list):
            mems = mems[:k]

    # Si pas de souvenirs, répondre normalement
    if not mems:
        return repondre_simple(user_prompt, temperature=None)

    # Mise en forme du contexte mémoire (sobre et robuste)
    lignes = []
    for m in mems:
        if isinstance(m, dict):
            d = m.get("date") or ""
            t = m.get("texte") or ""
            if d:
                lignes.append(f"- [{d}] {t}")
            else:
                lignes.append(f"- {t}")
        else:
            lignes.append(f"- {str(m)}")

    contexte = "\n".join(lignes)

    # Prompt enrichi : on indique au modèle comment utiliser (ou ignorer) le contexte
    prompt_enrichi = (
        "Tu es Alfred. Si c'est pertinent, utilise le contexte mémoire ci-dessous pour répondre ; "
        "sinon, réponds normalement.\n\n"
        "[Contexte — Souvenirs pertinents]\n"
        f"{contexte}\n\n"
        "[Question]\n"
        f"{user_prompt}"
    )

    return repondre_simple(prompt_enrichi, temperature=None)

