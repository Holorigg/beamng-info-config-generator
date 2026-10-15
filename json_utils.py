"""String-safe JSON/JSON5 reading for BeamNG mod files."""
import json
import re
from pathlib import Path

import pyjson5

# Tokenize strings and comments first: repairs never touch their contents.
_TOKENS = re.compile(
    r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|//[^\n]*|/\*[\s\S]*?\*/'
    r'|[A-Za-z_$][\w$]*|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[^\s]',
    re.MULTILINE,
)


def _repair_missing_commas(text):
    tokens = [m for m in _TOKENS.finditer(text) if not m.group().startswith(("//", "/*"))]
    insertions = []
    for i in range(1, len(tokens) - 1):
        previous, current, following = tokens[i - 1:i + 2]
        value = previous.group()
        ends_value = value[0] in "\"'" or value in ("}", "]", "true", "false", "null") or value[0] in "-0123456789"
        if (ends_value and following.group() == ":" and
                "\n" in text[previous.end():current.start()]):
            insertions.append(previous.end())
    for position in reversed(insertions):
        text = text[:position] + "," + text[position:]
    return text


def loads(text: str) -> dict:
    text = text.lstrip("\ufeff")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        try:
            value = pyjson5.decode(text)
        except pyjson5.Json5DecoderException:
            try:
                value = pyjson5.decode(_repair_missing_commas(text))
            except pyjson5.Json5DecoderException as exc:
                raise ValueError(str(exc)) from exc
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object at the root")
    return value


def decode(raw: bytes) -> str:
    """Decode bytes to string: UTF-8-sig first, cp1251 fallback."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1251", errors="replace")


def load_bytes(raw: bytes) -> dict:
    """Decode bytes then parse tolerantly."""
    return loads(decode(raw))


def load_file(path) -> dict:
    """Read a file from disk and parse tolerantly."""
    return load_bytes(Path(path).read_bytes())
