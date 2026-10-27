"""Optional interface translation. English is the default and the source text."""

LANGUAGES = {"en": "English", "ru": "Русский"}
_language = "en"


def set_language(code):
    global _language
    _language = code if code in LANGUAGES else "en"


def language():
    return _language


def t(text: str) -> str:
    if _language == "ru":
        from i18n_ru import RU
        return RU.get(text, text)
    return text
