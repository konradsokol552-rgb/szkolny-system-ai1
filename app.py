import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

# --- 1. STAŁE I BAZA DANYCH ---
NAZWA_SZKOLY = "szkola_podstawowa_1"  # Nazwa Twojego dokumentu szkoły w Firestore
HASLO_SYSTEMOWE = "kM8#pQ!2vZ$xL@9tW"
COL_KLASY = "klasy"

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


def pobierz_kolekcje_klas():
    return db.collection("szkola").document(NAZWA_SZKOLY).collection(COL_KLASY)

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

def zaloguj_uzytkownika(id_input, haslo_input):
    doc_ref = pobierz_kolekcje_kont().document(id_input)
    doc = doc_ref.get()
    
    if not doc.exists:
        return False
    
    dane = doc.to_dict()
    if dane.get("haslo") != haslo_input:
        return False
    
    st.session_state.update({
        "zalogowany_id": id_input,
        "user_api_key": dane.get("user_api_key", ""),
        "role": dane.get("rola", "uczen"),
        "klasa": dane.get("klasa", ""),
        "postep_tematow": dane.get("postep_tematow", {}),
        "historia_czatow": dane.get("historia_czatow", {})
    })
    return True

def stworz_konto(id_input, typ, klucz_api, klasa, haslo):
    if klasa.strip():
        pobierz_kolekcje_klas().document(klasa.strip()).set({"nazwa": klasa.strip()}, merge=True)

    nowy_profil = {
        "user_api_key": klucz_api,
        "haslo": haslo,
        "postep_tematow": {},
        "historia_czatow": {},
        "rola": typ,
        "klasa": klasa.strip()
    }
    pobierz_kolekcje_kont().document(id_input).set(nowy_profil)


# --- 3. INTERFEJS LOGOWANIA ---
if __name__ == "__main__":
    st.set_page_config(page_title="szkolny-system-ai.streamlit.app", layout="centered")
    ustaw_czysty_interfejs(ukryj_sidebar=True)

    st.title("🏫 Logowanie do Systemu")
    id_input = st.text_input("Nazwa konta", key="login_nazwa_konta").strip()
    haslo_input = st.text_input("Hasło konta", type="password", key="login_haslo_konta")

    # LOGOWANIE
    if st.button("Zaloguj"):
        if id_input and haslo_input and zaloguj_uzytkownika(id_input, haslo_input):
            rola = st.session_state.role
            if rola == "dyrektor":
                st.switch_page("pages/03_dyrektor.py")
            elif rola == "nauczyciel":
                st.switch_page("pages/02_nauczyciel.py")
            else:
                st.switch_page("pages/01_uczen.py")
        else:
            st.error("Konto nie istnieje, dane są nieprawidłowe lub brakuje hasła.")

    # TWORZENIE KONTA (Awaryjne / Początkowe)
    with st.expander("Tworzenie konta"):
        haslo_tworzenia = st.text_input("Hasło systemowe", type="password", key="create_haslo_systemowe")
        typ_konta = st.selectbox("Typ konta", ["uczen", "nauczyciel", "dyrektor"], key="create_typ_konta")
        nowy_klucz_api = st.text_input("Klucz API Gemini", type="password", key="create_klucz_api")
        haslo_konta = st.text_input("Hasło konta", type="password", key="create_haslo_konta")
        klasa_konta = st.text_input("Klasa / oddział", placeholder="np. 1A", key="create_klasa_konta").strip()
        
        if st.button("Zarejestruj konto"):
            if haslo_tworzenia != HASLO_SYSTEMOWE:
                st.error("Błędne hasło systemowe!")
            elif not id_input or not nowy_klucz_api or not haslo_konta:
                st.error("Wypełnij nazwę konta, klucz API i hasło!")
            else:
                stworz_konto(id_input, typ_konta, nowy_klucz_api, klasa_konta, haslo_konta)
                st.success(f"Konto {id_input} ({typ_konta}) utworzone!")