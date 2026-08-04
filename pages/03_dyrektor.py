import streamlit as st
from config import ustaw_czysty_interfejs
from services.auth_service import sprawdz_dostep, stworz_konto
from services.db_service import (
    pobierz_konto,
    pobierz_wszystkie_konta,
    usun_konto,
    pobierz_przedmioty,
    zapisz_przedmiot,
    usun_przedmiot,
)

st.set_page_config(page_title="Panel Dyrektora", layout="wide")

# Ochrona dostępu - tylko dla zalogowanego dyrektora
sprawdz_dostep(wymagana_rola="dyrektor")
ustaw_czysty_interfejs(ukryj_sidebar=False)

st.title("🏛️ Panel Zarządzania Dyrektora")
st.write(f"Zalogowano jako: **{st.session_state.get('zalogowany_id')}**")

if st.button("Wyloguj się"):
    st.session_state.clear()
    st.switch_page("app.py")

st.divider()

zakladka1, zakladka2, zakladka3 = st.tabs(["➕ Dodaj Nowe Konto", "📋 Wszystkie Konta w Szkole", "🧩 Zarządzanie Przedmiotami"])

# --- ZAKŁADKA 1: TWORZENIE KONTA ---
with zakladka1:
    st.subheader("Tworzenie nowego użytkownika")
    with st.form("form_dodaj_konto"):
        nowe_id = st.text_input("Nazwa / Login użytkownika (np. j.kowalski)").strip()
        rola = st.selectbox("Rola w systemie", ["uczen", "nauczyciel"])
        klucz_api = st.text_input("Klucz API Gemini dla tego konta", type="password")
        haslo_konta = st.text_input("Hasło konta", type="password")
        klasa = st.text_input("Klasa / oddział", placeholder="np. 1A").strip()
        
        submit = st.form_submit_button("Utwórz konto")
        if submit:
            if not nowe_id or not klucz_api or not haslo_konta:
                st.error("Podaj nazwę użytkownika, klucz API oraz hasło!")
            else:
                existing = pobierz_konto(nowe_id)
                if existing:
                    st.error(f"Konto o nazwie '{nowe_id}' już istnieje!")
                else:
                    if stworz_konto(nowe_id, rola, klucz_api, klasa, haslo_konta):
                        st.success(f"Pomyślnie utworzono konto: {nowe_id} [{rola}] klasy {klasa or '-'}")
                    else:
                        st.error("Wystąpił błąd podczas tworzenia konta.")

# --- ZAKŁADKA 2: PODGLĄD I EDYCJA KONT ---
with zakladka2:
    st.subheader("Lista kont")
    
    wszystkie = pobierz_wszystkie_konta()
    lista_kont = []
    
    for dane in wszystkie:
        api_key = dane.get("user_api_key", "")
        lista_kont.append({
            "ID (Login)": dane.get("id"),
            "Rola": dane.get("rola", "brak"),
            "Klasa": dane.get("klasa", "brak"),
            "Klucz API": "***" + api_key[-4:] if api_key else "Brak"
        })
    
    if lista_kont:
        st.dataframe(lista_kont, use_container_width=True)
        
        st.divider()
        st.subheader("⚙️ Akcje na kontach")
        wybrane_id = st.selectbox("Wybierz konto do usunięcia:", [k["ID (Login)"] for k in lista_kont])
        
        if st.button("🗑️ Usuń wybrane konto", type="primary"):
            if wybrane_id == st.session_state.get("zalogowany_id"):
                st.error("Nie możesz usunąć konta, na którym jesteś obecnie zalogowany!")
            else:
                usun_konto(wybrane_id)
                st.success(f"Usunięto konto: {wybrane_id}")
                st.rerun()
    else:
        st.info("Brak zarejestrowanych kont w bazie.")

# --- ZAKŁADKA 3: ZARZĄDZANIE PRZEDMIOTAMI ---
with zakladka3:
    st.subheader("Zarządzanie przedmiotami i tematami")
    st.caption("Tematy wpisuj jeden pod drugim.")

    przedmioty = pobierz_przedmioty()

    with st.form("form_dodaj_przedmiot"):
        nowy_przedmiot = st.text_input("Nazwa nowego przedmiotu").strip()
        nowe_tematy = st.text_area("Tematy nowego przedmiotu (wpisuj jeden pod drugim)", placeholder="np. Algebra\nGeometria")
        if st.form_submit_button("➕ Dodaj przedmiot"):
            if not nowy_przedmiot:
                st.error("Wpisz nazwę przedmiotu.")
            else:
                tematy = [t.strip() for t in nowe_tematy.splitlines() if t.strip()]
                zapisz_przedmiot(nowy_przedmiot, tematy)
                st.success(f"Dodano przedmiot: {nowy_przedmiot}")
                st.rerun()

    if przedmioty:
        st.divider()
        wybrany_przedmiot = st.selectbox("Edytuj istniejący przedmiot", list(przedmioty.keys()), key="wybrany_przedmiot")
        tematy_text = "\n".join(przedmioty[wybrany_przedmiot])
        tematy_input = st.text_area("Edytowanie tematów (wpisuj jeden pod drugim)", value=tematy_text, height=220, key="tematy_input")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Zapisz tematy"):
                tematy = [t.strip() for t in tematy_input.splitlines() if t.strip()]
                zapisz_przedmiot(wybrany_przedmiot, tematy)
                st.success(f"Zapisano tematy dla: {wybrany_przedmiot}")
                st.rerun()
        with col2:
            if st.button("🗑️ Usuń przedmiot"):
                usun_przedmiot(wybrany_przedmiot)
                st.success(f"Usunięto przedmiot: {wybrany_przedmiot}")
                st.rerun()
    else:
        st.info("Brak przedmiotów do zarządzania.")