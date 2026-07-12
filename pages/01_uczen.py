import streamlit as st
import requests
from google.oauth2 import service_account
from google.cloud import firestore
import pandas as pd
from datetime import datetime

# --- STRAŻNIK ---
if "zalogowany_id" not in st.session_state:
    st.switch_page("app.py")
if st.session_state.get("role") != "uczen":
    st.error("Nie masz uprawnień ucznia.")
    st.stop()

# =====================================================================
# KONFIGURACJA FIRESTORE
# =====================================================================
def init_firestore():
    try:
        if "connections" not in st.secrets:
            st.error("❌ BŁĄD: Brak sekcji [connections] w pliku secrets.toml!")
            return None
        
        key_dict = st.secrets["connections"]["firestore"]
        if not key_dict:
            st.error("❌ BŁĄD: Sekcja [connections.firestore] jest pusta!")
            return None
            
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ KRYTYCZNY BŁĄD FIRESTORE: {str(e)}")
        return None

db = init_firestore()
if db is None:
    st.stop()

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

# Odchudzona funkcja zapisu - obsługuje wszystko na raz
def zapisz_profil_w_chmurze():
    if "zalogowany_id" in st.session_state:
        postepy = st.session_state.get("postep_tematow", {})
        historia = st.session_state.get("historia_czatow", {})
        
        if not isinstance(historia, dict):
            historia = {}
            
        if "aktualny_temat" in st.session_state:
            temat = st.session_state.aktualny_temat
            licznik = st.session_state.get("licznik_zadan", 0)
            
            if not isinstance(postepy.get(temat), dict):
                postepy[temat] = {"status": postepy.get(temat, "W trakcie")}
            postepy[temat]["licznik"] = licznik
            st.session_state.postep_tematow = postepy

        dane_do_zapisu = {
            "user_api_key": st.session_state.get("user_api_key", ""),
            "postep_tematow": postepy,
            "historia_czatow": historia,
            "teorie_lekcji": st.session_state.get("teorie_lekcji", {})
        }
        db.collection("postepy_uczniow").document(st.session_state.zalogowany_id).set(dane_do_zapisu, merge=True)

def czy_temat_niezaliczone(t):
    dane = st.session_state.postep_tematow.get(t, "Nie rozpoczęte")
    status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
    return status != "ZALICZONY"

# =====================================================================
# LOGIKA AI (SYSTEM PROMPT)
# =====================================================================
SYSTEM_PROMPT = """
Jesteś Autonomicznym Systemem Edukacyjnym. Twoim zadaniem jest przeprowadzenie ucznia przez wybrany Temat według ściśle określonego algorytmu.

GŁÓWNE ZASADY BEZPIECZEŃSTWA:
- NIGDY nie podawaj gotowego wyniku ani pełnego rozwiązania zadania.
- Jeśli uczeń pyta o rzeczy niezwiązane z lekcją, napisz: "Wróćmy do nauki" i powtórz aktualne zadanie.
- ZAKAZ GENEROWANIA "THOUGHTS". Odpowiadaj bezpośrednio do ucznia.
- WSKAZÓWKI: Muszą być krótkie (max 2 zdania), potoczne, nie akademickie.

PĘTLA LOGICZNA TEMATU:
1. [FAZA TEORII]: 
   - Tekst 1 (Dane): Max 50 zdań wiedzy merytorycznej z logicznymi akapitami.
   - Tekst 2 (Algorytm decyzyjny): Stwórz strukturę: [krok/pytanie] -> [Akcja: jeśli TAK / jeśli NIE].
   - Po wyświetleniu przejdź do Fazy Praktyki.

2. [FAZA PRAKTYKI]:
   - jezeli zadanie zostalo poprawnie rozwiązane zacznij wiadomosć od [ZALICZONE]
   - Generuj 8 zadań (po 2 z 4 typów). Podawaj PO JEDNYM.
   - Jeśli uczeń odpowie DOBRZE: podaj kolejne zadanie.
   - Jeśli uczeń odpowie ŹLE: Wyjaśnij krótko dlaczego, napisz "Odłóżmy to zadanie na koniec", przesuń zadanie na koniec kolejki i daj nowe.
"""

# ZMIANA: Dodano "licznik_zadan" do argumentów
def zapytaj_ai(historia_rozmowy, temat_kontekst, licznik_zadan):
    if not st.session_state.get("user_api_key"):
        return "❌ BŁĄD: Brak klucza API w profilu!"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={st.session_state.user_api_key}"
    
    historia_do_wyslania = historia_rozmowy[-10:]
    
    contents = []
    for m in historia_do_wyslania:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    
    # KOTWICA KONTEKSTOWA: Przypominamy AI na jakim jest etapie
    dynamiczny_kontekst = f"AKTUALNY TEMAT: {temat_kontekst}\nSTATUS: Uczeń rozwiązał poprawnie {licznik_zadan} z 8 zadań. Jesteś w FAZIE PRAKTYKI. Podaj wyłącznie zadanie, nie powtarzaj teorii."
    if licznik_zadan == 0 and len(historia_rozmowy) <= 1:
        dynamiczny_kontekst = f"AKTUALNY TEMAT: {temat_kontekst}\nSTATUS: Początek lekcji. Wygeneruj FAZĘ TEORII, a następnie pierwsze zadanie."

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{dynamiczny_kontekst}"}]}
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 429:
            raise Exception("Limit 429 przekroczony - ponawiam próbę...")
            
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"❌ Błąd API ({response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Błąd połączenia: {str(e)}"

# =====================================================================
# INTERFEJS GŁÓWNY (Sidebar)
# =====================================================================
if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_strukture()

with st.sidebar:
    st.header("🏫 Dziennik Ucznia")
    wybrany_przedmiot = st.selectbox("Wybierz przedmiot:", list(st.session_state.struktura_dydaktyczna.keys()))
    dostepne = st.session_state.struktura_dydaktyczna.get(wybrany_przedmiot, [])
    
    st.subheader("📚 Status tematów")
    
    def priorytet(t):
        dane = st.session_state.postep_tematow.get(t, "Nie rozpoczęte")
        s = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        return {"W trakcie": 0, "Nie rozpoczęte": 1, "NIEZALICZONY": 2, "ZALICZONY": 3}.get(s, 4)

    for temat in sorted(dostepne, key=priorytet):
        dane = st.session_state.postep_tematow.get(temat, "Nie rozpoczęte")
        status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        
        if status == "ZALICZONY": st.success(f"✅ {temat}")
        elif status == "W trakcie": st.info(f"🔄 {temat}")
        elif status == "NIEZALICZONY": st.error(f"❌ {temat} (niezaliczony)")
        else: st.warning(f"🚩 {temat}")
        
    st.markdown("---")
    
    wybor_tematu = st.selectbox(
        "Wybierz temat do rozpoczęcia:", 
        [t for t in dostepne if czy_temat_niezaliczone(t)],
        key="glowny_wybor_tematu"
    )
    
    if st.button("Rozpocznij lekcję"):
        st.session_state.aktualny_temat = wybor_tematu
        profil = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)
        
        if profil and isinstance(profil, dict):
            st.session_state.teorie_lekcji = profil.get("teorie_lekcji", {})
            st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu, None)
            
            stan_tematu = profil.get("postep_tematow", {}).get(wybor_tematu)
            st.session_state.licznik_zadan = stan_tematu.get("licznik", 0) if isinstance(stan_tematu, dict) else 0
            
            historia = profil.get("historia_czatow", {})
            st.session_state.messages = historia.get(wybor_tematu, []) if isinstance(historia, dict) else []
        else:
            st.session_state.teoria_lekcji = None
            st.session_state.messages = []
            st.session_state.licznik_zadan = 0
            
        if not st.session_state.messages:
            with st.spinner("Przygotowuję lekcję..."):
                instrukcja = "Wyślij odpowiedź w formacie: [TEORIA]Treść teorii[TEORIA_KONIEC] [ZADANIE]Treść zadania"
                # Podajemy licznik = 0
                odp = zapytaj_ai([{"role": "user", "content": instrukcja}], wybor_tematu, 0)
                
                if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                    st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                    if "teorie_lekcji" not in st.session_state: st.session_state.teorie_lekcji = {}
                    st.session_state.teorie_lekcji[wybor_tematu] = st.session_state.teoria_lekcji
                    
                    st.session_state.messages.append({"role": "assistant", "content": odp.split("[ZADANIE]")[1].strip()})
                    zapisz_profil_w_chmurze()
                else:
                    st.session_state.teoria_lekcji = odp
        st.rerun()

# =====================================================================
# EKRAN GŁÓWNY
# =====================================================================
if "aktualny_temat" not in st.session_state:
    st.title(f"Cześć {st.session_state.zalogowany_id}, w czym mogę pomóc?")
    st.subheader("Twój postęp (ostatnie 4 tygodnie)")
    
    dzis = datetime.now()
    tygodnie_dane = {"Tydzień 1": 0, "Tydzień 2": 0, "Tydzień 3": 0, "Tydzień 4": 0}

    for temat, dane in st.session_state.postep_tematow.items():
        status = dane.get("status") if isinstance(dane, dict) else dane
        data_str = dane.get("data") if isinstance(dane, dict) else None
        
        if status == "ZALICZONY" and data_str:
            try:
                data_uko = datetime.strptime(data_str, "%Y-%m-%d")
                roznica_dni = (dzis - data_uko).days
                
                if 0 <= roznica_dni < 7: tygodnie_dane["Tydzień 1"] += 1
                elif 7 <= roznica_dni < 14: tygodnie_dane["Tydzień 2"] += 1
                elif 14 <= roznica_dni < 21: tygodnie_dane["Tydzień 3"] += 1
                elif 21 <= roznica_dni < 28: tygodnie_dane["Tydzień 4"] += 1
            except ValueError:
                continue 

    st.bar_chart(pd.DataFrame.from_dict(tygodnie_dane, orient='index', columns=['Ilość']))
        
else:
    st.caption(f"📖 Temat: {st.session_state.aktualny_temat}")
    st.subheader("Postęp w temacie:")
    licznik = st.session_state.get("licznik_zadan", 0)
    st.progress(min(licznik / 8, 1.0))
    st.caption(f"Wykonano zadań: {licznik} / 8")
    
    czy_sprawdzian = any("sprawdzający" in m["content"] for m in st.session_state.messages)
    
    if st.session_state.get("teoria_lekcji") and not czy_sprawdzian:
        with st.expander("📘 MATERIAŁY", expanded=True):
            st.markdown(st.session_state.teoria_lekcji)
            
    if st.session_state.messages:
        ostatnia = st.session_state.messages[-1]
        with st.chat_message(ostatnia["role"]):
            st.markdown(ostatnia["content"])
            
    if prompt := st.chat_input("Napisz odpowiedź..."):
        if "aktualny_temat" not in st.session_state:
            st.error("Błąd: Nie wybrano tematu!")
        else:
            stan_tematu = st.session_state.postep_tematow.get(st.session_state.aktualny_temat, {})
            status = stan_tematu.get("status") if isinstance(stan_tematu, dict) else stan_tematu
            
            if status == "Nie rozpoczęte" or status is None:
                st.session_state.postep_tematow[st.session_state.aktualny_temat] = {"status": "W trakcie"}
                zapisz_profil_w_chmurze() 
            
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.spinner("Myślę..."):
                # Przekazujemy licznik zadan do funkcji AI!
                obecny_licznik = st.session_state.get("licznik_zadan", 0)
                odp = zapytaj_ai(st.session_state.messages, st.session_state.aktualny_temat, obecny_licznik)
                
                if odp.startswith("❌"):
                    st.error(f"AI zwróciło błąd: {odp}")
                else:
                    if "[ZALICZONE]" in odp:
                        st.session_state.licznik_zadan = obecny_licznik + 1
                    
                    st.session_state.messages.append({"role": "assistant", "content": odp.replace("[ZALICZONE]", "").strip()})
                    
                    if not isinstance(st.session_state.get("historia_czatow"), dict):
                        st.session_state.historia_czatow = {}
                    st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
                    
                    zapisz_profil_w_chmurze()
                    st.rerun()