import streamlit as st
from google.oauth2 import service_account
from google.cloud import firestore

# Funkcja inicjalizująca Firestore (wspólna)
def init_firestore():
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])

db = init_firestore()

st.title("🏫 Logowanie do Systemu")

id_input = st.text_input("Nazwa konta").strip()
haslo_input = st.text_input("Hasło (opcjonalnie)", type="password")

if st.button("Zaloguj"):
    doc = db.collection("postepy_uczniow").document(id_input).get()
    
    if doc.exists:
        dane = doc.to_dict()
        st.session_state.zalogowany_id = id_input
        st.session_state.user_api_key = dane.get("user_api_key", "")
        # Domyślnie rola to "uczen", chyba że w bazie jest inaczej
        st.session_state.role = dane.get("rola", "uczen") 
        
        if st.session_state.role == "nauczyciel":
            st.switch_page("pages/02_nauczyciel.py")
        else:
            st.switch_page("pages/01_uczen.py")
    else:
        st.error("Nie znaleziono takiego konta!")