import random
import time
import requests
import streamlit as st


def zapytaj_ai(historia_rozmowy: list, temat_kontekst: str, licznik_zadan: int, system_prompt: str) -> str:
    api_key = st.session_state.get("user_api_key")
    if not api_key:
        return "❌ BŁĄD: Brak klucza API w profilu!"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={api_key}"

    contents = [
        {
            "role": "user" if m["role"] == "user" else "model",
            "parts": [{"text": m["content"]}]
        }
        for m in historia_rozmowy[-10:]
    ]

    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "Rozpoczynamy lekcję."}]})

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

    try:
        response = requests.post(url, json=payload, timeout=20)
        if response.status_code == 429:
            return "❌ Przeciążenie serwera (429). Spróbuj ponownie za chwilę."
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return f"❌ Błąd API ({response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Błąd połączenia: {str(e)}"
