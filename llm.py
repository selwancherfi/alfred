# llm.py — version SAFE (n’envoie jamais 'temperature' ni 'response_format')

from __future__ import annotations
import os, json
from typing import List, Dict, Optional, Any
from openai import OpenAI

_client = OpenAI()
_RUNTIME_MODEL: Optional[str] = None

def set_runtime_model(model_name: Optional[str]) -> None:
    global _RUNTIME_MODEL
    _RUNTIME_MODEL = model_name

def get_model(default: str = "gpt-5") -> str:
    return _RUNTIME_MODEL or os.getenv("OPENAI_MODEL", default)

def _create_chat_completion(
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,   # ignoré
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,  # ignoré
) -> str:
    try:
        kwargs: Dict[str, Any] = {"model": get_model(), "messages": messages}
        if max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        # ⚠️ NE PAS envoyer temperature / response_format (GPT-5)
        resp = _client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        return f"Erreur LLM : {e}"

def repondre_simple(prompt: str, temperature: Optional[float] = 0.2, max_tokens: Optional[int] = None, system_msg: Optional[str] = None) -> str:
    msgs = [{"role":"system","content":system_msg}] if system_msg else []
    msgs.append({"role":"user","content":prompt})
    return _create_chat_completion(msgs, temperature=temperature, max_tokens=max_tokens)

def repondre_avec_context(system_msg: str, user_msg: str, temperature: Optional[float] = 0.2, max_tokens: Optional[int] = None) -> str:
    msgs = [{"role":"system","content":system_msg},{"role":"user","content":user_msg}]
    return _create_chat_completion(msgs, temperature=temperature, max_tokens=max_tokens)

def repondre_chat(messages: List[Dict[str,str]], temperature: Optional[float]=0.2, max_tokens: Optional[int]=None) -> str:
    return _create_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)

def repondre_json(system_msg: str, user_msg: str, temperature: Optional[float]=0.0, max_tokens: Optional[int]=None, strict_json: bool=False) -> Any:
    raw = _create_chat_completion(
        [{"role":"system","content":system_msg},{"role":"user","content":user_msg}],
        temperature=temperature, max_tokens=max_tokens
    )
    if isinstance(raw, str) and raw.startswith("Erreur LLM :"):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return raw
