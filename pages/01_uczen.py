from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from config import STREFA_PL
from services.auth_service import sprawdz_dostep
from services.ai_service import zapytaj_ai
from services.db_service import (
    pobierz_konto,
    zapisz_konto,
    pobierz_przedmioty,
    pobierz_status_lekcji_globalnej,
    wczytaj_profil_z_chmury,
    zapisz_profil_do_chmury,
)

# =====================================================================
# 1. STRAŻNIK DOSTĘPU I INICJALIZACJA
# =====================================================================
sprawdz_dostep(wymagana_rola="uczen")

user_id = st.session_state.zalogowany_id

def sprawdz_aktywnosc_lekcji() -> bool:
    dane = pobierz_status_lekcji_globalnej()
    if dane and dane.get("godzina_blokady"):
        try:
            godzina_blokady = datetime.strptime(dane["godzina_blokady"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=STREFA_PL)
            return datetime.now(STREFA_PL) < godzina_blokady
        except Exception:
            pass
    return False

def ustaw_stan_testu(w_trakcie: bool):
    zapisz_konto(user_id, {"w_trakcie_testu": w_trakcie}, merge=True)
    wczytaj_profil_z_chmury.clear()

def zapisz_profil_w_chmurze_local():
    postepy = st.session_state.get("postep_tematow", {})
    historia = st.session_state.get("historia_czatow", {})
    if not isinstance(historia, dict):
        historia = {}
        
    if "aktualny_temat" in st.session_state:
        temat = st.session_state.aktualny_temat
        licznik = st.session_state.get("licznik_zadan", 0)
        
        if not isinstance(postepy.get(temat), dict):
            postepy[temat] = {"status": postepy.get(temat, "W trakcie")}
        postepy[temat]["licznik"] = licznik
        st.session_state.postep_tematow = postepy

    dane_do_zapisu = {
        "user_api_key": st.session_state.get("user_api_key", ""),
        "rola": st.session_state.get("role", "uczen"),
        "postep_tematow": postepy,
        "historia_czatow": historia,
        "teorie_lekcji": st.session_state.get("teorie_lekcji", {})
    }
    zapisz_profil_do_chmury(user_id, dane_do_zapisu)

def _parsuj_czas_blokady(raw_blokada) -> datetime:
    if isinstance(raw_blokada, datetime):
        return raw_blokada.replace(tzinfo=STREFA_PL) if raw_blokada.tzinfo is None else raw_blokada.astimezone(STREFA_PL)
    try:
        return datetime.fromisoformat(str(raw_blokada)).astimezone(STREFA_PL)
    except Exception:
        return datetime.now(STREFA_PL)

lekcja_aktywna = sprawdz_aktywnosc_lekcji()
profil_aktualny = wczytaj_profil_z_chmury(user_id) or {}

if not lekcja_aktywna and profil_aktualny.get("w_trakcie_testu"):
    ustaw_stan_testu(False)
    st.rerun()

# =====================================================================
# 2. SYSTEM ANTY-CHEAT
# =====================================================================
st.markdown("""
<style>
    div[class*="st-key-btn_ac_rerun_hidden"],
    .st-key-btn_ac_rerun_hidden {
        display: none !important;
        height: 0px !important;
        margin: 0px !important;
        padding: 0px !important;
        overflow: hidden !important;
        position: absolute !important;
        pointer-events: none !important;
    }
</style>
""", unsafe_allow_html=True)

if st.button("RERUN_ANTYCHEAT_TRIGGER", key="btn_ac_rerun_hidden"):
    zapisz_konto(user_id, {"sygnal_oszustwa": True}, merge=True)
    wczytaj_profil_z_chmury.clear()
    st.rerun()

if profil_aktualny.get("sygnal_oszustwa") is True:
    teraz_pl = datetime.now(STREFA_PL)
    czas_kary = teraz_pl + timedelta(minutes=45)
    zapisz_konto(user_id, {
        "sygnal_oszustwa": False,
        "blokada_do": czas_kary
    }, merge=True)
    wczytaj_profil_z_chmury.clear()
    profil_aktualny["blokada_do"] = czas_kary
    profil_aktualny["sygnal_oszustwa"] = False

if profil_aktualny.get("blokada_do"):
    czas_blokady = _parsuj_czas_blokady(profil_aktualny["blokada_do"])
    teraz = datetime.now(STREFA_PL)
    
    if czas_blokady > teraz:
        st.error("🚨 WYKRYTO OPUSZCZENIE KARTY LUB UTRATĘ FOKUSU! 🚨")
        st.warning(f"Twój dostęp do lekcji został zablokowany do godziny: **{czas_blokady.strftime('%H:%M:%S')}**")
        st.info("⏳ czas blokady: 45min.")
        st.stop()

# Wstrzykiwanie skryptu JS podczas testu
w_trakcie_testu = profil_aktualny.get("w_trakcie_testu", False)
if lekcja_aktywna and w_trakcie_testu:
    components.html("""
    <script>
        let oszustwoWyslane = false;
        let wakeLock = null;

        const targetDoc = window.parent ? window.parent.document : document;
        const targetWin = window.parent ? window.parent : window;

        async function aktywujWakeLock() {
            try {
                if ('wakeLock' in navigator) {
                    wakeLock = await navigator.wakeLock.request('screen');
                    console.log("🔒 Wake Lock: Ekran nie zgaśnie podczas testu.");
                }
            } catch (err) {
                console.warn("Nie udało się aktywować Wake Lock:", err);
            }
        }
        aktywujWakeLock();

        function znajdzPrzycisk() {
            const dokumenty = [document];
            try { if (window.parent && window.parent !== window) dokumenty.push(window.parent.document); } catch (e) {}
            try { if (window.top && window.top !== window) dokumenty.push(window.top.document); } catch (e) {}

            for (const doc of dokumenty) {
                try {
                    let btn = doc.querySelector('.st-key-btn_ac_rerun_hidden button') || 
                              doc.querySelector('[class*="st-key-btn_ac_rerun_hidden"] button');
                    if (btn) return btn;

                    const buttons = doc.querySelectorAll('button');
                    for (let b of buttons) {
                        if (b.innerText && b.innerText.includes("RERUN_ANTYCHEAT_TRIGGER")) {
                            return b;
                        }
                    }
                } catch (e) {}
            }
            return null;
        }

        function wyzwolRerunStreamlit() {
            const btn = znajdzPrzycisk();
            if (btn) {
                btn.click();
            } else if (targetWin && targetWin.location) {
                targetWin.location.reload();
            }
        }

        function zglosOszustwo() {
            if (oszustwoWyslane) return;
            oszustwoWyslane = true;
            wyzwolRerunStreamlit();
        }

        targetDoc.addEventListener("visibilitychange", function() {
            if (targetDoc.visibilityState === 'hidden') {
                zglosOszustwo();
            } else if (targetDoc.visibilityState === 'visible') {
                if (!oszustwoWyslane) {
                    aktywujWakeLock();
                } else {
                    wyzwolRerunStreamlit();
                }
            }
        });

        targetWin.addEventListener("beforeunload", function(e) {
            zglosOszustwo();
        });
    </script>
    """, height=0)

# =====================================================================
# 3. PASEK BOCZNY (MENU I KONTROLA SESJI)
# =====================================================================
if "struktura_dydaktyczna" not in st.session_state:
    st.session_state.struktura_dydaktyczna = pobierz_przedmioty()

with st.sidebar:
    if w_trakcie_testu:
        st.error("🔒 TRWA TEST KOŃCOWY!")
        st.caption("Wylogowanie oraz zmiana tematów są zablokowane do czasu ukończenia sprawdzianu.")
    else:
        if st.button("Wyloguj"):
            st.session_state.clear()
            st.switch_page("app.py")

    st.header("🏫 Dziennik Ucznia")
    
    if not st.session_state.struktura_dydaktyczna:
        st.warning("Brak przedmiotów w bazie.")
        st.stop()
        
    wybrany_przedmiot = st.selectbox(
        "Wybierz przedmiot:", 
        list(st.session_state.struktura_dydaktyczna.keys()),
        disabled=w_trakcie_testu
    )
    dostepne = st.session_state.struktura_dydaktyczna.get(wybrany_przedmiot, [])
    
    st.subheader("📚 Status tematów")
    
    def priorytet(t):
        dane = st.session_state.get("postep_tematow", {}).get(t, "Nie rozpoczęte")
        s = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        return {"W trakcie": 0, "Nie rozpoczęte": 1, "NIEZALICZONY": 2, "ZALICZONY": 3}.get(s, 4)

    for temat in sorted(dostepne, key=priorytet):
        dane = st.session_state.get("postep_tematow", {}).get(temat, "Nie rozpoczęte")
        status = dane.get("status", "Nie rozpoczęte") if isinstance(dane, dict) else dane
        
        if status == "ZALICZONY":
            st.success(f"✅ {temat}")
        elif status == "W trakcie":
            st.info(f"🔄 {temat}")
        elif status == "NIEZALICZONY":
            st.error(f"❌ {temat} (niezaliczony)")
        else:
            st.warning(f"🚩 {temat}")
        
    st.markdown("---")
    
    tematy_do_wyboru = [
        t for t in dostepne 
        if st.session_state.get("postep_tematow", {}).get(t, {}).get("status") != "ZALICZONY"
    ]
    
    if not tematy_do_wyboru:
        st.success("Wszystkie tematy zostały zaliczone! 🎉")
    else:
        wybor_tematu = st.selectbox(
            "Wybierz temat:", 
            tematy_do_wyboru, 
            key="glowny_wybor_tematu",
            disabled=w_trakcie_testu
        )
        
        if st.button("Rozpocznij lekcję", disabled=w_trakcie_testu):
            if not lekcja_aktywna:
                st.error("Nauczyciel nie aktywował jeszcze lekcji.")
            else:
                st.session_state.aktualny_temat = wybor_tematu
                st.session_state.teorie_lekcji = profil_aktualny.get("teorie_lekcji", {})
                st.session_state.teoria_lekcji = st.session_state.teorie_lekcji.get(wybor_tematu)
                
                stan_tematu = profil_aktualny.get("postep_tematow", {}).get(wybor_tematu, {})
                st.session_state.licznik_zadan = stan_tematu.get("licznik", 0) if isinstance(stan_tematu, dict) else 0
                if isinstance(stan_tematu, dict) and stan_tematu.get("ma_sprawdzian"):
                    ustaw_stan_testu(True)
                
                historia = profil_aktualny.get("historia_czatow", {})
                st.session_state.messages = historia.get(wybor_tematu, []) if isinstance(historia, dict) else []
                
                if not st.session_state.messages:
                    with st.spinner("Inicjalizacja lekcji z AI..."):
                        instrukcja = "Rozpoczynamy lekcję. Wyślij odpowiedź w formacie: [TEORIA]Treść teorii[TEORIA_KONIEC] [ZADANIE]Treść zadania"
                        st.session_state.messages = [{"role": "user", "content": instrukcja}]
                        
                        odp = zapytaj_ai(st.session_state.messages, wybor_tematu, 0)
                        
                        if "[TEORIA]" in odp and "[ZADANIE]" in odp:
                            st.session_state.teoria_lekcji = odp.split("[TEORIA]")[1].split("[TEORIA_KONIEC]")[0].strip()
                            if "teorie_lekcji" not in st.session_state:
                                st.session_state.teorie_lekcji = {}
                            st.session_state.teorie_lekcji[wybor_tematu] = st.session_state.teoria_lekcji
                            
                            zadanie_tresc = odp.split("[ZADANIE]")[1].strip()
                            st.session_state.messages = [{"role": "assistant", "content": zadanie_tresc}]
                            zapisz_profil_w_chmurze_local()
                        else:
                            st.session_state.teoria_lekcji = odp
                            st.session_state.messages = [{"role": "assistant", "content": odp}]
                            zapisz_profil_w_chmurze_local()
                st.rerun()

# =====================================================================
# 4. GŁÓWNY PANEL APLIKACJI
# =====================================================================
if "aktualny_temat" not in st.session_state:
    st.title(f"Cześć **{st.session_state.get('zalogowany_id')}**, który temat robimy?")
    st.subheader("Twój postęp (ostatnie 4 tygodnie)")
    
    dzis = datetime.now()
    tygodnie_dane = {"Tydzień 1": 0, "Tydzień 2": 0, "Tydzień 3": 0, "Tydzień 4": 0}

    for temat, dane in st.session_state.get("postep_tematow", {}).items():
        if isinstance(dane, dict) and dane.get("status") == "ZALICZONY" and dane.get("data"):
            try:
                data_uko = datetime.strptime(dane["data"], "%Y-%m-%d")
                roznica_dni = (dzis - data_uko).days
                
                if 0 <= roznica_dni < 7:
                    tygodnie_dane["Tydzień 1"] += 1
                elif 7 <= roznica_dni < 14:
                    tygodnie_dane["Tydzień 2"] += 1
                elif 14 <= roznica_dni < 21:
                    tygodnie_dane["Tydzień 3"] += 1
                elif 21 <= roznica_dni < 28:
                    tygodnie_dane["Tydzień 4"] += 1
            except ValueError:
                continue 

    st.bar_chart(pd.DataFrame.from_dict(tygodnie_dane, orient='index', columns=['Ilość']))
        
else:
    # SPRAWDZANIE I WYŚWIETLANIE BALONÓW
    if st.session_state.get("pokaz_balony"):
        st.balloons()
        st.toast("🎉 Temat zaliczony!", icon="🎈")
        st.session_state.pokaz_balony = False  # Czyścimy po wyrenderowaniu

    st.caption(f"📖 Temat: {st.session_state.aktualny_temat}")
    
    # --- PRZYCISK WEZWANIA POMOCY (SOS) ---
    stan_pomocy = profil_aktualny.get("potrzebuje_pomocy", False)

    if stan_pomocy:
        if st.button("🟢 Odwołaj wezwanie pomocy", use_container_width=True):
            zapisz_konto(user_id, {
                "potrzebuje_pomocy": False,
                "aktualny_temat_problemu": ""
            }, merge=True)
            wczytaj_profil_z_chmury.clear()
            st.rerun()
    else:
        if st.button("🚨 WEZWIJ NAUCZYCIELA DO POMOCY", use_container_width=True):
            temat = st.session_state.aktualny_temat
            postepy = profil_aktualny.get("postep_tematow", {})
            
            if temat not in postepy:
                postepy[temat] = {"status": "W trakcie", "licznik_sos": 0}
            
            if isinstance(postepy[temat], dict):
                postepy[temat]["licznik_sos"] = postepy[temat].get("licznik_sos", 0) + 1
            
            zapisz_konto(user_id, {
                "potrzebuje_pomocy": True,
                "aktualny_temat_problemu": temat,
                "postep_tematow": postepy
            }, merge=True)
            wczytaj_profil_z_chmury.clear()
            st.rerun()

    # --- WERYFIKACJA STANU LEKCJI I INTERFEJS CZATU ---
    if not lekcja_aktywna:
        st.error("🔒 Lekcja zakończona! Czat i zadania zostały zablokowane.")
        if st.session_state.get("teoria_lekcji"):
            with st.expander("📘 MATERIAŁY (Tylko podgląd)", expanded=True):
                st.markdown(st.session_state.teoria_lekcji)
    else:
        st.subheader("Postęp w temacie:")
        licznik = st.session_state.get("licznik_zadan", 0)
        st.progress(min(licznik / 8, 1.0))
        st.caption(f"Wykonano zadań: {licznik} / 8")
        
        czy_sprawdzian = any("sprawdzający" in m["content"] for m in st.session_state.messages)
        
        if st.session_state.get("teoria_lekcji") and not czy_sprawdzian:
            with st.expander("📘 MATERIAŁY", expanded=True):
                st.markdown(st.session_state.teoria_lekcji)
                
        if st.session_state.messages:
            ostatnia = st.session_state.messages[-1]
            with st.chat_message(ostatnia["role"]):
                st.markdown(ostatnia["content"])
                
        if prompt := st.chat_input("Napisz odpowiedź..."):
            stan_tematu = st.session_state.postep_tematow.get(st.session_state.aktualny_temat, {})
            status = stan_tematu.get("status") if isinstance(stan_tematu, dict) else stan_tematu
            
            if status in ["Nie rozpoczęte", None]:
                st.session_state.postep_tematow[st.session_state.aktualny_temat] = {"status": "W trakcie"}
                zapisz_profil_w_chmurze_local() 
            
            st.session_state.messages.append({"role": "user", "content": prompt})
            
            with st.spinner("Myślę..."):
                obecny_licznik = st.session_state.get("licznik_zadan", 0)
                temat_aktyw = st.session_state.aktualny_temat
                odp = zapytaj_ai(st.session_state.messages, temat_aktyw, obecny_licznik)
                
                if odp.startswith("❌"):
                    st.error(f"AI zwróciło błąd: {odp}")
                else:
                    if "[SPRAWDZIAN]" in odp:
                        if "postep_tematow" not in st.session_state:
                            st.session_state.postep_tematow = {}
                        if not isinstance(st.session_state.postep_tematow.get(temat_aktyw), dict):
                            st.session_state.postep_tematow[temat_aktyw] = {"status": "W trakcie", "licznik": obecny_licznik}
                        st.session_state.postep_tematow[temat_aktyw]["ma_sprawdzian"] = True
                        ustaw_stan_testu(True)
                        odp = odp.replace("[SPRAWDZIAN]", "").strip()
                        
                    if "[KONIEC SPRAWDZIANU]" in odp:
                        ustaw_stan_testu(False)
                        if "postep_tematow" in st.session_state and isinstance(st.session_state.postep_tematow.get(temat_aktyw), dict):
                            st.session_state.postep_tematow[temat_aktyw]["ma_sprawdzian"] = False
                        odp = odp.replace("[KONIEC SPRAWDZIANU]", "").strip()

                    if "GRATULACJE! Temat ZALICZONY" in odp:
                        st.session_state.pokaz_balony = True
                        st.session_state.postep_tematow[st.session_state.aktualny_temat] = {
                            "status": "ZALICZONY",
                            "data": datetime.now().strftime("%Y-%m-%d"),
                            "licznik": st.session_state.licznik_zadan
                        }
                        st.success("🎉 GRATULACJE! Temat ZALICZONY. Masz czas wolny, możesz zrobić następny temat albo i nie.")

                    if "[ZALICZONE]" in odp:
                        st.session_state.licznik_zadan = obecny_licznik + 1
                    
                    czysta_odp = odp.replace("[ZALICZONE]", "").strip()
                    st.session_state.messages.append({"role": "assistant", "content": czysta_odp})
                    
                    if not isinstance(st.session_state.get("historia_czatow"), dict):
                        st.session_state.historia_czatow = {}
                    st.session_state.historia_czatow[st.session_state.aktualny_temat] = st.session_state.messages
                    
                    zapisz_profil_w_chmurze_local()
                    st.rerun()