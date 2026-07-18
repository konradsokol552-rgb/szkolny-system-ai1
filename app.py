import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

st.set_page_config(page_title="Szkolny System AI", layout="wide")

# 2. Brutalne wycięcie stopki z linkami za pomocą CSS
st.markdown("""
    <style>
    footer {visibility: hidden !important;}
    .stAppDeployButton {display: none !important;}
    </style>
""", unsafe_html=True)

# --- STAŁE ---
COL_UCZNIOWIE = "postepy_uczniow"
HASLO_SYSTEMOWE = "TwojeTajneHaslo123" # W przyszłości przenieś to do st.secrets

# --- KONFIGURACJA CSS ---
st.markdown(
    """
    <style>
        [data-testid="stSidebar"] {
            display: none;
        }
        [data-testid="collapsedSidebar"] {
            display: none;
        }
    </style>
    """,
    unsafe_allow_html=True
)

# --- FIRESTORE ---
@st.cache_resource
def get_db():
    if "connections" not in st.secrets:
        st.error("Brak konfiguracji Firestore w secrets.toml!")
        st.stop()
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()

# --- FUNKCJE POMOCNICZE ---
def zaloguj_uzytkownika(id_input):
    doc_ref = db.collection(COL_UCZNIOWIE).document(id_input)
    doc = doc_ref.get()
    
    if not doc.exists:
        return False
    
    dane = doc.to_dict()
    st.session_state.update({
        "zalogowany_id": id_input,
        "user_api_key": dane.get("user_api_key", ""),
        "role": dane.get("rola", "uczen"),
        "postep_tematow": dane.get("postep_tematow", {}),
        "historia_czatow": dane.get("historia_czatow", {})
    })
    return True

def stworz_konto(id_input, typ, klucz_api):
    nowy_profil = {
        "user_api_key": klucz_api, 
        "postep_tematow": {}, 
        "historia_czatow": {},
        "rola": typ
    }
    db.collection(COL_UCZNIOWIE).document(id_input).set(nowy_profil)

# --- INTERFEJS ---
st.title("🏫 Logowanie do Systemu")
id_input = st.text_input("Nazwa konta").strip()

# LOGOWANIE
if st.button("Zaloguj"):
    if id_input and zaloguj_uzytkownika(id_input):
        if st.session_state.role == "nauczyciel":
            st.switch_page("pages/02_nauczyciel.py")
        else:
            st.switch_page("pages/01_uczen.py")
    else:
        st.error("Konto nie istnieje lub nazwa jest pusta.")

# TWORZENIE KONTA
with st.expander("Tworzenie konta"):
    haslo_tworzenia = st.text_input("Hasło systemowe", type="password")
    typ_konta = st.selectbox("Typ konta", ["uczen", "nauczyciel"])
    nowy_klucz_api = st.text_input("Klucz API Gemini", type="password")
    
    if st.button("Zarejestruj konto"):
        if haslo_tworzenia != HASLO_SYSTEMOWE:
            st.error("Błędne hasło systemowe!")
        elif not id_input or not nowy_klucz_api:
            st.error("Wypełnij nazwę konta i klucz API!")
        else:
            stworz_konto(id_input, typ_konta, nowy_klucz_api)
            st.success(f"Konto {id_input} ({typ_konta}) utworzone!")