import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh # Poprawny import

# --- UKRYCIE DOMYŚLNEGO MENU STREAMLIT ---
st.markdown("""
    <style>
        [data-testid="stSidebarNav"] {display: none !important;}
    </style>
""", unsafe_allow_html=True)

# --- STRAŻNIK ---
if "zalogowany_id" not in st.session_state:
    st.switch_page("app.py")
if st.session_state.get("role") != "nauczyciel":
    st.error("Brak dostępu! Tylko dla nauczycieli.")
    st.stop()

# Ustawienie automatycznego odświeżania co 3 sekundy
count = st_autorefresh(interval=3000, limit=None, key="nauczyciel_refresh")

# --- PANEL NAUCZYCIELA ---
def init_firestore():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()


# Pasek boczny dla nauczyciela
with st.sidebar:
    if st.button("Wyloguj"):
        st.session_state.clear()
        st.switch_page("app.py")

st.title("👨‍🏫 Panel Nauczyciela")
st.write(f"Zalogowano jako: **{st.session_state.zalogowany_id}**")

# --- SEKCJA AKTYWACJI CZASOWEJ LEKCJI ---
st.header("⏱️ Zarządzanie Czasem Lekcji")
status_lekcji = db.collection("ustawienia_lekcji").document("globalna").get()

if status_lekcji.exists:
    dane_lekcji = status_lekcji.to_dict()
    godzina_blokady_str = dane_lekcji.get("godzina_blokady")
    if godzina_blokady_str:
        godzina_blokady = datetime.strptime(godzina_blokady_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < godzina_blokady:
            st.success(f"🟢 Lekcja jest AKTYWNA do godziny: {godzina_blokady.strftime('%H:%M:%S')}")
        else:
            st.error("🔴 Czas lekcji minął. Aplikacje uczniów są zablokowane.")
else:
    st.warning("Lekcja nie została jeszcze aktywowana.")

if st.button("Aktywuj lekcję na 1 godzinę", use_container_width=True):
    nowa_blokada = datetime.now() + timedelta(hours=1)
    nowa_blokada_str = nowa_blokada.strftime("%Y-%m-%d %H:%M:%S")
    db.collection("ustawienia_lekcji").document("globalna").set({"godzina_blokady": nowa_blokada_str})
    st.success(f"Pomyślnie aktywowano lekcję! Blokada nastąpi o: {nowa_blokada_str}")
    st.rerun()

st.markdown("---")
st.header("Lista uczniów i ich postępy")

# Wyciągamy wszystkich uczniów z bazy
uczniowie = db.collection("postepy_uczniow").where("rola", "==", "uczen").stream()

for u in uczniowie:
    dane = u.to_dict()
    potrzebuje_pomocy = dane.get("potrzebuje_pomocy", False)
    temat_problemu = dane.get("aktualny_temat_problemu", "Brak")
    
    # Zmiana etykiety i wyświetlenie czerwonego powiadomienia, jeśli uczeń wezwał pomoc
    if potrzebuje_pomocy:
        st.error(f"🚨 UCZEŃ POTRZEBUJE POMOCY: **{u.id}** (Utknął na: {temat_problemu})")
        etykieta_ucznia = f"🚨 [POMOC] Uczeń: {u.id}"
    else:
        etykieta_ucznia = f"Uczeń: {u.id}"
        
    with st.expander(etykieta_ucznia):
        postepy = dane.get('postep_tematow', {})
        if postepy:
            for temat, stan in postepy.items():
                status = stan.get("status") if isinstance(stan, dict) else stan
                if status == "ZALICZONY":
                    st.success(f"✅ {temat} - ZALICZONY")
                elif status == "W trakcie":
                    licznik = stan.get("licznik", 0) if isinstance(stan, dict) else 0
                    st.info(f"🔄 {temat} - W trakcie ({licznik}/8 zadań)")
                else:
                    st.error(f"❌ {temat} - {status}")
        else:
            st.write("Brak rozpoczętych tematów.")
            
        st.markdown("---")
        if st.button(f"Zresetuj dane ucznia {u.id}", key=f"reset_{u.id}"):
            db.collection("postepy_uczniow").document(u.id).update({
                "postep_tematow": {},
                "historia_czatow": {},
                "teorie_lekcji": {},
                "potrzebuje_pomocy": False,
                "aktualny_temat_problemu": ""
            })
            st.success(f"Zresetowano postępy dla ucznia {u.id}!")
            st.rerun()