import streamlit as st
import requests
from google.oauth2 import service_account
from google.cloud import firestore

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
        # --- KLUCZOWA POPRAWKA ---
        # Jeśli dane są już listą, używamy ich. Jeśli to string, pakujemy w listę.
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
        db.collection("postepy_uczniow").document(st.session_state.zalogowany_id).set({
            "user_api_key": st.session_state.user_api_key,
            "postep_tematow": st.session_state.postep_tematow
        })

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

KOMENDY DEWELOPERSKIE:
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
- Podaj wynik liczbowy i ocenę.


"""
def zapytaj_ai(historia_rozmowy, temat_kontekst):
    if not st.session_state.get("user_api_key"):
        return "❌ BŁĄD: Brak klucza API w profilu!"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={st.session_state.user_api_key}"
    
    # Przygotowanie historii
    contents = []
    for m in historia_rozmowy:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    
    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": f"{SYSTEM_PROMPT}\n\nAKTUALNY TEMAT: {temat_kontekst}"}]}
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        else:
            return f"❌ Błąd API ({response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Błąd połączenia: {str(e)}"

# =====================================================================
# LOGOWANIE
# =====================================================================
if "zalogowany_id" not in st.session_state:
    st.title("🏫 Logowanie do Systemu")
    id_input = st.text_input("Identyfikator:").strip()
    klucz_input = st.text_input("Klucz Gemini API:", type="password")
    if st.button("Zaloguj"):
        dane = wczytaj_profil_z_chmury(id_input)
        if dane:
            st.session_state.zalogowany_id = id_input
            st.session_state.user_api_key = dane.get("user_api_key", "")
            st.session_state.postep_tematow = dane.get("postep_tematow", {})
            st.rerun()
        elif klucz_input:
            st.session_state.zalogowany_id = id_input
            st.session_state.user_api_key = klucz_input
            st.session_state.postep_tematow = {}
            zapisz_profil_w_chmurze()
            st.rerun()
    st.stop()

if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_strukture()

# =====================================================================
# INTERFEJS GŁÓWNY 
# =====================================================================
with st.sidebar:
    st.header("🏫 Dziennik Ucznia")
    wybrany_przedmiot = st.selectbox("Wybierz przedmiot:", list(st.session_state.struktura_dydaktyczna.keys()))
    
    # Lista tematów
    dostepne = st.session_state.struktura_dydaktyczna.get(wybrany_przedmiot, [])
    
    st.subheader("📚 Status tematów")
    
    # Sortowanie: "W trakcie" i "Nie rozpoczęte" na górze, reszta na dole
    def priorytet(t):
        s = st.session_state.postep_tematow.get(t, "Nie rozpoczęte")
        return {"W trakcie": 0, "Nie rozpoczęte": 1, "NIEZALICZONY": 2, "ZALICZONY": 3}.get(s, 4)

    # Pętla wyświetlająca statusy
    for temat in sorted(dostepne, key=priorytet):
        status = st.session_state.postep_tematow.get(temat, "Nie rozpoczęte")
        
        if status == "ZALICZONY": 
            st.success(f"✅ {temat}")
        elif status == "W trakcie": 
            st.info(f"🔄 **{temat}**")
        elif status == "NIEZALICZONY": 
            st.error(f"❌ {temat} (niezaliczony)")
        else: 
            st.warning(f"🚩 {temat}")

    st.markdown("---")
    # Dopiero tutaj Twój selectbox do rozpoczęcia
    wybor_tematu = st.selectbox("Wybierz temat do rozpoczęcia:", [t for t in dostepne if st.session_state.postep_tematow.get(t) != "ZALICZONY"])
    
    if st.button("Rozpocznij lekcję"):
            st.session_state.aktualny_temat = wybor_tematu
            st.session_state.postep_tematow[wybor_tematu] = "W trakcie"
            st.session_state.licznik_zadan = 0
            
            st.session_state.messages = [] 
            st.session_state.teoria_lekcji = None 
            
            with st.spinner("Przygotowuję lekcję..."):
                # 1. Prosimy AI o odpowiedź z wyraźnym separatorem
                instrukcja = "Wyślij odpowiedź w formacie: [TEORIA]Treść teorii i treść algorytmu decyzyjnego[TEORIA_KONIEC] [ZADANIE]treśc pierwszego zadania"
                odpowiedz_z_ai = zapytaj_ai([{"role": "user", "content": instrukcja}], wybor_tematu)
                
                # 2. Tu jest "magia" - tniemy stringa w kodzie Pythona
                if "[TEORIA]" in odpowiedz_z_ai and "[ZADANIE]" in odpowiedz_z_ai:
                    # Wycinamy teorię
                    teoria_raw = odpowiedz_z_ai.split("[TEORIA]")[1]
                    teoria = teoria_raw.split("[TEORIA_KONIEC]")[0].strip()
                    
                    # Wycinamy zadanie
                    zadanie = odpowiedz_z_ai.split("[ZADANIE]")[1].strip()
                    
                    # 3. Rozdzielamy to do różnych zmiennych w aplikacji
                    st.session_state.teoria_lekcji = teoria
                    st.session_state.messages.append({"role": "assistant", "content": zadanie})
                else:
                    # Jeśli AI nie trafiło z formatem, wszystko idzie do teorii (bezpiecznik)
                    st.session_state.teoria_lekcji = odpowiedz_z_ai
                    
# --- GŁÓWNY EKRAN (musi być wyrównany do lewej, NIE pod sidebar) ---
# --- EKRAN POWITALNY / DASHBOARD ---
if "aktualny_temat" not in st.session_state:
    st.title(f"Cześć {st.session_state.zalogowany_id}, w czym mogę pomóc?")
    
    # Wykres postępów (przykład: licznik zaliczonych tematów wg typu)
    st.subheader("Twój postęp")
    dane_wykresu = {t: 1 if s == "ZALICZONY" else 0 for t, s in st.session_state.postep_tematow.items()}
    if dane_wykresu:
        st.bar_chart(dane_wykresu)
    else:
        st.write("Rozpocznij pierwszy temat, aby zobaczyć statystyki!")
    
    st.info("Wybierz przedmiot i temat z bocznego paska, aby zacząć naukę.")
    st.stop()
    
if "aktualny_temat" in st.session_state:
    st.caption(f"📖 Temat: {st.session_state.aktualny_temat}")
    # PASEK POSTĘPU
    if st.session_state.get("licznik_zadan", 0) > 0:
        postep = st.session_state.licznik_zadan / 8
        st.progress(postep, text=f"Postęp praktyki: {st.session_state.licznik_zadan}/8 zadań")
    # 1. Wyświetl teorię
    jest_sprawdzian = any("TEST" in m["content"].upper() or "SPRAWDZIAN" in m["content"].upper() for m in st.session_state.messages)
    if st.session_state.get("teoria_lekcji") and not jest_sprawdzian:
        with st.expander("📘 MATERIAŁY POMOCNICZE", expanded=True):
            st.markdown(st.session_state.teoria_lekcji)
    
    # 2. Wyświetl TYLKO OSTATNIĄ wiadomość
    if st.session_state.messages:
        ostatnia_wiadomosc = st.session_state.messages[-1]
        with st.chat_message(ostatnia_wiadomosc["role"]): 
            st.markdown(ostatnia_wiadomosc["content"])

# Obsługa odpowiedzi
    if prompt := st.chat_input("Napisz odpowiedź..."):
        # LOGIKA POTWIERDZENIA SPRAWDZIANU
        if st.session_state.get("oczekuje_na_potwierdzenie"):
            if prompt.upper() == "TAK":
                # Tutaj AI powinno już sprawdzić wyniki, wysyłamy pusty prompt by AI zakończyło fazę
                st.session_state.oczekuje_na_potwierdzenie = False
            else:
                st.session_state.oczekuje_na_potwierdzenie = False
                st.warning("Dobrze, spróbuj jeszcze raz pomyśleć.")
                st.rerun()

        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.spinner("Myślę..."):
            odp = zapytaj_ai(st.session_state.messages, st.session_state.aktualny_temat)
            
            # Wychwycenie momentu "Czy na pewno chcesz oddać?"
            if "CZY NA PEWNO CHCESZ ODDAĆ" in odp.upper():
                st.session_state.oczekuje_na_potwierdzenie = True
            
            if "[ZALICZONE]" in odp and st.session_state.licznik_zadan < 8:
                st.session_state.licznik_zadan += 1
            
            # ... (reszta Twojej logiki aktualizacji statusów) ...
            st.session_state.messages.append({"role": "assistant", "content": odp.replace("[ZALICZONE]", "").strip()})
            zapisz_profil_w_chmurze()
            st.rerun()
