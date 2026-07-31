import random
import time
import requests
import streamlit as st
from typing import List, Dict, Any

from config import SYSTEM_PROMPT


def pobierz_klucz_api() -> str:
    """Pobiera klucz API ze stanu sesji lub globalnych sekretów."""
    api_key = st.session_state.get("user_api_key", "").strip()
    if not api_key and "connections" in st.secrets and "gemini_api_key" in st.secrets["connections"]:
        api_key = st.secrets["connections"]["gemini_api_key"]
    if not api_key and "GEMINI_API_KEY" in st.secrets:
        api_key = st.secrets["GEMINI_API_KEY"]
    return api_key


def zapytaj_ai(
    historia_rozmowy: List[Dict[str, str]],
    temat_kontekst: str,
    licznik_zadan: int,
    custom_system_prompt: str = None
) -> str:
    """
    Wysyła zapytanie do Gemini AI z obsługą kontekstu lekcji, ponawianiem prób przy 429
    oraz wsparciem dla SDK i REST fallback.
    """
    api_key = pobierz_klucz_api()
    if not api_key:
        return "❌ BŁĄD: Brak klucza API Gemini w profilu ani w konfiguracji systemowej!"

    system_prompt = custom_system_prompt or SYSTEM_PROMPT
    ziarno = f"{time.time()}_{random.randint(1000, 9999)}"

    if licznik_zadan == 0 and len(historia_rozmowy) <= 1:
        dynamiczny_kontekst = (
            f"AKTUALNY TEMAT: {temat_kontekst}\n"
            f"STATUS: Początek lekcji. Wygeneruj FAZĘ TEORII, a następnie pierwsze zadanie.\n"
            f"ZIARNO_LOSOWOSCI: {ziarno}"
        )
    else:
        dynamiczny_kontekst = (
            f"AKTUALNY TEMAT: {temat_kontekst}\n"
            f"STATUS: Uczeń rozwiązał poprawnie {licznik_zadan} z 8 zadań. Jesteś w FAZIE PRAKTYKI. Podaj wyłącznie zadanie, nie powtarzaj teorii.\n"
            f"ZIARNO_LOSOWOSCI: {ziarno}"
        )

    # Próba wywołania przez nowe SDK google-genai jeśli dostępne
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        
        contents_sdk = []
        for m in historia_rozmowy[-10:]:
            role = "user" if m["role"] == "user" else "model"
            contents_sdk.append({"role": role, "parts": [{"text": m["content"]}]})

        if contents_sdk and contents_sdk[0]["role"] == "model":
            contents_sdk.insert(0, {"role": "user", "parts": [{"text": "Rozpoczynamy lekcję."}]})

        full_system_instruction = f"{system_prompt}\n\n{dynamiczny_kontekst}"
        
        # Próba wygenerowania odpowiedzi przez SDK
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=contents_sdk,
            config={
                "system_instruction": full_system_instruction,
                "temperature": 0.7,
                "top_p": 0.95,
            }
        )
        if response.text:
            return response.text
    except Exception:
        pass  # Przejście do REST fallback w razie braku biblioteki lub innego błedu

    # --- REST FALLBACK (Z powtórzeniami przy 429) ---
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"

    contents = [
        {
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["content"]}]
        }
        for m in historia_rozmowy[-10:]
    ]

    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "Rozpoczynamy lekcję."}]})

    payload = {
        "contents": contents,
        "systemInstruction": {
            "parts": [{"text": f"{system_prompt}\n\n{dynamiczny_kontekst}"}]
        },
        "generationConfig": {
            "temperature": 0.7,
            "topP": 0.95
        }
    }

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=25)
            if response.status_code == 429:
                if attempt < max_retries - 1:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return "❌ Przeciążenie serwera (429). Spróbuj ponownie za chwilę."

            if response.status_code == 200:
                json_resp = response.json()
                if "candidates" in json_resp and json_resp["candidates"]:
                    parts = json_resp["candidates"][0]["content"]["parts"]
                    return "".join(p.get("text", "") for p in parts)
                return "❌ Model zwrócił pustą odpowiedź."

            return f"❌ Błąd API ({response.status_code}): {response.text}"
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                continue
            return "❌ Przekroczono czas oczekiwania na odpowiedź AI."
        except Exception as e:
            return f"❌ Błąd połączenia: {str(e)}"

    return "❌ Nie udało się uzyskać odpowiedzi od AI."
