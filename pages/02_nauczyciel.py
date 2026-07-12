import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

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

st.title("👨‍🏫 Panel Nauczyciela")
st.write(f"Witaj, {st.session_state.zalogowany_id}!")

st.header("Lista uczniów i ich postępy")

uczniowie = db.collection("postepy_uczniow").stream()

for u in uczniowie:
    dane = u.to_dict()
    with st.expander(f"Uczeń: {u.id}"):
        st.write(f"Postęp tematów: {dane.get('postep_tematow')}")
        
        if st.button(f"Zresetuj dane ucznia {u.id}", key=u.id):
            db.collection("postepy_uczniow").document(u.id).update({
                "postep_tematow": {},
                "historia_czatow": {},
                "teorie_lekcji": {}
            })
            st.success("Zresetowano postępy!")
            st.rerun()

if st.button("Wyloguj"):
    st.session_state.clear()
    st.switch_page("app.py")