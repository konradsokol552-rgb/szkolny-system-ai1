import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

st.set_page_config(page_title="Panel Dyrektora", layout="wide")

# Ochrona dostępu - tylko dla zalogowanego dyrektora
if st.session_state.get("role") != "dyrektor":
    st.error("Brak uprawnień do przeglądania tej strony!")
    st.stop()

# --- BAZA DANYCH ---
NAZWA_SZKOLY = "szkola_podstawowa_1"

@st.cache_resource
def get_db():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = get_db()
konta_ref = db.collection("szkola").document(NAZWA_SZKOLY).collection("konta")
klasy_ref = db.collection("szkola").document(NAZWA_SZKOLY).collection("klasy")

st.title("🏛️ Panel Zarządzania Dyrektora")
st.write(f"Zalogowano jako: **{st.session_state.get('zalogowany_id')}**")

COL_PRZEDMIOTY = "przedmioty"


def get_szkolne_dane_ref():
    return db.collection("szkola").document(NAZWA_SZKOLY)


def get_przedmioty_ref():
    return get_szkolne_dane_ref().collection(COL_PRZEDMIOTY)


def pobierz_przedmioty() -> dict:
    struktura = {}
    for doc in get_przedmioty_ref().stream():
        tematy = doc.to_dict().get("lista_tematow", [])
        if not isinstance(tematy, list):
            tematy = [str(tematy)]
        struktura[doc.id] = tematy
    return struktura


def zapisz_przedmiot(nazwa: str, tematy: list):
    if nazwa.strip():
        get_przedmioty_ref().document(nazwa.strip()).set({"lista_tematow": tematy}, merge=True)


def usun_przedmiot(nazwa: str):
    if nazwa.strip():
        get_przedmioty_ref().document(nazwa.strip()).delete()

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
        rola = st.selectbox("Rola w systemie", ["uczen", "nauczyciel", "dyrektor"])
        klucz_api = st.text_input("Klucz API Gemini dla tego konta", type="password")
        klasa = st.text_input("Klasa / oddział", placeholder="np. 1A").strip()
        
        submit = st.form_submit_button("Utwórz konto")
        if submit:
            if not nowe_id or not klucz_api:
                st.error("Podaj nazwę użytkownika oraz klucz API!")
            else:
                doc_check = konta_ref.document(nowe_id).get()
                if doc_check.exists:
                    st.error(f"Konto o nazwie '{nowe_id}' już istnieje!")
                else:
                    if klasa:
                        klasy_ref.document(klasa).set({"nazwa": klasa}, merge=True)
                    konta_ref.document(nowe_id).set({
                        "user_api_key": klucz_api,
                        "rola": rola,
                        "klasa": klasa,
                        "postep_tematow": {},
                        "historia_czatow": {}
                    })
                    st.success(f"Pomyślnie utworzono konto: {nowe_id} [{rola}] klasy {klasa or '-'}")

# --- ZAKŁADKA 2: PODGLĄD I EDYCJA KONT ---
with zakladka2:
    st.subheader("`Lista kont`")
    
    # Wyciąganie wszystkich kont z podkolekcji
    docs = konta_ref.stream()
    lista_kont = []
    
    for doc in docs:
        dane = doc.to_dict()
        lista_kont.append({
            "ID (Login)": doc.id,
            "Rola": dane.get("rola", "brak"),
            "Klasa": dane.get("klasa", "brak"),
            "Klucz API": "***" + dane.get("user_api_key", "")[-4:] if dane.get("user_api_key") else "Brak"
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
                konta_ref.document(wybrane_id).delete()
                st.success(f"Usunięto konto: {wybrane_id}")
                st.rerun()
    else:
        st.info("Brak zarejestrowanych kont w bazie.")

# --- ZAKŁADKA 3: ZARZĄDZANIE PRZEDMIOTAMI ---
with zakladka3:
    st.subheader("Zarządzanie przedmiotami i tematami")
    st.caption("Tematy wpisuj jeden pod drugim!!!")

    przedmioty = pobierz_przedmioty()

    with st.form("form_dodaj_przedmiot"):
        nowy_przedmiot = st.text_input("Nazwa nowego przedmiotu").strip()
        nowe_tematy = st.text_area("Tematy nowego przedmiotu (jeden per linię)", placeholder="np. Algebra\nGeometria")
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
        tematy_input = st.text_area("Tematy dla wybranego przedmiotu", value=tematy_text, height=220, key="tematy_input")

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