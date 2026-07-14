import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- KONFIGURACJA ---
STREFA_PL = ZoneInfo("Europe/Warsaw")
# Definicja stałych - koniec z literówkami w nazwach kolekcji!
COL_POSTEPY = "postepy_uczniow"
COL_LEKCJE = "ustawienia_lekcji"
DOC_LEKCJA_GLOBAL = "globalna"

# --- ZARZĄDZANIE POŁĄCZENIEM ---
@st.cache_resource
def get_db():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()

# --- FUNKCJE POMOCNICZE (LOGIKA BAZY) ---
def pobierz_uczniow():
    try:
        return list(db.collection(COL_POSTEPY).where("rola", "==", "uczen").stream())
    except Exception as e:
        st.error("Błąd połączenia z bazą uczniów.")
        return []

def zresetuj_dane_ucznia(uczen_id):
    doc_ref = db.collection(COL_POSTEPY).document(uczen_id)
    doc_ref.update({
        "postep_tematow": {},
        "historia_czatow": {},
        "teorie_lekcji": {},
        "potrzebuje_pomocy": False,
        "aktualny_temat_problemu": ""
    })

# --- STRAŻNIK ---
if "zalogowany_id" not in st.session_state or st.session_state.get("role") != "nauczyciel":
    st.switch_page("app.py")

# --- UI: SIDEBAR ---
@st.fragment(run_every=3)
def render_sidebar():
    st.title("👨‍🏫 Nauczyciel")
    st.write(f"Zalogowano: **{st.session_state.get('zalogowany_id')}**")
    
    if st.button("Wyloguj"):
        st.session_state.clear()
        st.rerun()
    
    st.markdown("---")
    st.subheader("Lista uczniów")
    
    uczniowie = pobierz_uczniow()
    for u in uczniowie:
        dane = u.to_dict()
        if st.button(f"{'🚨' if dane.get('potrzebuje_pomocy') else '👤'} {u.id}", key=f"btn_{u.id}", use_container_width=True):
            st.session_state.wybrany_uczen_id = u.id
            st.rerun()

with st.sidebar:
    render_sidebar()

# --- UI: GŁÓWNY PANEL ---
st.title("Panel Nauczyciela")

# Zarządzanie czasem
status_lekcji_ref = db.collection(COL_LEKCJE).document(DOC_LEKCJA_GLOBAL)
status_lekcji = status_lekcji_ref.get()

if status_lekcji.exists:
    dane_lekcji = status_lekcji.to_dict()
    if dane_lekcji.get("godzina_blokady"):
        godzina_blokady = datetime.strptime(dane_lekcji["godzina_blokady"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=STREFA_PL)
        if datetime.now(STREFA_PL) < godzina_blokady:
            st.success(f"🟢 Lekcja AKTYWNA do: {godzina_blokady.strftime('%H:%M:%S')}")
        else:
            st.error("🔴 Czas lekcji minął.")

if st.button("Aktywuj lekcję na 1 godzinę"):
    nowa_blokada = datetime.now(STREFA_PL) + timedelta(hours=1)
    status_lekcji_ref.set({"godzina_blokady": nowa_blokada.strftime("%Y-%m-%d %H:%M:%S")})
    st.rerun()

# Wyświetlanie szczegółów ucznia
if "wybrany_uczen_id" in st.session_state:
    uczen_id = st.session_state.wybrany_uczen_id
    doc = db.collection(COL_POSTEPY).document(uczen_id).get()
    
    if doc.exists:
        dane = doc.to_dict()
        st.header(f"Podgląd ucznia: {uczen_id}")
        
        if dane.get("potrzebuje_pomocy"):
            st.error(f"🚨 UCZEŃ PROSI O POMOC: {dane.get('aktualny_temat_problemu')}")
        
        # Wyświetlanie postępów
        for temat, stan in dane.get('postep_tematow', {}).items():
            status = stan.get("status") if isinstance(stan, dict) else stan
            licznik_sos = stan.get("licznik_sos", 0) if isinstance(stan, dict) else 0
            sos_text = f" | 🆘 SOS: {licznik_sos}" if licznik_sos > 0 else ""
            
            if status == "ZALICZONY":
                st.success(f"✅ {temat} - ZALICZONY{sos_text}")
            elif status == "W trakcie":
                st.info(f"🔄 {temat} - W trakcie ({stan.get('licznik', 0)}/8){sos_text}")
            else:
                st.error(f"❌ {temat} - {status}{sos_text}")
                
        if st.button(f"Zresetuj dane ucznia {uczen_id}"):
            zresetuj_dane_ucznia(uczen_id)
            st.rerun()
    else:
        st.warning("Uczeń nie istnieje.")