import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

# --- 1. STAŁE I BAZA DANYCH ---
NAZWA_SZKOLY = "szkola_podstawowa_1"  # Nazwa Twojego dokumentu szkoły w Firestore
HASLO_SYSTEMOWE = "TwojeTajneHaslo123"

@st.cache_resource
def get_db():
    if "connections" not in st.secrets:
        st.error("Brak konfiguracji Firestore w secrets.toml!")
        st.stop()
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()

# Referencja do podkolekcji 'konta' w wybranej szkole
def pobierz_kolekcje_kont():
    return db.collection("szkola").document(NAZWA_SZKOLY).collection("konta")

# --- 2. FUNKCJE POMOCNICZE WIZUALNE I LOGICZNE ---
def ustaw_czysty_interfejs(ukryj_sidebar=False):
    style = """
        <style>
        footer {display: none !important; visibility: hidden !important; height: 0 !important;}
        [data-testid="stFooter"] {display: none !important; visibility: hidden !important;}
        [data-testid="stViewerBadge"] {display: none !important; visibility: hidden !important;}
        .stViewerBadge {display: none !important; visibility: hidden !important;}
        .stAppDeployButton {display: none !important; visibility: hidden !important;}
        .stAppViewMain {bottom: 0 !important; padding-bottom: 0 !important;}
        """
    if ukryj_sidebar:
        style += """
        [data-testid="stSidebar"] {display: none !important;}
        [data-testid="collapsedSidebar"] {display: none !important;}
        """
    style += "</style>"
    st.markdown(style, unsafe_allow_html=True)

def zaloguj_uzytkownika(id_input):
    doc_ref = pobierz_kolekcje_kont().document(id_input)
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
    pobierz_kolekcje_kont().document(id_input).set(nowy_profil)


# --- 3. INTERFEJS LOGOWANIA ---
if __name__ == "__main__":
    st.set_page_config(page_title="szkolny-system-ai.streamlit.app", layout="centered")
    ustaw_czysty_interfejs(ukryj_sidebar=True)

    st.title("🏫 Logowanie do Systemu")
    id_input = st.text_input("Nazwa konta").strip()

    # LOGOWANIE
    if st.button("Zaloguj"):
        if id_input and zaloguj_uzytkownika(id_input):
            rola = st.session_state.role
            if rola == "dyrektor":
                st.switch_page("pages/03_dyrektor.py")
            elif rola == "nauczyciel":
                st.switch_page("pages/02_nauczyciel.py")
            else:
                st.switch_page("pages/01_uczen.py")
        else:
            st.error("Konto nie istnieje lub nazwa jest pusta.")

    # TWORZENIE KONTA (Awaryjne / Początkowe)
    with st.expander("Tworzenie konta"):
        haslo_tworzenia = st.text_input("Hasło systemowe", type="password")
        typ_konta = st.selectbox("Typ konta", ["uczen", "nauczyciel", "dyrektor"])
        nowy_klucz_api = st.text_input("Klucz API Gemini", type="password")
        
        if st.button("Zarejestruj konto"):
            if haslo_tworzenia != HASLO_SYSTEMOWE:
                st.error("Błędne hasło systemowe!")
            elif not id_input or not nowy_klucz_api:
                st.error("Wypełnij nazwę konta i klucz API!")
            else:
                st.stworz_konto(id_input, typ_konta, nowy_klucz_api)
                st.success(f"Konto {id_input} ({typ_konta}) utworzone!")