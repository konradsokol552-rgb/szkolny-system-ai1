from datetime import datetime
import streamlit as st

from config import STREFA_PL, ustaw_czysty_interfejs
from services.auth_service import sprawdz_dostep
from services.db_service import (
    pobierz_uczniow_klasy,
    pobierz_konto,
    odblokuj_antycheat_ucznia,
    zresetuj_dane_ucznia,
    pobierz_status_lekcji_globalnej,
    aktywuj_lekcje_globalna,
)

# --- STRAŻNIK DOSTĘPU ---
sprawdz_dostep(wymagana_rola="nauczyciel")
ustaw_czysty_interfejs(ukryj_sidebar=False)

# --- UI: SIDEBAR ---
@st.fragment(run_every=3)
def render_sidebar():
    st.title("👨‍🏫 Nauczyciel")
    st.write(f"Zalogowano: **{st.session_state.get('zalogowany_id')}**")
    
    if st.button("Wyloguj"):
        st.session_state.clear()
        st.switch_page("app.py")
    
    st.markdown("---")
    klasa_nauczyciela = st.session_state.get('klasa', '-')
    st.subheader(f"Lista uczniów klasy: {klasa_nauczyciela}")
    
    uczniowie = pobierz_uczniow_klasy(klasa_nauczyciela)
    for u in uczniowie:
        dane = u.to_dict()
        icon = '🚨' if dane.get('potrzebuje_pomocy') else '👤'
        if st.button(f"{icon} {u.id}", key=f"btn_{u.id}", use_container_width=True):
            st.session_state.wybrany_uczen_id = u.id
            st.rerun()

with st.sidebar:
    render_sidebar()

# --- UI: GŁÓWNY PANEL ---
st.title("Panel Nauczyciela")

# Zarządzanie czasem lekcji
dane_lekcji = pobierz_status_lekcji_globalnej()
if dane_lekcji and dane_lekcji.get("godzina_blokady"):
    godzina_blokady = datetime.strptime(dane_lekcji["godzina_blokady"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=STREFA_PL)
    if datetime.now(STREFA_PL) < godzina_blokady:
        st.success(f"🟢 Lekcja AKTYWNA do: {godzina_blokady.strftime('%H:%M:%S')}")
    else:
        st.error("🔴 Czas lekcji minął.")

if st.button("Aktywuj lekcję na 1 godzinę"):
    aktywuj_lekcje_globalna(1.0)
    st.rerun()

# Wyświetlanie szczegółów wybranego ucznia
if "wybrany_uczen_id" in st.session_state:
    uczen_id = st.session_state.wybrany_uczen_id
    dane = pobierz_konto(uczen_id)
    
    if dane:
        st.header(f"Podgląd ucznia: {uczen_id}")
        
        if dane.get("potrzebuje_pomocy"):
            st.error(f"🚨 UCZEŃ PROSI O POMOC: {dane.get('aktualny_temat_problemu')}")

        if dane.get("blokada_do"):
            st.warning("🔒 Uczeń ma aktywną blokadę anty-cheat.")
            if st.button(f"🔓 Odblokuj anty-cheat dla {uczen_id}"):
                if odblokuj_antycheat_ucznia(uczen_id):
                    st.success("Blokada została usunięta.")
                    st.rerun()
        
        # Wyświetlanie postępów
        st.subheader("Postępy w tematach:")
        postepy = dane.get('postep_tematow', {})
        if postepy:
            for temat, stan in postepy.items():
                status = stan.get("status") if isinstance(stan, dict) else stan
                licznik_sos = stan.get("licznik_sos", 0) if isinstance(stan, dict) else 0
                sos_text = f" | 🆘 SOS: {licznik_sos}" if licznik_sos > 0 else ""
                
                if status == "ZALICZONY":
                    st.success(f"✅ {temat} - ZALICZONY{sos_text}")
                elif status == "W trakcie":
                    liczba_praktyka = stan.get('licznik', 0) if isinstance(stan, dict) else 0
                    st.info(f"🔄 {temat} - W trakcie ({liczba_praktyka}/8){sos_text}")
                else:
                    st.error(f"❌ {temat} - {status}{sos_text}")
        else:
            st.info("Brak wpisów o postępach ucznia.")
                
        if st.button(f"Zresetuj dane ucznia {uczen_id}"):
            if zresetuj_dane_ucznia(uczen_id):
                st.success("Dane ucznia zostały zresetowane.")
                st.rerun()
    else:
        st.warning("Wybrany uczeń nie istnieje w bazie.")