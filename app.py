import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

# --- UKRYCIE DOMYŚLNEGO MENU STREAMLIT ---
st.markdown("""
    <style>
        [data-testid="stSidebarNav"] {display: none !important;}
    </style>
""", unsafe_allow_html=True)

# --- KONFIGURACJA FIRESTORE ---
def init_firestore():
    if "connections" not in st.secrets:
        st.error("Brak konfiguracji Firestore w secrets.toml!")
        return None
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

st.title("🏫 Logowanie do Systemu")

id_input = st.text_input("Nazwa konta").strip()

# LOGOWANIE
if st.button("Zaloguj"):
    if not db:
        st.error("Błąd połączenia z bazą danych.")
        st.stop()
        
    doc = db.collection("postepy_uczniow").document(id_input).get()
    
    if doc.exists:
        dane = doc.to_dict()
        st.session_state.zalogowany_id = id_input
        st.session_state.user_api_key = dane.get("user_api_key", "")
        st.session_state.role = dane.get("rola", "uczen")
        st.session_state.postep_tematow = dane.get("postep_tematow", {})
        st.session_state.historia_czatow = dane.get("historia_czatow", {})
        
        if st.session_state.role == "nauczyciel":
            st.switch_page("pages/02_nauczyciel.py")
        else:
            st.switch_page("pages/01_uczen.py")
    else:
        st.error("Konto nie istnieje.")

# TWORZENIE KONTA (ZWIJANE)
with st.expander("➕ Utwórz nowe konto"):
    haslo_tworzenia = st.text_input("Hasło systemowe", type="password", key="new_sys_pass")
    typ_konta = st.selectbox("Typ konta", ["uczen", "nauczyciel"])
    nowy_klucz_api = st.text_input("Klucz API Gemini", type="password", key="new_api_key")
    
    if st.button("Zarejestruj konto"):
        if haslo_tworzenia == "TwojeTajneHaslo123":
            if id_input and nowy_klucz_api:
                nowy_profil = {
                    "user_api_key": nowy_klucz_api, 
                    "postep_tematow": {}, 
                    "historia_czatow": {},
                    "rola": typ_konta
                }
                db.collection("postepy_uczniow").document(id_input).set(nowy_profil)
                st.success(f"Konto {id_input} ({typ_konta}) utworzone! Możesz się teraz zalogować.")
            else:
                st.error("Wpisz nazwę konta i klucz API!")
        else:
            st.error("Błędne hasło systemowe!")