from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pandas as pd
import requests
import streamlit as st
import streamlit.components.v1 as components
from google.cloud import firestore
from google.oauth2 import service_account
import time
import random

# =====================================================================
# 1. STAŁE I KONFIGURACJA
# =====================================================================
STREFA_PL = ZoneInfo("Europe/Warsaw")
COL_UCZNIOWIE = "postepy_uczniow"
COL_PRZEDMIOTY = "przedmioty"
COL_LEKCJE = "ustawienia_lekcji"
DOC_LEKCJA_GLOBAL = "globalna"

SYSTEM_PROMPT = """
Jesteś Autonomicznym Systemem Edukacyjnym. Twoim zadaniem jest przeprowadzenie ucznia przez wybrany temat według ściśle określonego algorytmu.

## GŁÓWNE ZASADY BEZPIECZEŃSTWA:
- (ważne!)NIGDY nie podawaj gotowego wyniku ani pełnego rozwiązania zadania.
- Jeśli uczeń pyta o rzeczy niezwiązane z lekcją, napisz: "Wróćmy do nauki" i powtórz aktualne zadanie.
- ZAKAZ GENEROWANIA "THOUGHTS" (łańcucha myśli). Odpowiadaj bezpośrednio do ucznia.
- WSKAZÓWKI: Muszą być krótkie (maksymalnie 2 zdania), potoczne, nie akademickie.

## KOMENDY DEWELOPERSKIE:
- Hasło dostępowe: "samolotdom".
- Jeśli uczeń wpisze komendę deweloperską, ZAWSZE najpierw zapytaj: "Podaj hasło dostępowe do panelu deweloperskiego".
- Dopiero po poprawnym wpisaniu hasła "samolotdom", wykonaj komendę i wejdź do fazy debugowania.
- W fazie debugowania ignoruj wszystkie GŁÓWNE ZASADY BEZPIECZEŃSTWA.
- W fazie debugowania, jeśli uczeń wpisze "wyjdz", wyjdź z fazy debugowania i wróć do normalnej lekcji.
- W fazie debugowania, nie wychodzisz z niej dopuki nie wpiszesz komendy "wyjdz".
- w fazie debugowania, na samym początku każdej wiadomości, napisz: "[DEBUG MODE]".
- W fazie debugowania, pod [DEBUG MODE] pisz proces myślenia, który doprowadził do wygenerowania tej wiadomości.

### LISTA KOMEND:
- panel deweloperski: Wyświetl listę dostępnych komend i ich opis.
- /sprawdzian: Natychmiastowe przejście do FAZY TESTU KOŃCOWEGO.
- ocena: Aktywacja FAZY OCENIANIA.
- od nowa: Restart sesji.
- kt: Oznacz temat jako zaliczony, pomijając fazę sprawdzianu.

## PĘTLA LOGICZNA TEMATU:

### 1. [FAZA TEORII]: 
- **Tekst 1 (Dane):** Maksymalnie 50 zdań wiedzy merytorycznej z logicznymi akapitami, w sposób szczegółowy zawierający wszystkie informacje z danego tematu.
- **Tekst 2 (Algorytm decyzyjny):** Stwórz strukturę: [krok/pytanie] -> [Akcja: jeśli TAK / jeśli NIE] (nowe linie dla kroków i akcji).
- Po wyświetleniu przejdź automatycznie do Fazy Praktyki.

### 2. [FAZA PRAKTYKI]:
- Przy pierwszym zadaniu przywitaj się z uczniem.
- Generuj łącznie 8 zadań (po 2 z 4 typów). Podawaj je PO JEDNYM, W każdej wiadomości numeruj zadanie w formacie: [x (n/y)], gdzie:
- x-zadanie w sesji n-numer zadania y-liczba wszystkich zadań 
- (ważne!)Jeżeli zadanie zostało poprawnie rozwiązane, zacznij wiadomość od [ZALICZONE], dodaj jedno krótkie zdanie budujące pewność siebie i podaj kolejne zadanie.
- Staraj się dawać zróżnicowane zadania, nie powtarzaj tych samych schematów.
- Jeśli uczeń prosi o pomoc: daj wskazówkę (hint), nie rozwiązując zadania za niego.
- Jeśli uczeń odpowie ŹLE: Wyjaśnij krótko dlaczego (używając algorytmu), napisz "Odłóżmy to zadanie na koniec", przesuń to zadanie na koniec kolejki i przejdź do kolejnego.
-jezeli uczeni robi ponownie źle zrobione zadania, zmień treść zdania, zachowując ten sam typ. Pociesz ucznia i naprowadzaj go, ale nigdy nie dawaj gotowych odpowiedzi.
-po zakoniczeniu fazy praktyki zapytaj sie czunia czy chce powtuzyć fazę pratyki.
-jezeli powie nie, przechodzisz do fazy testu końcowego.

### 3. [FAZA TESTU KOŃCOWEGO]: 
- (ważne!) W wiadomości z testem napisz na samym początku [SPRAWDZIAN].
- Powiedz: "Czas na test sprawdzający. Teraz pracujesz samodzielnie, bez moich wskazówek." Wygeneruj 4 zadania (po jednym z każdego typu).
- Masz zakaz podawania wskazówek i podpowiedzi. Uczeń musi samodzielnie rozwiązać test, ale możesz wyjaśniać nieścisłości w treści zadań, jeśli uczeń o to zapyta.
- **PROCEDURA ODDANIA:** Gdy uczeń zgłosi chęć oddania testu, MASZ ZAKAZ sprawdzania wyników od razu. Wyświetl tylko: "Czy na pewno chcesz oddać sprawdzian? Napisz TAK lub NIE."
- **REAKCJA NA WYBÓR:** -> "NIE": Napisz: "Dobrze, spróbuj jeszcze raz pomyśleć", i wyświetl test ponownie.
  -> "TAK": Sprawdź test i na początku wiadomości ze sprawdzzeniem napisz [KONIEC SPRAWDZIANU].
    * 100% punktów -> Wyświetl: "GRATULACJE! Temat ZALICZONY. Masz czas wolny, możesz zrobić następny temat albo i nie."
    * <100% punktów -> Wyświetl: "Test niezaliczony na 100%. Pomijamy ten temat na później" + wyjaśnij błędy. Oznacz temat jako "POMINIĘTY".
"""

# =====================================================================
# 2. BAZA DANYCH I CACHOWANE FUNKCJE POMOCNICZE
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

@st.cache_data(ttl=10)
def wczytaj_profil_z_chmury(identyfikator: str):
    try:
        doc = db.collection(COL_UCZNIOWIE).document(identyfikator).get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        st.error(f"Nie udało się wczytać profilu: {e}")
        return {}

def czysc_cache_profilu():
    wczytaj_profil_z_chmury.clear()

def sprawdz_aktywnosc_lekcji() -> bool:
    try:
        status_lekcji = db.collection(COL_LEKCJE).document(DOC_LEKCJA_GLOBAL).get()
        if status_lekcji.exists:
            godzina_str = status_lekcji.to_dict().get("godzina_blokady")
            if godzina_str:
                godzina_blokady = datetime.strptime(godzina_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=STREFA_PL)
                return datetime.now(STREFA_PL) < godzina_blokady
    except Exception:
        pass
    return False

@st.cache_data(ttl=300)
def pobierz_strukture() -> dict:
    try:
        docs = db.collection(COL_PRZEDMIOTY).stream()
        struktura = {}
        for doc in docs:
            dane = doc.to_dict().get("lista_tematow", [])
            struktura[doc.id] = dane if isinstance(dane, list) else [str(dane)]
        return struktura
    except Exception as e:
        st.error(f"Błąd wczytywania struktury: {e}")
        return {}

def ustaw_stan_testu(w_trakcie: bool):
    if "zalogowany_id" in st.session_state:
        db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).set(
            {"w_trakcie_testu": w_trakcie}, merge=True
        )
        czysc_cache_profilu()

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
        czysc_cache_profilu()
    except Exception as e:
        st.error(f"Błąd zapisu danych: {e}")

def _parsuj_czas_blokady(raw_blokada) -> datetime:
    if isinstance(raw_blokada, datetime):
        return raw_blokada.replace(tzinfo=STREFA_PL) if raw_blokada.tzinfo is None else raw_blokada.astimezone(STREFA_PL)
    try:
        return datetime.fromisoformat(str(raw_blokada)).astimezone(STREFA_PL)
    except Exception:
        return datetime.now(STREFA_PL)

# =====================================================================
# 3. STRAŻNIK DOSTĘPU
# =====================================================================
if "zalogowany_id" not in st.session_state:
    st.switch_page("app.py")
if st.session_state.get("role") != "uczen":
    st.error("Nie masz uprawnień uczniowskich.")
    st.stop()

lekcja_aktywna = sprawdz_aktywnosc_lekcji()
profil_aktualny = wczytaj_profil_z_chmury(st.session_state.zalogowany_id)

if not lekcja_aktywna and profil_aktualny.get("w_trakcie_testu"):
    ustaw_stan_testu(False)
    st.rerun()

# =====================================================================
# 4. SYSTEM ANTY-CHEAT
# =====================================================================
# CSS do ukrycia wyzwalacza ponownego przeładowania
st.markdown("""
<style>
    div[class*="st-key-btn_ac_rerun_hidden"],
    .st-key-btn_ac_rerun_hidden {
        display: none !important;
        height: 0px !important;
        margin: 0px !important;
        padding: 0px !important;
        overflow: hidden !important;
        position: absolute !important;
        pointer-events: none !important;
    }
</style>
""", unsafe_allow_html=True)

if st.button("RERUN_ANTYCHEAT_TRIGGER", key="btn_ac_rerun_hidden"):
    try:
        db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).set({
            "sygnal_oszustwa": True
        }, merge=True)
        czysc_cache_profilu()
    except Exception as e:
        st.error(f"Błąd zgłoszenia oszustwa: {e}")
    st.rerun()

# Reakcja na sygnał oszustwa
if profil_aktualny.get("sygnal_oszustwa") is True:
    teraz_pl = datetime.now(STREFA_PL)
    czas_kary = teraz_pl + timedelta(minutes=45)
    try:
        db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).set({
            "sygnal_oszustwa": False,
            "blokada_do": czas_kary
        }, merge=True)
        czysc_cache_profilu()
        profil_aktualny["blokada_do"] = czas_kary
        profil_aktualny["sygnal_oszustwa"] = False
    except Exception as e:
        st.error(f"Błąd przetwarzania kary: {e}")

# Egzekwowanie blokady czasowej
if profil_aktualny.get("blokada_do"):
    czas_blokady = _parsuj_czas_blokady(profil_aktualny["blokada_do"])
    teraz = datetime.now(STREFA_PL)
    
    if czas_blokady > teraz:
        st.error("🚨 WYKRYTO OPUSZCZENIE KARTY LUB UTRATĘ FOKUSU! 🚨")
        st.warning(f"Twój dostęp do lekcji został zablokowany do godziny: **{czas_blokady.strftime('%H:%M:%S')}**")
        st.info("⏳ czas blokady: 45min.")
        st.stop()

# Wstrzykiwanie skryptu śledzącego JS podczas testu
w_trakcie_testu = profil_aktualny.get("w_trakcie_testu", False)
if lekcja_aktywna and w_trakcie_testu:
    components.html("""
    <script>
        let oszustwoWyslane = false;
        const targetDoc = window.parent ? window.parent.document : document;
        const targetWin = window.parent ? window.parent : window;

        function znajdzPrzycisk() {
            const dokumenty = [document];
            try {
                if (window.parent && window.parent !== window) dokumenty.push(window.parent.document);
            } catch (e) {
                console.warn("Brak dostępu do window.parent.document", e);
            }
            try {
                if (window.top && window.top !== window) dokumenty.push(window.top.document);
            } catch (e) {
                console.warn("Brak dostępu do window.top.document", e);
            }

            for (const doc of dokumenty) {
                try {
                    let btn = doc.querySelector('.st-key-btn_ac_rerun_hidden button') || 
                              doc.querySelector('[class*="st-key-btn_ac_rerun_hidden"] button');
                    if (btn) return btn;

                    const buttons = doc.querySelectorAll('button');
                    for (let b of buttons) {
                        if (b.innerText && b.innerText.includes("RERUN_ANTYCHEAT_TRIGGER")) {
                            return b;
                        }
                    }
                } catch (e) {
                    console.warn("Błąd wyszukiwania przycisku w dokumencie:", e);
                }
            }
            return null;
        }

        function wyzwolRerunStreamlit() {
            const btn = znajdzPrzycisk();
            if (btn) {
                btn.click();
            } else if (targetWin && targetWin.location) {
                targetWin.location.reload();
            }
        }

        function zglosOszustwo() {
            if (oszustwoWyslane) return;
            oszustwoWyslane = true;
            wyzwolRerunStreamlit();
        }

        targetDoc.addEventListener("visibilitychange", function() {
            if (targetDoc.visibilityState === 'hidden') {
                zglosOszustwo();
            } else if (targetDoc.visibilityState === 'visible' && oszustwoWyslane) {
                wyzwolRerunStreamlit();
            }
        });

        targetWin.addEventListener("focus", function() {
            if (oszustwoWyslane) wyzwolRerunStreamlit();
        });

        targetWin.addEventListener("beforeunload", function(e) {
            zglosOszustwo();
        });
    </script>
    """, height=0)

# =====================================================================
# 5. KOMUNIKACJA Z MODELOWĄ WARSTWĄ AI
# =====================================================================
import time
import random

def zapytaj_ai(historia_rozmowy: list, temat_kontekst: str, licznik_zadan: int) -> str:
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
    
    # ZABEZPIECZENIE RÓL: Gemini wymaga, aby pierwsza wiadomość w historii należała do 'user'
    if contents and contents[0]["role"] == "model":
        contents.insert(0, {"role": "user", "parts": [{"text": "Rozpoczynamy lekcję."}]})

    # UNIKALNE ZIARNO: Gwarantuje unikalność pytań przy każdym wywołaniu
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
            "parts": [{"text": f"{SYSTEM_PROMPT}\n\n{dynamiczny_kontekst}"}]
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
            return response.json()['candidates'][0]['content']['parts'][0]['text']
        return f"❌ Błąd API ({response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Błąd połączenia: {str(e)}"
# =====================================================================
# 6. PASEK BOCZNY (MENU I KONTROLA SESJI)
# =====================================================================
if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_strukture()

with st.sidebar:
    if w_trakcie_testu:
        st.error("🔒 TRWA TEST KOŃCOWY!")
        st.caption("Wylogowanie oraz zmiana tematów są zablokowane do czasu ukończenia sprawdzianu.")
    else:
        if st.button("Wyloguj", use_container_width=True):
            st.session_state.clear()
            st.switch_page("app.py")

    st.header("🏫 Dziennik Ucznia")
    
    if not st.session_state.struktura_dydaktyczna:
        st.warning("Brak przedmiotów w bazie.")
        st.stop()
        
    wybrany_przedmiot = st.selectbox(
        "Wybierz przedmiot:", 
        list(st.session_state.struktura_dydaktyczna.keys()),
        disabled=w_trakcie_testu
    )
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
    
    tematy_do_wyboru = [
        t for t in dostepne 
        if st.session_state.get("postep_tematow", {}).get(t, {}).get("status") != "ZALICZONY"
    ]
    
    if not tematy_do_wyboru:
        st.success("Wszystkie tematy zostały zaliczone! 🎉")
    else:
        wybor_tematu = st.selectbox(
            "Wybierz temat:", 
            tematy_do_wyboru, 
            key="glowny_wybor_tematu",
            disabled=w_trakcie_testu
        )
        
        if st.button("Rozpocznij lekcję", use_container_width=True, disabled=w_trakcie_testu):
            if not lekcja_aktywna:
                st.error("Nauczyciel nie aktywował jeszcze lekcji.")
            else:
                st.session_state.aktualny_temat = wybor_tematu
                st.session_state.teorie_lekcji = profil_aktualny.get("teorie_lekcji", {})
                st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu)
                
                stan_tematu = profil_aktualny.get("postep_tematow", {}).get(wybor_tematu, {})
                st.session_state.licznik_zadan = stan_tematu.get("licznik", 0) if isinstance(stan_tematu, dict) else 0
                if isinstance(stan_tematu, dict) and stan_tematu.get("ma_sprawdzian"):
                    ustaw_stan_testu(True)
                
                historia = profil_aktualny.get("historia_czatow", {})
                st.session_state.messages = historia.get(wybor_tematu, []) if isinstance(historia, dict) else []
                
                if not st.session_state.messages:
                    with st.spinner("Inicjalizacja lekcji z AI..."):
                        instrukcja = "Rozpoczynamy lekcję. Wyślij odpowiedź w formacie: [TEORIA]Treść teorii[TEORIA_KONIEC] [ZADANIE]Treść zadania"
                        
                        # Zapisujemy intencję użytkownika, żeby utrzymać prawidłowy priorytet ról w API
                        st.session_state.messages = [{"role": "user", "content": instrukcja}]
                        
                        odp = zapytaj_ai(st.session_state.messages, wybor_tematu, 0)
                        
                        if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                            st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                            if "teorie_lekcji" not in st.session_state:
                                st.session_state.teorie_lekcji = {}
                            st.session_state.teorie_lekcji[wybor_tematu] = st.session_state.teoria_lekcji
                            
                            # Nadpisujemy historię czatu czystym zadaniem od AI
                            zadanie_tresc = odp.split("[ZADANIE]")[1].strip()
                            st.session_state.messages = [{"role": "assistant", "content": zadanie_tresc}]
                            zapisz_profil_w_chmurze()
                        else:
                            st.session_state.teoria_lekcji = odp
                            st.session_state.messages = [{"role": "assistant", "content": odp}]
                            zapisz_profil_w_chmurze()
                st.rerun()

# =====================================================================
# 7. GŁÓWNY PANEL APLIKACJI
# =====================================================================
if "aktualny_temat" not in st.session_state:
    st.title("Cześć Uczniu, w czym mogę pomóc?")
    st.subheader("Twój postęp (ostatnie 4 tygodnie)")
    
    dzis = datetime.now()
    tygodnie_dane = {"Tydzień 1": 0, "Tydzień 2": 0, "Tydzień 3": 0, "Tydzień 4": 0}

    for temat, dane in st.session_state.get("postep_tematow", {}).items():
        if isinstance(dane, dict) and dane.get("status") == "ZALICZONY" and dane.get("data"):
            try:
                data_uko = datetime.strptime(dane["data"], "%Y-%m-%d")
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
    
    # --- PRZYCISK WEZWANIA POMOCY (SOS) ---
    stan_pomocy = profil_aktualny.get("potrzebuje_pomocy", False)

    if stan_pomocy:
        if st.button("🟢 Odwołaj wezwanie pomocy", use_container_width=True):
            db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).update({
                "potrzebuje_pomocy": False,
                "aktualny_temat_problemu": ""
            })
            czysc_cache_profilu()
            st.rerun()
    else:
        if st.button("🚨 WEZWIJ NAUCZYCIELA DO POMOCY", use_container_width=True):
            temat = st.session_state.aktualny_temat
            postepy = profil_aktualny.get("postep_tematow", {})
            
            if temat not in postepy:
                postepy[temat] = {"status": "W trakcie", "licznik_sos": 0}
            
            if isinstance(postepy[temat], dict):
                postepy[temat]["licznik_sos"] = postepy[temat].get("licznik_sos", 0) + 1
            
            db.collection(COL_UCZNIOWIE).document(st.session_state.zalogowany_id).update({
                "potrzebuje_pomocy": True,
                "aktualny_temat_problemu": temat,
                "postep_tematow": postepy
            })
            czysc_cache_profilu()
            st.rerun()

    # --- WERYFIKACJA STANU LEKCJI I INTERFEJS CZATU ---
    if not lekcja_aktywna:
        st.error("🔒 Lekcja zakończona! Czat i zadania zostały zablokowane.")
        if st.session_state.get("teoria_lekcji"):
            with st.expander("📘 MATERIAŁY (Tylko podgląd)", expanded=True):
                st.markdown(st.session_state.teoria_lekcji)
    else:
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
            stan_tematu = st.session_state.postep_tematow.get(st.session_state.aktualny_temat, {})
            status = stan_tematu.get("status") if isinstance(stan_tematu, dict) else stan_tematu
            
            if status in ["Nie rozpoczęte", None]:
                st.session_state.postep_tematow[st.session_state.aktualny_temat] = {"status": "W trakcie"}
                zapisz_profil_w_chmurze() 
            
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.spinner("Myślę..."):
                obecny_licznik = st.session_state.get("licznik_zadan", 0)
                temat_aktyw = st.session_state.aktualny_temat
                odp = zapytaj_ai(st.session_state.messages, temat_aktyw, obecny_licznik)
                
                if odp.startswith("❌"):
                    st.error(f"AI zwróciło błąd: {odp}")
                else:
                    if "[SPRAWDZIAN]" in odp:
                        if "postep_tematow" not in st.session_state:
                            st.session_state.postep_tematow = {}
                        if not isinstance(st.session_state.postep_tematow.get(temat_aktyw), dict):
                            st.session_state.postep_tematow[temat_aktyw] = {"status": "W trakcie", "licznik": obecny_licznik}
                        st.session_state.postep_tematow[temat_aktyw]["ma_sprawdzian"] = True
                        ustaw_stan_testu(True)
                        odp = odp.replace("[SPRAWDZIAN]", "").strip()
                        
                    if "[KONIEC SPRAWDZIANU]" in odp:
                        ustaw_stan_testu(False)
                        if "postep_tematow" in st.session_state and isinstance(st.session_state.postep_tematow.get(temat_aktyw), dict):
                            st.session_state.postep_tematow[temat_aktyw]["ma_sprawdzian"] = False
                        odp = odp.replace("[KONIEC SPRAWDZIANU]", "").strip()

                    if "[ZALICZONE]" in odp:
                        st.session_state.licznik_zadan = obecny_licznik + 1
                        
                        if st.session_state.licznik_zadan >= 8:
                            st.session_state.postep_tematow[st.session_state.aktualny_temat] = {
                                "status": "ZALICZONY",
                                "data": datetime.now().strftime("%Y-%m-%d"),
                                "licznik": st.session_state.licznik_zadan
                            }
                            st.success("🎉 GRATULACJE! Temat ZALICZONY. Masz czas wolny, możesz zrobić następny temat albo i nie.")
                    
                    if st.session_state.licznik_zadan >= 8 and "GRATULACJE! Temat ZALICZONY" in odp:
                        st.balloons()
                        st.session_state.postep_tematow[st.session_state.aktualny_temat] = {
                            "status": "ZALICZONY",
                            "data": datetime.now().strftime("%Y-%m-%d"),
                            "licznik": st.session_state.get("licznik_zadan", 8)
                        }
                    
                    czysta_odp = odp.replace("[ZALICZONE]", "").strip()
                    st.session_state.messages.append({"role": "assistant", "content": czysta_odp})
                    
                    if not isinstance(st.session_state.get("historia_czatow"), dict):
                        st.session_state.historia_czatow = {}
                    st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
                    
                    zapisz_profil_w_chmurze()
                    st.rerun()