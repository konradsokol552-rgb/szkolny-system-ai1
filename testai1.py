import streamlit as st
import requests
from google.oauth2 import service_account
from google.cloud import firestore
import pandas as pd
from datetime import datetime, timedelta
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
        historia = st.session_state.get("historia_czatow", {})
        if not isinstance(historia, dict):
            historia = {}

        dane_do_zapisu = {
            "user_api_key": st.session_state.user_api_key,
            "postep_tematow": st.session_state.postep_tematow,
            "historia_czatow": st.session_state.get("historia_czatow", {}),
            "teorie_lekcji": st.session_state.get("teorie_lekcji", {})
        }
        db.collection("postepy_uczniow").document(st.session_state.zalogowany_id).set(dane_do_zapisu, merge=True)
def zapisz_historie_w_chmurze(temat, wiadomosci):
    if "zalogowany_id" in st.session_state:
        profil = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)
        
        # ZABEZPIECZENIE: Pobierz historię tylko jeśli to słownik, inaczej stwórz pusty
        historia_pelna = profil.get("historia_czatow")
        if not isinstance(historia_pelna, dict):
            historia_pelna = {}
        
        # Teraz bezpiecznie aktualizujemy
        historia_pelna[temat] = wiadomosci
        
        # Zapis do bazy
        db.collection("postepy_uczniow").document(st.session_state.zalogowany_id).update({
            "historia_czatow": historia_pelna
        })
# Przygotowanie listy dostępnych tematów
def czy_temat_niezaliczone(t):
    dane = st.session_state.postep_tematow.get(t, "Nie rozpoczęte")
    # Wyciągamy status bezpiecznie, niezależnie czy to słownik czy string
    status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
    return status != "ZALICZONY"

    # Używamy nowej funkcji filtrującej
    wybor_tematu = st.selectbox(
        "Wybierz temat do rozpoczęcia:", 
        [t for t in dostepne if czy_temat_niezaliczone(t)],
        key="glowny_wybor_tematu"
    )

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
- Podaj wynik liczbowy i ocenę.


"""
def zapytaj_ai(historia_rozmowy, temat_kontekst):
    if not st.session_state.get("user_api_key"):
        return "❌ BŁĄD: Brak klucza API w profilu!"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={st.session_state.user_api_key}"
    
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
    klucz_input = st.text_input("Klucz Gemini API (tylko przy twożeniu konta)", type="password")
    haslo_tworzenia = st.text_input("Hasło (tylko przy twożeniu konta):", type="password")
    
    if st.button("Zaloguj / Zarejestruj"):
        dane = wczytaj_profil_z_chmury(id_input)
        
        if dane:
            st.session_state.zalogowany_id = id_input
            st.session_state.user_api_key = dane.get("user_api_key", "")
            
            # --- KLUCZOWE: Inicjalizacja postępów z bazy ---
            surowe_postepy = dane.get("postep_tematow", {})
            st.session_state.postep_tematow = surowe_postepy 
            st.session_state.historia_czatow = dane.get("historia_czatow", {})
            st.rerun()
        else:
            if haslo_tworzenia == "TwojeTajneHaslo123":
                nowy_profil = {"user_api_key": klucz_input, "postep_tematow": {}, "historia_czatow": {}}
                db.collection("postepy_uczniow").document(id_input).set(nowy_profil)
                st.success("Konto utworzone! Zaloguj się.")
            else:
                st.error("Błędny identyfikator lub hasło!")
    st.stop() # ZATRZYMUJE CAŁĄ RESZTĘ, DOPÓKI NIE BĘDZIE ZALOGOWANY
if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_strukture()

# =====================================================================
# INTERFEJS GŁÓWNY (Sidebar)
# =====================================================================
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
        elif status == "W trakcie": st.info(f"🔄 **{temat}**")
        elif status == "NIEZALICZONY": st.error(f"❌ {temat} (niezaliczony)")
        else: st.warning(f"🚩 {temat}")
        
    st.markdown("---")
    
    # UNIKALNY KLUCZ ROZWIĄZUJE BŁĄD DUPLICATE ELEMENT
    wybor_tematu = st.selectbox(
        "Wybierz temat do rozpoczęcia:", 
        [t for t in dostepne if czy_temat_niezaliczone(t)],
        key="glowny_wybor_tematu"
    )
    
    if st.button("Rozpocznij lekcję"):
        st.session_state.aktualny_temat = wybor_tematu
        st.session_state.licznik_zadan = 0
        
        # 1. NAJPIERW POBIERZ PROFIL
        profil = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)
        
        # 2. TERAZ MOŻESZ Z NIEGO KORZYSTAĆ
        if profil and isinstance(profil, dict):
            # Wczytaj zapisaną teorię
            st.session_state.teorie_lekcji = profil.get("teorie_lekcji", {})
            st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu, None)
            
            # Wczytaj historię
            historia = profil.get("historia_czatow", {})
            st.session_state.messages = historia.get(wybor_tematu, []) if isinstance(historia, dict) else []
        else:
            st.session_state.teoria_lekcji = None
            st.session_state.messages = []
            
        # 3. Jeśli nie ma historii, wygeneruj lekcję
        if not st.session_state.messages:
            with st.spinner("Przygotowuję lekcję..."):
                instrukcja = "Wyślij odpowiedź w formacie: [TEORIA]Treść teorii[TEORIA_KONIEC] [ZADANIE]Treść zadania"
                odp = zapytaj_ai([{"role": "user", "content": instrukcja}], wybor_tematu)
                
                if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                    st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                    # Zapisz do sesji i bazy
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

    # Pętla zliczająca postępy
    for temat, dane in st.session_state.postep_tematow.items():
        # Obsługa formatu dict (nowy) oraz string (stary/pozostałości)
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
    # --- NAGŁÓWEK I PASEK POSTĘPU ---
    st.caption(f"📖 Temat: {st.session_state.aktualny_temat}")
    st.subheader("Postęp w temacie:")
    licznik = st.session_state.get("licznik_zadan", 0)
    st.progress(min(licznik / 8, 1.0))
    st.caption(f"Wykonano zadań: {licznik} / 8")
    
    # --- MATERIAŁY (TEORIA) ---
    czy_sprawdzian = any("sprawdzający" in m["content"] for m in st.session_state.messages)
    
    if st.session_state.get("teoria_lekcji") and not czy_sprawdzian:
        with st.expander("📘 MATERIAŁY", expanded=True):
            st.markdown(st.session_state.teoria_lekcji)
    
    # --- CZAT (TYLKO OSTATNIA WIADOMOŚĆ) ---
    if st.session_state.messages:
        ostatnia = st.session_state.messages[-1]
        with st.chat_message(ostatnia["role"]):
            st.markdown(ostatnia["content"])
            
    # --- OBSŁUGA INPUTU ---
    if prompt := st.chat_input("Napisz odpowiedź..."):
        if "aktualny_temat" not in st.session_state:
            st.error("Błąd: Nie wybrano tematu!")
        else:
            # 1. POBIERZ AKTUALNY STAN Z BAZY (żeby nie pracować na starej kopii)
            aktualny_profil = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)
            if aktualny_profil:
                st.session_state.postep_tematow = aktualny_profil.get("postep_tematow", {})

            # 2. SPRAWDŹ STATUS
            stan_tematu = st.session_state.postep_tematow.get(st.session_state.aktualny_temat)
            status = stan_tematu.get("status") if isinstance(stan_tematu, dict) else stan_tematu
            
            # 3. ZMIEŃ NA "W trakcie" TYLKO JEŚLI JEST "Nie rozpoczęte"
            if status == "Nie rozpoczęte" or status is None:
                st.session_state.postep_tematow[st.session_state.aktualny_temat] = "W trakcie"
                zapisz_profil_w_chmurze() # Zapisz do bazy!
            
            # 4. KONTYNUUJ LOGIKĘ CZATU
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.spinner("Myślę..."):
                odp = zapytaj_ai(st.session_state.messages, st.session_state.aktualny_temat)
                
                if odp.startswith("❌"):
                    st.error(f"AI zwróciło błąd: {odp}")
                if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                    st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                    
                    # Zapisz do sesji i do bazy
                    if "teorie_lekcji" not in st.session_state: st.session_state.teorie_lekcji = {}
                    st.session_state.teorie_lekcji[st.session_state.aktualny_temat] = st.session_state.teoria_lekcji
                    zapisz_profil_w_chmurze() # Teraz teoria zostanie zapisana na stałe
                else:
                    # Logika licznika
                    if "[ZALICZONE]" in odp:
                        st.session_state.licznik_zadan = st.session_state.get("licznik_zadan", 0) + 1
                    
                    st.session_state.messages.append({"role": "assistant", "content": odp.replace("[ZALICZONE]", "").strip()})
                    
                    # Zapis historii
                    if not isinstance(st.session_state.get("historia_czatow"), dict):
                        st.session_state.historia_czatow = {}
                    st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
                    
                    zapisz_profil_w_chmurze()
                    st.rerun()
