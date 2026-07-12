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
haslo_input = st.text_input("Klucz API (Tylko przy tworzeniu konta)", type="password")
haslo_tworzenia = st.text_input("Hasło systemowe (Tylko przy tworzeniu konta)", type="password")

if st.button("Zaloguj / Zarejestruj"):
    if not db:
        st.error("Błąd połączenia z bazą danych.")
        st.stop()
        
    doc = db.collection("postepy_uczniow").document(id_input).get()
    
    if doc.exists:
        dane = doc.to_dict()
        
        # Zapisujemy dane do sesji
        st.session_state.zalogowany_id = id_input
        st.session_state.user_api_key = dane.get("user_api_key", "")
        st.session_state.role = dane.get("rola", "uczen")
        st.session_state.postep_tematow = dane.get("postep_tematow", {})
        st.session_state.historia_czatow = dane.get("historia_czatow", {})
        
        # Przekierowanie zależne od roli
        if st.session_state.role == "nauczyciel":
            st.switch_page("pages/02_nauczyciel.py")
        else:
            st.switch_page("pages/01_uczen.py")
    else:
        # Tworzenie nowego konta
        if haslo_tworzenia == "TwojeTajneHaslo123":
            nowy_profil = {
                "user_api_key": haslo_input, 
                "postep_tematow": {}, 
                "historia_czatow": {},
                "rola": "uczen"
            }
            db.collection("postepy_uczniow").document(id_input).set(nowy_profil)
            st.success("Konto utworzone! Kliknij przycisk ponownie, aby się zalogować.")
        else:
            st.error("Nie znaleziono konta, a hasło do utworzenia nowego jest błędne!")