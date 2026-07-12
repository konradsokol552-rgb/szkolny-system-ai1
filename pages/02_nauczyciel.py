import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

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

st.header("Lista uczniów i ich postępy")

# Wyciągamy wszystkich uczniów z bazy
uczniowie = db.collection("postepy_uczniow").where("rola", "==", "uczen").stream()

for u in uczniowie:
    dane = u.to_dict()
    with st.expander(f"Uczeń: {u.id}"):
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
        if st.button(f"Zresetuj dane ucznia {u.id}(nie będzie można tego cofnąć)", key=f"reset_{u.id}"):
            db.collection("postepy_uczniow").document(u.id).update({
                "postep_tematow": {},
                "historia_czatow": {},
                "teorie_lekcji": {}
            })
            st.success(f"Zresetowano postępy dla ucznia {u.id}!")
            st.rerun()