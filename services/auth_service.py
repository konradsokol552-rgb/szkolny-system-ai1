import hashlib
import os
import streamlit as st
from typing import Optional, Dict, Any

from services.db_service import pobierz_konto, zapisz_konto


def hash_password(password: str) -> str:
    """Haszuje hasło używając bezpiecznego algorytmu PBKDF2 z solą."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return f"pbkdf2:sha256:{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored_password: str) -> bool:
    """Sprawdza poprawność hasła z obsługą starszych kont (jawny tekst) oraz nowo zhaszowanych."""
    if not stored_password:
        return False

    # Sprawdzenie nowego formatu zhaszowanego
    if stored_password.startswith("pbkdf2:sha256:"):
        try:
            _, _, salt_hex, key_hex = stored_password.split(":")
            salt = bytes.fromhex(salt_hex)
            key = bytes.fromhex(key_hex)
            new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
            return new_key == key
        except Exception:
            return False

    # Obsługa wsteczna dla istniejących kont w postaci plain-text
    return password == stored_password


def zaloguj_uzytkownika(id_input: str, haslo_input: str) -> bool:
    """Weryfikuje dane logowania i inicjalizuje stan sesji Streamlit."""
    if not id_input or not haslo_input:
        return False

    dane = pobierz_konto(id_input.strip())
    if not dane:
        return False

    stored_pw = dane.get("haslo", "")
    if not verify_password(haslo_input, stored_pw):
        return False

    # Automatyczna migracja starego hasła z tekstu jawnego na zhaszowane
    if not stored_pw.startswith("pbkdf2:sha256:"):
        dane["haslo"] = hash_password(haslo_input)
        zapisz_konto(id_input.strip(), dane)

    st.session_state.update({
        "zalogowany_id": id_input.strip(),
        "user_api_key": dane.get("user_api_key", ""),
        "role": dane.get("rola", "uczen"),
        "klasa": dane.get("klasa", ""),
        "postep_tematow": dane.get("postep_tematow", {}),
        "historia_czatow": dane.get("historia_czatow", {})
    })
    return True


def stworz_konto(id_input: str, typ: str, klucz_api: str, klasa: str, haslo: str) -> bool:
    """Tworzy nowe konto w systemie z zhaszowanym hasłem."""
    user_id = id_input.strip()
    if not user_id or not haslo or not klucz_api:
        return False

    nowy_profil = {
        "user_api_key": klucz_api.strip(),
        "haslo": hash_password(haslo),
        "postep_tematow": {},
        "historia_czatow": {},
        "rola": typ,
        "klasa": klasa.strip()
    }
    zapisz_konto(user_id, nowy_profil, merge=False)
    return True


def sprawdz_dostep(wymagana_rola: Optional[str] = None) -> None:
    """Strażnik dostępu dla stron. Przekierowuje na app.py w przypadku braku uprawnień."""
    if "zalogowany_id" not in st.session_state or not st.session_state.get("zalogowany_id"):
        st.switch_page("app.py")
        st.stop()

    if wymagana_rola and st.session_state.get("role") != wymagana_rola:
        st.error(f"⛔ Brak uprawnień do przeglądania tej strony! Wymagana rola: {wymagana_rola}")
        st.stop()
