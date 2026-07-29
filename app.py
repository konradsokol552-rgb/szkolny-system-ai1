import streamlit as st
from config import HASLO_SYSTEMOWE
from services.auth_service import zaloguj_uzytkownika, stworz_konto


def ustaw_czysty_interfejs(ukryj_sidebar: bool = False) -> None:
    """Stosuje niestandardowe style CSS ukrywające stopkę i opcjonalnie sidebar Streamlita."""
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


if __name__ == "__main__":
    st.set_page_config(page_title="szkolny-system-ai.streamlit.app", layout="centered")
    ustaw_czysty_interfejs(ukryj_sidebar=True)

    st.title("🏫 Logowanie do Systemu")

    # Formularz logowania
    id_input = st.text_input("Nazwa konta", key="login_nazwa_konta").strip()
    haslo_input = st.text_input("Hasło konta", type="password", key="login_haslo_konta")

    if st.button("Zaloguj", use_container_width=True):
        if id_input and haslo_input and zaloguj_uzytkownika(id_input, haslo_input):
            rola = st.session_state.get("role", "uczen")
            if rola == "dyrektor":
                st.switch_page("pages/03_dyrektor.py")
            elif rola == "nauczyciel":
                st.switch_page("pages/02_nauczyciel.py")
            else:
                st.switch_page("pages/01_uczen.py")
        else:
            st.error("Nieprawidłowa nazwa konta lub błędne hasło.")

    # Tworzenie konta (Awaryjne / Początkowe)
    with st.expander("Tworzenie nowego konta"):
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
                if stworz_konto(id_input, typ_konta, nowy_klucz_api, klasa_konta, haslo_konta):
                    st.success(f"Konto {id_input} ({typ_konta}) zostało utworzone!")
                else:
                    st.error("Nie udało się utworzyć konta.")