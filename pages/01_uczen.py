import streamlit as st
import requests
from google.oauth2 import service_account
from google.cloud import firestore
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components
from streamlit_js_eval import streamlit_js_eval

# =====================================================================
# 1. STAŁE (Muszą być załadowane jako pierwsze)
# =====================================================================
STREFA_PL = ZoneInfo("Europe/Warsaw")
COL_UCZNIOWIE = "postepy_uczniow"
COL_PRZEDMIOTY = "przedmioty"
COL_LEKCJE = "ustawienia_lekcji"
DOC_LEKCJA_GLOBAL = "globalna"

# =====================================================================
# 2. POŁĄCZENIE Z BAZĄ DANYCH I FUNKCJE BAZODANOWE
# =====================================================================
@st.cache_resource
def get_db():
    try:
        key_dict = st.secrets["connections"]["firestore"]
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project=key_dict["project_id"])
    except Exception as e:
        st.error(f"❌ KRYTYCZNY BŁĄD AUTORYZACJI FIRESTORE: {str(e)}")
        st.stop()

db = get_db()

def wczytaj_profil_z_chmury(identyfikator):
    try:
        doc = db.collection(COL_UCZNIOWIE).document(identyfikator).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        st.error(f"Nie udało się wczytać profilu: {e}")
        return None

def sprawdz_aktywnosc_lekcji():
    try:
        status_lekcji = db.collection(COL_LEKCJE).document(DOC_LEKCJA_GLOBAL).get()
        if status_lekcji.exists:
            godzina_blokady_str = status_lekcji.to_dict().get("godzina_blokady")
            if godzina_blokady_str:
                godzina_blokady = datetime.strptime(godzina_blokady_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=STREFA_PL)
                return datetime.now(STREFA_PL) < godzina_blokady
    except Exception:
        pass
    return False

@st.cache_data(ttl=300)
def pobierz_strukture():
    try:
        docs = db.collection(COL_PRZEDMIOTY).stream()
        struktura = {}
        for doc in docs:
            dane = doc.to_dict().get("lista_tematow", [])
            struktura[doc.id] = dane if isinstance(dane, list) else [str(dane)]
        return struktura
    except Exception as e:
        st.error(f"Błąd struktury: {e}")
        return {}

def czy_temat_niezaliczone(t):
    dane = st.session_state.get("postep_tematow", {}).get(t, "Nie rozpoczęte")
    status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
    return status != "ZALICZONY"

# =====================================================================
# 3. STRAŻNIK DOSTĘPU I INICJALIZACJA PROFILU
# =====================================================================
if "zalogowany_id" not in st.session_state:
    st.switch_page("app.py")
if st.session_state.get("role") != "uczen":
    st.error("Nie masz uprawnień uczniowskich.")
    st.stop()

# Pobieramy profil, zanim użyje go anty-cheat!
lekcja_aktywna = sprawdz_aktywnosc_lekcji()
profil_aktualny = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)

# =====================================================================
# SYSTEM ANTY-CHEAT (DETEKCJA I EGZEKWOWANIE KARY)
# =====================================================================

# 1. REAKCJA PYTHONA NA SYGNAŁ Z BAZY DANYCH
# Jeśli JS zapisał w bazie sygnał oszustwa, Python przetwarza go i zamienia na twardą blokadę czasową
if profil_aktualny and profil_aktualny.get("sygnal_oszustwa") is True:
    czas_kary = datetime.now(STREFA_PL) + timedelta(minutes=45)
    try:
        # Nadpisujemy flagę sygnału i ustawiamy oficjalną godzinę blokady
        db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).set({
            "sygnal_oszustwa": False,
            "blokada_do": czas_kary
        }, merge=True)
        # Odświeżamy profil w pamięci podręcznej podręcznej sesji
        profil_aktualny["blokada_do"] = czas_kary
        profil_aktualny["sygnal_oszustwa"] = False
    except Exception as e:
        st.error(f"Błąd przetwarzania kary: {e}")

# 2. BRAMKA LOGICZNA - WERYFIKACJA BLOKADY
if profil_aktualny and profil_aktualny.get("blokada_do"):
    blokada = profil_aktualny["blokada_do"]
    
    # Normalizacja dla obiektów typu Datetime z Firestore vs strefa PL
    if isinstance(blokada, datetime):
        czas_blokady = blokada
    else:
        czas_blokady = blokada.replace(tzinfo=STREFA_PL) 
        
    if czas_blokady > datetime.now(STREFA_PL):
        st.error("🚨 WYKRYTO OPUSZCZENIE KARTY LUB UTRATĘ FOKUSU! 🚨")
        st.warning(f"Twój dostęp do lekcji został zablokowany do: {czas_blokady.strftime('%H:%M:%S')}")
        st.stop()

# 3. WSTRZYKIWANIE SKRYPTU DETEKCJI (BEZPOŚREDNI STRZAŁ DO REST API)
# Wyciągamy Project ID dynamicznie z sekretów, żeby skrypt JS wiedział, gdzie uderzyć
try:
    project_id = st.secrets["connections"]["firestore"]["project_id"]
except Exception:
    project_id = "twoj-projekt-firestore" # fallback

if lekcja_aktywna and "zalogowany_id" in st.session_state:
    user_doc_id = st.session_state.zalogowany_id
    
    st.components.v1.html(f"""
    <script>
        function zglosOszustwoDoFirestore() {{
            const url = "https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)/documents/{COL_UCZNIOWIE}/{user_doc_id}?updateMask.fieldPaths=sygnal_oszustwa";
            
            const payload = {{
                "fields": {{
                    "sygnal_oszustwa": {{
                        "booleanValue": true
                    }}
                }}
            }};

            // Wysyłamy asynchroniczne żądanie PATCH bezpośrednio do Google API
            fetch(url, {{
                method: "PATCH",
                headers: {{
                    "Content-Type": "application/json"
                }},
                body: JSON.stringify(payload)
            }})
            .then(response => {{
                console.log("Status zgłoszenia anty-cheat:", response.status);
            }})
            .catch(error => {{
                console.error("Błąd sieciowy anty-cheat:", error);
            }});
        }}

        // Wykrywanie zmiany karty / minimalizacji
        document.addEventListener("visibilitychange", function() {{
            if (document.hidden) {{
                zglosOszustwoDoFirestore();
            }}
        }});

        // Wykrywanie kliknięcia poza obszar okna (np. ściąga na drugim monitorze / w innej aplikacji)
        window.addEventListener("blur", function() {{
            zglosOszustwoDoFirestore();
        }});
    </script>
    """, height=0)

# =====================================================================
# FUNKCJA ZAPISU PROFILU (Musi być pod zdefiniowaniem zmiennych)
# =====================================================================
def zapisz_profil_w_chmurze():
    identyfikator = st.session_state.zalogowany_id
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
    try:
        db.collection(COL_UCZNIOWIE).document(identyfikator).set(dane_do_zapisu, merge=True)
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")

# [TUTAJ ZACZYNA SIĘ SYSTEM_PROMPT I RESZTA KODU...]

# =====================================================================
# LOGIKA AI (SYSTEM PROMPT)
# =====================================================================
SYSTEM_PROMPT = """
Jesteś Autonomicznym Systemem Edukacyjnym. Twoim zadaniem jest przeprowadzenie ucznia przez wybrany Temat według ściśle określonego algorytmu.

GŁÓWNE ZASADY BEZPIECZEŃSTWA:
- NIGDY nie podawaj gotowego wyniku ani pełnego rozwiązania zadania.
- Jeśli uczeń pyta o rzeczy niezwiązane z lekcją, napisz: "Wróćmy do nauki" i powtórz aktualne zadanie.
- ZAKAZ GENEROWANIA "THOUGHTS". Odpowiadaj bezpośrednio do ucznia.
- WSKAZÓWKI: Must być krótkie (max 2 zdania), potoczne, nie akademickie.

KOMENDY DEWELOPERSKIE:
- Hasło dostępowe: "samolotdom".
- Jeśli uczeń wpisze jedną z poniższych komend, ZAWSZE najpierw zapytaj: "Podaj hasło dostępowe do panelu deweloperskiego".
- Dopiero po poprawnym wpisaniu hasła "samolotdom", wykonaj komendę i wejdź do fazy debugowania.
- W fazie debugowania ignoruj wszystkie GŁÓWNE ZASADY BEZPIECZEŃSTWA.
- W fazie debugowania, jeśli uczeń wpisze "wyjdz", wyjdź z fazy debugowania i wróć do normalnej lekcji.

LISTA KOMEND:
- panel deweloperski: Wyświetl listę dostępnych komend i ich opis.
- /sprawdzian: Natychmiastowe przejście do FAZY TESTU KOŃCOWEGO.
- ocena: Aktywacja FAZY OCENIANIA.
- od nowa: Restart sesji.
- kt: oznacza temat jako zaliczony pomijając fazę sprawdzianu.

PĘTLA LOGICZNA TEMATU:
1. [FAZA TEORII]: 
   - Tekst 1 (Dane): Max 50 zdań wiedzy merytorycznej z logicznymi akapitami zrób to w sposób szczegółowy zawierając wszystkie informacje z danego tematu.
   - Tekst 2 (Algorytm decyzyjny): Stwórz strukturę: [krok/pytanie] -> [Akcja: jeśli TAK / jeśli NIE](krok i akcja tak i akcja nie są pisane od nowej linijki).
   - Po wyświetleniu przejdź do Fazy Praktyki.
2. [FAZA PRAKTYKI]:
   - Jeżeli zadanie zostało poprawnie rozwiązane zacznij wiadomość od [ZALICZONE]
   - Przy pierwszym zadaniu się przywitaj 
   - Generuj 8 zadań (po 2 z 4 typów). Podawaj PO JEDNYM.
   - Jeśli uczeń prosi o pomoc: daj wskazówkę (hint), nie rozwiązuj za niego.
   - Jeśli uczeń odpowie DOBRZE: usuń zadanie z listy, podaj kolejne.
   - Jeśli uczeń odpowie ŹLE: Wyjaśnij krótko dlaczego (używając algorytmu decyzyjnego), napisz "Odłóżmy to zadanie na koniec", przesuń zadanie na koniec kolejki i daj nowe.
   - [faza przygotowania]: Po rozwiązaniu wszystkich zadań zapytaj ucznia, czy chce jeszcze poćwiczyć konkretny typ zadania. Poinformuj go że jeżeli chce iść dalej to ma napisać koniec. Jeśli napisze "koniec", przejdź do FAZY TESTU KOŃCOWEGO. Jeśli "NIE", idź tam od razu.
   - Po każdym poprawnie wykonanym zadaniu dodaj jedno krótkie zdanie budujące pewność siebie lub odnieś się do logiki ucznia (np. "Dokładnie tak, świetnie przekształciłeś wzór!")
   - Po źle wykonanym zadaniu pociesz ucznia
   - Przy ponownym rozwiązywaniu źle zrobionego zadania staraj się naprowadzić ucznia
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

def zapytaj_ai(historia_rozmowy, temat_kontekst, licznik_zadan):
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
    
    if licznik_zadan == 0 and len(historia_rozmowy) <= 1:
        dynamiczny_kontekst = f"AKTUALNY TEMAT: {temat_kontekst}\nSTATUS: Początek lekcji. Wygeneruj FAZĘ TEORII, a następnie pierwsze zadanie."
    else:
        dynamiczny_kontekst = f"AKTUALNY TEMAT: {temat_kontekst}\nSTATUS: Uczeń rozwiązał poprawnie {licznik_zadan} z 8 zadań. Jesteś w FAZIE PRAKTYKI. Podaj wyłącznie zadanie, nie powtarzaj teorii."

    payload = {
        "contents": contents,
        "systemInstruction": {"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{dynamiczny_kontekst}"}]}
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 429:
            return "❌ Przeciążenie serwera (429). Spróbuj ponownie za chwilę."
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        return f"❌ Błąd API ({response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Błąd połączenia: {str(e)}"

# =====================================================================
# PASEK BOCZNY
# =====================================================================
if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_strukture()

with st.sidebar:
    if st.button("Wyloguj", use_container_width=True):
        st.session_state.clear()
        st.switch_page("app.py")

    st.header("🏫 Dziennik Ucznia")
    
    if not st.session_state.struktura_dydaktyczna:
        st.warning("Brak przedmiotów w bazie.")
        st.stop()
        
    wybrany_przedmiot = st.selectbox("Wybierz przedmiot:", list(st.session_state.struktura_dydaktyczna.keys()))
    dostepne = st.session_state.struktura_dydaktyczna.get(wybrany_przedmiot, [])
    
    st.subheader("📚 Status tematów")
    
    def priorytet(t):
        dane = st.session_state.get("postep_tematow", {}).get(t, "Nie rozpoczęte")
        s = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        return {"W trakcie": 0, "Nie rozpoczęte": 1, "NIEZALICZONY": 2, "ZALICZONY": 3}.get(s, 4)

    for temat in sorted(dostepne, key=priorytet):
        dane = st.session_state.get("postep_tematow", {}).get(temat, "Nie rozpoczęte")
        status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        
        if status == "ZALICZONY":
            st.success(f"✅ {temat}")
        elif status == "W trakcie":
            st.info(f"🔄 {temat}")
        elif status == "NIEZALICZONY":
            st.error(f"❌ {temat} (niezaliczony)")
        else:
            st.warning(f"🚩 {temat}")
        
    st.markdown("---")
    
    tematy_do_wyboru = [t for t in dostepne if czy_temat_niezaliczone(t)]
    if not tematy_do_wyboru:
        st.success("Wszystkie tematy zostały zaliczone! 🎉")
    else:
        wybor_tematu = st.selectbox("Wybierz temat:", tematy_do_wyboru, key="glowny_wybor_tematu")
        
        if st.button("Rozpocznij lekcję", use_container_width=True):
            if not lekcja_aktywna:
                st.error("Nauczyciel nie aktywował jeszcze lekcji.")
            else:
                st.session_state.aktualny_temat = wybor_tematu
                
                if profil_aktualny and isinstance(profil_aktualny, dict):
                    st.session_state.teorie_lekcji = profil_aktualny.get("teorie_lekcji", {})
                    st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu)
                    
                    stan_tematu = profil_aktualny.get("postep_tematow", {}).get(wybor_tematu)
                    st.session_state.licznik_zadan = stan_tematu.get("licznik", 0) if isinstance(stan_tematu, dict) else 0
                    
                    historia = profil_aktualny.get("historia_czatow", {})
                    st.session_state.messages = historia.get(wybor_tematu, []) if isinstance(historia, dict) else []
                else:
                    st.session_state.teoria_lekcji = None
                    st.session_state.messages = []
                    st.session_state.licznik_zadan = 0
                    
                if not st.session_state.messages:
                    with st.spinner("Inicjalizacja lekcji z AI..."):
                        instrukcja = "Wyślij odpowiedź w formacie: [TEORIA]Treść teorii[TEORIA_KONIEC] [ZADANIE]Treść zadania"
                        odp = zapytaj_ai([{"role": "user", "content": instrukcja}], wybor_tematu, 0)
                        
                        if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                            st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                            if "teorie_lekcji" not in st.session_state:
                                st.session_state.teorie_lekcji = {}
                            st.session_state.teorie_lekcji[wybor_tematu] = st.session_state.teoria_lekcji
                            st.session_state.messages.append({"role": "assistant", "content": odp.split("[ZADANIE]")[1].strip()})
                            zapisz_profil_w_chmurze()
                        else:
                            st.session_state.teoria_lekcji = odp
                st.rerun()

# =====================================================================
# OBSZAR GŁÓWNY APPLICATION VIZ
# =====================================================================
if "aktualny_temat" not in st.session_state:
    st.title("Cześć Uczniu, w czym mogę pomóc?")
    st.subheader("Twój postęp (ostatnie 4 tygodnie)")
    
    dzis = datetime.now()
    tygodnie_dane = {"Tydzień 1": 0, "Tydzień 2": 0, "Tydzień 3": 0, "Tydzień 4": 0}

    for temat, dane in st.session_state.get("postep_tematow", {}).items():
        status = dane.get("status") if isinstance(dane, dict) else dane
        data_str = dane.get("data") if isinstance(dane, dict) else None
        
        if status == "ZALICZONY" and data_str:
            try:
                data_uko = datetime.strptime(data_str, "%Y-%m-%d")
                roznica_dni = (dzis - data_uko).days
                
                if 0 <= roznica_dni < 7:
                    tygodnie_dane["Tydzień 1"] += 1
                elif 7 <= roznica_dni < 14:
                    tygodnie_dane["Tydzień 2"] += 1
                elif 14 <= roznica_dni < 21:
                    tygodnie_dane["Tydzień 3"] += 1
                elif 21 <= roznica_dni < 28:
                    tygodnie_dane["Tydzień 4"] += 1
            except ValueError:
                continue 

    st.bar_chart(pd.DataFrame.from_dict(tygodnie_dane, orient='index', columns=['Ilość']))
        
else:
    st.caption(f"📖 Temat: {st.session_state.aktualny_temat}")
    
    # --- DWUKIERUNKOWY PRZYCISK POMOCY (SOS) ---
    stan_pomocy = profil_aktualny.get("potrzebuje_pomocy", False) if profil_aktualny else False

    if stan_pomocy:
        if st.button("🟢 Odwołaj wezwanie pomocy", use_container_width=True):
            db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).update({
                "potrzebuje_pomocy": False,
                "aktualny_temat_problemu": ""
            })
            st.rerun()
    else:
        if st.button("🚨 WEZWIJ NAUCZYCIELA DO POMOCY", use_container_width=True):
            temat = st.session_state.aktualny_temat
            postepy = profil_aktualny.get("postep_tematow", {}) if profil_aktualny else {}
            
            if temat not in postepy:
                postepy[temat] = {"status": "W trakcie", "licznik_sos": 0}
            
            if isinstance(postepy[temat], dict):
                postepy[temat]["licznik_sos"] = postepy[temat].get("licznik_sos", 0) + 1
            
            db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).update({
                "potrzebuje_pomocy": True,
                "aktualny_temat_problemu": temat,
                "postep_tematow": postepy
            })
            st.rerun()

    # --- WERYFIKACJA STANU LEKCJI I RENDEROWANIE INTERFEJSU ---
    if not lekcja_aktywna:
        st.error("🔒 Lekcja zakończona! Czat i zadania zostały zablokowane.")
        if st.session_state.get("teoria_lekcji"):
            with st.expander("📘 MATERIAŁY (Tylko podgląd)", expanded=True):
                st.markdown(st.session_state.teoria_lekcji)
    else:
        # Interfejs aktywnej lekcji
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
                
                if status in ["Nie rozpoczęte", None]:
                    st.session_state.postep_tematow[st.session_state.aktualny_temat] = {"status": "W trakcie"}
                    zapisz_profil_w_chmurze() 
                
                st.session_state.messages.append({"role": "user", "content": prompt})
                
                with st.spinner("Myślę..."):
                    obecny_licznik = st.session_state.get("licznik_zadan", 0)
                    odp = zapytaj_ai(st.session_state.messages, st.session_state.aktualny_temat, obecny_licznik)
                    
                    if odp.startswith("❌"):
                        st.error(f"AI zwróciło błąd: {odp}")
                    else:
                        if "[ZALICZONE]" in odp:
                            st.session_state.licznik_zadan = obecny_licznik + 1
                            
                            if st.session_state.licznik_zadan >= 8:
                                st.session_state.postep_tematow[st.session_state.aktualny_temat] = {
                                    "status": "ZALICZONY",
                                    "data": datetime.now().strftime("%Y-%m-%d"),
                                    "licznik": st.session_state.licznik_zadan
                                }
                                st.success("🎉 Gratulacje! Temat został zaliczony.")
                        
                        elif "GRATULACJE! Temat ZALICZONY" in odp:
                            st.session_state.postep_tematow[st.session_state.aktualny_temat] = {
                                "status": "ZALICZONY",
                                "data": datetime.now().strftime("%Y-%m-%d"),
                                "licznik": st.session_state.licznik_zadan
                            }
                        
                        czysta_odp = odp.replace("[ZALICZONE]", "").strip()
                        st.session_state.messages.append({"role": "assistant", "content": czysta_odp})
                        
                        if not isinstance(st.session_state.get("historia_czatow"), dict):
                            st.session_state.historia_czatow = {}
                        st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
                        
                        zapisz_profil_w_chmurze()
                        st.rerun()