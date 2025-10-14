# llm.py
# Abstraction du modèle LLM (GPT-*), modèle configurable via ENV ou réglage runtime.
# Compatible avec Streamlit/serveur : pas de dépendance à Streamlit dans ce module.

from __future__ import annotations
import os
import json
from typing import List, Dict, Optional, Any

try:
    from openai import OpenAI
except Exception as e:
    raise RuntimeError(
        "Le package officiel OpenAI est requis. Installe :\n"
        "  pip install --upgrade openai\n"
        f"Erreur d'import : {e}"
    )

# Le client lit OPENAI_API_KEY depuis l'environnement (Streamlit Secrets / variables système)
_client = OpenAI()

# Permet un override du modèle au runtime (ex. depuis l'UI)
_RUNTIME_MODEL: Optional[str] = None


def set_runtime_model(model_name: Optional[str]) -> None:
    """
    Définit un modèle prioritaire au runtime (durée de vie du process).
    Utilise None pour revenir au comportement standard (ENV).
    """
    global _RUNTIME_MODEL
    _RUNTIME_MODEL = model_name


def get_model(default: str = "gpt-5") -> str:
    """
    Ordre de priorité :
      1) _RUNTIME_MODEL si défini
      2) ENV OPENAI_MODEL
      3) fallback 'default'
    """
    if _RUNTIME_MODEL:
        return _RUNTIME_MODEL
    return os.getenv("OPENAI_MODEL", default)


def _create_chat_completion(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Appel brut au Chat Completions API, retourne le texte de la première choice.
    Gère le cas d'erreur en renvoyant un message textuel "Erreur LLM : ...".
    """
    try:
        kwargs: Dict[str, Any] = {
            "model": get_model(),
            "messages": messages,
            "temperature": float(temperature),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        if response_format is not None:
            kwargs["response_format"] = response_format

        resp = _client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        return f"Erreur LLM : {e}"


def repondre_simple(
    prompt: str,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    system_msg: Optional[str] = None,
) -> str:
    """
    Appel minimaliste : un prompt utilisateur, avec option system.
    """
    messages: List[Dict[str, str]] = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": prompt})
    return _create_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)


def repondre_avec_context(
    system_msg: str,
    user_msg: str,
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Appel standard avec persona (system) + message utilisateur (user).
    Idéal pour l'injection de souvenirs dans user_msg.
    """
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    return _create_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)


def repondre_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
) -> str:
    """
    Appel générique : tu fournis toi-même la liste de messages [{'role','content'}, ...].
    """
    return _create_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)


def repondre_json(
    system_msg: str,
    user_msg: str,
    temperature: float = 0.0,
    max_tokens: Optional[int] = None,
    strict_json: bool = False,
) -> Any:
    """
    Demande une réponse JSON. Retourne déjà parsé (dict/list) si possible.
    - strict_json=True : force le formatage JSON via response_format=json_object (si supporté).
    """
    response_format = {"type": "json_object"} if strict_json else None
    raw = _create_chat_completion(
        [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )
    # Si l'API renvoie une erreur sous forme de texte, on la retourne telle quelle
    if isinstance(raw, str) and raw.startswith("Erreur LLM :"):
        return raw
    # Sinon, on tente le parse JSON
    try:
        return json.loads(raw)
    except Exception:
        # Parfois le modèle met du texte autour : on renvoie la chaîne brute,
        # l'appelant pourra gérer un strip ou un reparse.
        return raw


__all__ = [
    "set_runtime_model",
    "get_model",
    "repondre_simple",
    "repondre_avec_context",
    "repondre_chat",
    "repondre_json",
]
