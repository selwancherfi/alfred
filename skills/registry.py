import os
import json
import importlib
from functools import lru_cache

# --- Localisation automatique du manifest ---
_MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "manifest.json")

@lru_cache(maxsize=1)
def _load_manifest():
    """Charge le manifest JSON des briques (une seule fois)."""
    with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@lru_cache(maxsize=None)
def _intent_map():
    """Construit la table intent -> (executor, ui_flag)."""
    m = {}
    for skill in _load_manifest():
        exec_path = skill["executor"]
        ui_intents = set(skill.get("ui_intents", []))
        for intent in skill["intents"]:
            m[intent] = {
                "executor": exec_path,
                "ui": intent in ui_intents,
            }
    return m

def get_executor(intent: str):
    """Retourne (fonction_exécuteur, ui_bool) ou None."""
    info = _intent_map().get(intent)
    if not info:
        return None
    module_name, func_name = info["executor"].rsplit(".", 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, func_name), info["ui"]

def known_intents():
    """Liste tous les intents connus."""
    return list(_intent_map().keys())
