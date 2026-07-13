import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- KONFIGURACJA CSS ---
st.markdown("""
    <style>
        [data-testid="stSidebarNav"] {display: none !important;}
        
        /* CSS hack: Znajduje przycisk w sidebarze, który wewnątrz zawiera tekst "POMOC!" */
        div[data-testid="stSidebar"] button:has(div:contains("POMOC!")) {
            background-color: #FF4B4B !important;
            color: white !important;
        }
    </style>
""", unsafe_allow_html=True)

# --- STRAŻNIK ---
if "zalogowany_id" not in st.session_state:
    st.switch_page("app.py")
if st.session_state.get("role") != "nauczyciel":
    st.error("Brak dostępu! Tylko dla nauczycieli.")
    st.stop()

# Ustawienie automatycznego odświeżania co 10 sekund
count = st_autorefresh(interval=10000, limit=None, key="nauczyciel_refresh")

# --- PANEL NAUCZYCIELA ---
def init_firestore():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

# --- PANEL BOCZNY (NAWIGACJA UCZNIÓW) ---
with st.sidebar:
    st.title("👨‍🏫 Nauczyciel")
    st.write(f"Zalogowano: **{st.session_state.zalogowany_id}**")
    
    if st.button("Wyloguj"):
        st.session_state.clear()
        st.switch_page("app.py")
    
    st.markdown("---")
    st.subheader("Lista uczniów")
    
    # Pobieramy wszystkich uczniów
    uczniowie = list(db.collection("postepy_uczniow").where("rola", "==", "uczen").stream())
    
    for u in uczniowie:
        dane = u.to_dict()
        potrzebuje_pomocy = dane.get("potrzebuje_pomocy", False)
        
        # Etykieta przycisku
        if potrzebuje_pomocy:
            label = f"🚨 {u.id} (POMOC!)"
        else:
            label = f"👤 {u.id}"
            
        # Przycisk w sidebarze
        # Dzięki CSS powyżej, jeśli label zawiera "POMOC!", przycisk będzie czerwony!
        if st.button(label, key=f"btn_{u.id}", use_container_width=True):
            st.session_state.wybrany_uczen_id = u.id
            st.rerun()

# --- GŁÓWNY OBSZAR ---
st.title("Panel Nauczyciela")

# Zarządzanie czasem
status_lekcji = db.collection("ustawienia_lekcji").document("globalna").get()
if status_lekcji.exists:
    dane_lekcji = status_lekcji.to_dict()
    godzina_blokady_str = dane_lekcji.get("godzina_blokady")
    if godzina_blokady_str:
        godzina_blokady = datetime.strptime(godzina_blokady_str, "%Y-%m-%d %H:%M:%S")
        if datetime.now() < godzina_blokady:
            st.success(f"🟢 Lekcja AKTYWNA do: {godzina_blokady.strftime('%H:%M:%S')}")
        else:
            st.error("🔴 Czas lekcji minął.")

if st.button("Aktywuj lekcję na 1 godzinę"):
    nowa_blokada = datetime.now() + timedelta(hours=1)
    db.collection("ustawienia_lekcji").document("globalna").set({"godzina_blokady": nowa_blokada.strftime("%Y-%m-%d %H:%M:%S")})
    st.rerun()

st.markdown("---")

# --- WYŚWIETLANIE SZCZEGÓŁÓW ---
if "wybrany_uczen_id" in st.session_state:
    uczen_id = st.session_state.wybrany_uczen_id
    doc_ref = db.collection("postepy_uczniow").document(uczen_id)
    doc = doc_ref.get()
    
    if doc.exists:
        dane = doc.to_dict()
        st.header(f"Podgląd ucznia: {uczen_id}")
        
        if dane.get("potrzebuje_pomocy"):
            st.error(f"🚨 UCZEŃ PROSI O POMOC przy temacie: {dane.get('aktualny_temat_problemu')}")
        
        postepy = dane.get('postep_tematow', {})
        for temat, stan in postepy.items():
            status = stan.get("status") if isinstance(stan, dict) else stan
            if status == "ZALICZONY":
                st.success(f"✅ {temat} - ZALICZONY")
            elif status == "W trakcie":
                licznik = stan.get("licznik", 0) if isinstance(stan, dict) else 0
                st.info(f"🔄 {temat} - W trakcie ({licznik}/8 zadań)")
            else:
                st.error(f"❌ {temat} - {status}")
                
        if st.button(f"Zresetuj dane ucznia {uczen_id}"):
            doc_ref.update({
                "postep_tematow": {},
                "historia_czatow": {},
                "teorie_lekcji": {},
                "potrzebuje_pomocy": False,
                "aktualny_temat_problemu": ""
            })
            st.rerun()
    else:
        st.warning("Uczeń nie istnieje.")
else:
    st.info("Wybierz ucznia z paska bocznego, aby zobaczyć jego postępy.")