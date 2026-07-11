import streamlit as st
import requests
from google.oauth2 import service_account
from google.cloud import firestore
import pandas as pd
from datetime import datetime

# =====================================================================
# KONFIGURACJA FIRESTORE
# =====================================================================
def init_firestore():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

def pobierz_strukture():
    docs = db.collection("przedmioty").stream()
    struktura = {}
    for doc in docs:
        dane = doc.to_dict().get("lista_tematow", [])
        if isinstance(dane, list):
            struktura[doc.id] = dane
        else:
            struktura[doc.id] = [str(dane)]
    return struktura

def wczytaj_profil_z_chmury(identyfikator):
    doc = db.collection("postepy_uczniow").document(identyfikator).get()
    return doc.to_dict() if doc.exists else None

def zapisz_profil_w_chmurze():
    if "zalogowany_id" in st.session_state:
        dane_do_zapisu = {
            "user_api_key": st.session_state.user_api_key,
            "postep_tematow": st.session_state.postep_tematow,
            "historia_czatow": st.session_state.get("historia_czatow", {}),
            "teorie_lekcji": st.session_state.get("teorie_lekcji", {})
        }
        db.collection("postepy_uczniow").document(st.session_state.zalogowany_id).set(dane_do_zapisu, merge=True)

def czy_temat_niezaliczone(t, postepy):
    dane = postepy.get(t, "Nie rozpoczęte")
    status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
    return status != "ZALICZONY"

# =====================================================================
# LOGIKA AI
# =====================================================================
SYSTEM_PROMPT = """Jesteś Autonomicznym Systemem Edukacyjnym. Twoim zadaniem jest przeprowadzenie ucznia przez wybrany Temat według ściśle określonego algorytmu.

GŁÓWNE ZASADY BEZPIECZEŃSTWA:
- NIGDY nie podawaj gotowego wyniku ani pełnego rozwiązania zadania.
- Jeśli uczeń pyta o rzeczy niezwiązane z lekcją, napisz: "Wróćmy do nauki" i powtórz aktualne zadanie.
- ZAKAZ GENEROWANIA "THOUGHTS". Odpowiadaj bezpośrednio do ucznia.
- WSKAZÓWKI: Muszą być krótkie (max 2 zdania), potoczne, nie akademickie.

KOMENDY DEWELOPERSKIE:
- Hasło dostępowe: "samolotdom".
- Jeśli uczeń wpisze jedną z poniższych komend, ZAWSZE najpierw zapytaj: "Podaj hasło dostępowe do panelu deweloperskiego".
- Dopiero po poprawnym wpisaniu hasła "samolotdom", wykonaj komendę.

LISTA KOMEND:
- panel deweloperski: Wyświetl listę dostępnych komend i ich opis.
- /sprawdzian: Natychmiastowe przejście do FAZY TESTU KOŃCOWEGO.
- ocena: Aktywacja FAZY OCENIANIA.
- od nowa: Restart sesji.

PĘTLA LOGICZNA TEMATU:

1. [FAZA TEORII]: 
   - Tekst 1 (Dane): Max 50 zdań wiedzy merytorycznej z logicznymi akapitami.
   - Tekst 2 (Algorytm decyzyjny): Stwórz strukturę: [krok/pytanie] -> [Akcja: jeśli TAK / jeśli NIE].
   - Po wyświetleniu przejdź do Fazy Praktyki.

2. [FAZA PRAKTYKI]:
   - jezeli zadanie zostalo poprawnie rozwiązane zacznij wiadomosć od [ZALICZONE]
   - przy pierwszym zadaniu się przywitaj 
   - Generuj 8 zadań (po 2 z 4 typów). Podawaj PO JEDNYM.
   - Jeśli uczeń prosi o pomoc: daj wskazówkę (hint), nie rozwiązuj za niego.
   - Jeśli uczeń odpowie DOBRZE: usuń zadanie z listy, podaj kolejne.
   - Jeśli uczeń odpowie ŹLE: Wyjaśnij krótko dlaczego (używając algorytmu decyzyjnego), napisz "Odłóżmy to zadanie na koniec", przesuń zadanie na koniec kolejki i daj nowe.
   - [faza przygotowania]: Po rozwiązaniu wszystkich zadań zapytaj ucznia, czy chce jeszcze poćwiczyć konkretny typ zadania. poinforumuj go że jeżeli chce iśc dalej to ma napisać koniec.Jeśli napisze "koniec", przejdź do FAZY TESTU KOŃCOWEGO. Jeśli "NIE", idź tam od razu.
   - po każdym poprawnie wykonanym zadaniu Dodaj jedno krótkie zdanie budujące pewność siebie lub odnieś sie do logiki ucznia (np. "Dokładnie tak, świetnie przekształciłeś wzór!")
   - po źle wykonanym zadaniu pociesz ucznia
   - przy ponownym rozwiązywaniu źle zrobionego zadania staraj sie naprowadziać ucznia
3. [FAZA TESTU KOŃCOWEGO]: 
   - Powiedz: "Czas na test sprawdzający. Teraz pracujesz samodzielnie, bez moich wskazówek". Wygeneruj 4 zadania (po jednym z typu).
   - PROCEDURA ODDAWANIA: Po pierwszej odpowiedzi ucznia MASZ ZAKAZ sprawdzania wyników. Wyświetl tylko: "Czy na pewno chcesz oddać sprawdzian? Napisz TAK lub NIE."
   - REAKCJA: 
     -> "NIE": Napisz: "Dobrze, spróbuj jeszcze raz pomyśleć", wyświetl test ponownie.
     -> "TAK": Sprawdź test.
        * 100% -> Wyświetl: "GRATULACJE! Temat ZALICZONY."
        * <100% -> Wyświetl: "Test niezaliczony na 100%. Pomijamy ten temat na później" + wyjaśnij błędy. Oznacz temat jako "POMINIĘTY".

FAZA OCENIANIA:
- Policz skończone tematy vs wszystkie tematy.
- Wynik = (skończone / wszystkie).
- Skala: 1.0-0.9 = 6; 0.89-0.7 = 5; 0.69-0 = 1.
- Podaj wynik liczbowy i ocenę."""

def zapytaj_ai(historia_rozmowy, temat_kontekst):
    if not st.session_state.get("user_api_key"): return "❌ BŁĄD: Brak klucza API!"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.session_state.user_api_key}"
    contents = [{"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]} for m in historia_rozmowy]
    payload = {"contents": contents, "systemInstruction": {"parts": [{"text": f"{SYSTEM_PROMPT}\n\nAKTUALNY TEMAT: {temat_kontekst}"}]}}
    try:
        response = requests.post(url, json=payload)
        return response.json()['candidates'][0]['content']['parts'][0]['text'] if response.status_code == 200 else f"Błąd {response.status_code}"
    except Exception as e: return f"Błąd: {e}"

# =====================================================================
# LOGOWANIE
# =====================================================================
if "zalogowany_id" not in st.session_state:
    st.title("🏫 Logowanie")
    id_input = st.text_input("Identyfikator:").strip()
    klucz_input = st.text_input("Klucz API:", type="password")
    haslo = st.text_input("Hasło:", type="password")
    if st.button("Zaloguj"):
        dane = wczytaj_profil_z_chmury(id_input)
        if dane:
            st.session_state.update({"zalogowany_id": id_input, "user_api_key": dane.get("user_api_key"), "postep_tematow": dane.get("postep_tematow", {}), "historia_czatow": dane.get("historia_czatow", {}), "teorie_lekcji": dane.get("teorie_lekcji", {})})
            st.rerun()
        elif haslo == "TwojeTajneHaslo123":
            db.collection("postepy_uczniow").document(id_input).set({"user_api_key": klucz_input, "postep_tematow": {}, "historia_czatow": {}, "teorie_lekcji": {}})
            st.success("Konto utworzone!")
            st.rerun()
    st.stop()

if "struktura_dydaktyczna" not in st.session_state: st.session_state.struktura_dydaktyczna = pobierz_strukture()

# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    wybrany_przedmiot = st.selectbox("Przedmiot:", list(st.session_state.struktura_dydaktyczna.keys()))
    dostepne = st.session_state.struktura_dydaktyczna.get(wybrany_przedmiot, [])
    
    # Naprawiona logika selektora
    do_wyboru = [t for t in dostepne if czy_temat_niezaliczone(t, st.session_state.postep_tematow)]
    wybor_tematu = st.selectbox("Temat:", do_wyboru)
    
    if st.button("Rozpocznij lekcję"):
        st.session_state.aktualny_temat = wybor_tematu
        st.session_state.licznik_zadan = 0
        st.session_state.messages = st.session_state.historia_czatow.get(wybor_tematu, [])
        st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu, "")
        st.rerun()

# =====================================================================
# EKRAN GŁÓWNY
# =====================================================================
if "aktualny_temat" not in st.session_state:
    st.title(f"Witaj {st.session_state.zalogowany_id}")
else:
    if prompt := st.chat_input("Napisz odpowiedź..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        odp = zapytaj_ai(st.session_state.messages, st.session_state.aktualny_temat)
        st.session_state.messages.append({"role": "assistant", "content": odp})
        st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
        zapisz_profil_w_chmurze()
        st.rerun()

    for m in st.session_state.messages:
        with st.chat_message(m["role"]): st.markdown(m["content"])
