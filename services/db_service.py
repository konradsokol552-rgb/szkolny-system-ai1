from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import streamlit as st
from google.cloud import firestore
from google.oauth2 import service_account

from config import (
    NAZWA_SZKOLY,
    COL_KONTA,
    COL_KLASY,
    COL_PRZEDMIOTY,
    COL_LEKCJE,
    DOC_LEKCJA_GLOBAL,
    STREFA_PL
)


@st.cache_resource
def get_db() -> firestore.Client:
    """Tworzy i buforuje połączenie z Firestore."""
    if "connections" not in st.secrets or "firestore" not in st.secrets["connections"]:
        st.error("Brak konfiguracji Firestore w secrets.toml!")
        st.stop()
    key_dict = st.secrets["connections"]["firestore"]
    creds = service_account.Credentials.from_service_account_info(key_dict)
    return firestore.Client(credentials=creds, project=key_dict["project_id"])


def get_szkola_doc():
    return get_db().collection("szkola").document(NAZWA_SZKOLY)


def get_konta_ref():
    return get_szkola_doc().collection(COL_KONTA)


def get_klasy_ref():
    return get_szkola_doc().collection(COL_KLASY)


def get_przedmioty_ref():
    return get_szkola_doc().collection(COL_PRZEDMIOTY)


def get_lekcje_ref():
    return get_szkola_doc().collection(COL_LEKCJE)


# --- ZARZĄDZANIE KONTAMI ---

def pobierz_konto(account_id: str) -> Optional[Dict[str, Any]]:
    """Pobiera dane konta z bazy danych."""
    doc = get_konta_ref().document(account_id).get()
    if doc.exists:
        return doc.to_dict()
    return None


def zapisz_konto(account_id: str, data: Dict[str, Any], merge: bool = True) -> None:
    """Zapisuje lub aktualizuje konto użytkownika."""
    klasa = data.get("klasa", "")
    if isinstance(klasa, str) and klasa.strip():
        get_klasy_ref().document(klasa.strip()).set({"nazwa": klasa.strip()}, merge=True)
    get_konta_ref().document(account_id).set(data, merge=merge)


def usun_konto(account_id: str) -> None:
    """Usuwa konto o danym ID."""
    get_konta_ref().document(account_id).delete()


def pobierz_wszystkie_konta() -> List[Dict[str, Any]]:
    """Pobiera listę wszystkich kont w szkole."""
    lista = []
    for doc in get_konta_ref().stream():
        dane = doc.to_dict()
        dane["id"] = doc.id
        lista.append(dane)
    return lista


def pobierz_uczniow_klasy(klasa: str) -> List[Any]:
    """Pobiera listę dokumentów uczniów należących do danej klasy."""
    if not klasa:
        return []
    try:
        return list(
            get_konta_ref()
            .where("rola", "==", "uczen")
            .where("klasa", "==", klasa)
            .stream()
        )
    except Exception as e:
        st.error(f"Błąd podczas pobierania uczniów: {e}")
        return []


def odblokuj_antycheat_ucznia(uczen_id: str) -> bool:
    """Usuwa blokadę anty-cheat dla wybranego ucznia."""
    try:
        get_konta_ref().document(uczen_id).update({
            "blokada_do": firestore.DELETE_FIELD,
            "sygnal_oszustwa": False
        })
        return True
    except Exception as e:
        st.error(f"Błąd odblokowania ucznia {uczen_id}: {e}")
        return False


def zresetuj_dane_ucznia(uczen_id: str) -> bool:
    """Resetuje postępy, historię czatów i zgłoszenia SOS ucznia."""
    try:
        get_konta_ref().document(uczen_id).update({
            "postep_tematow": {},
            "historia_czatow": {},
            "teorie_lekcji": {},
            "potrzebuje_pomocy": False,
            "aktualny_temat_problemu": ""
        })
        return True
    except Exception as e:
        st.error(f"Błąd resetowania danych ucznia {uczen_id}: {e}")
        return False


@st.cache_data(ttl=10)
def wczytaj_profil_z_chmury(identyfikator: str) -> Optional[Dict[str, Any]]:
    """Pobiera profil ucznia z cache'owaniem."""
    return pobierz_konto(identyfikator)


def zapisz_profil_do_chmury(identyfikator: str, dane: Dict[str, Any]) -> None:
    """Zapisuje profil ucznia i unieważnia cache."""
    zapisz_konto(identyfikator, dane, merge=True)
    wczytaj_profil_z_chmury.clear()


# --- ZARZĄDZANIE PRZEDMIOTAMI ---

def pobierz_przedmioty() -> Dict[str, List[str]]:
    """Pobiera mapę przedmiotów wraz z przypisanymi tematami."""
    struktura = {}
    for doc in get_przedmioty_ref().stream():
        tematy = doc.to_dict().get("lista_tematow", [])
        if not isinstance(tematy, list):
            tematy = [str(tematy)]
        struktura[doc.id] = tematy
    return struktura


def zapisz_przedmiot(nazwa: str, tematy: List[str]) -> None:
    """Dodaje lub aktualizuje przedmiot i jego listę tematów."""
    if nazwa.strip():
        get_przedmioty_ref().document(nazwa.strip()).set({"lista_tematow": tematy}, merge=True)


def usun_przedmiot(nazwa: str) -> None:
    """Usuwa dany przedmiot z bazy."""
    if nazwa.strip():
        get_przedmioty_ref().document(nazwa.strip()).delete()


# --- ZARZĄDZANIE CZASEM LEKCJI ---

def pobierz_status_lekcji_globalnej() -> Optional[Dict[str, Any]]:
    """Pobiera dokument globalnej lekcji."""
    doc = get_lekcje_ref().document(DOC_LEKCJA_GLOBAL).get()
    if doc.exists:
        return doc.to_dict()
    return None


def aktywuj_lekcje_globalna(godziny: float = 1.0) -> None:
    """Aktywuje lekcję na zadany czas od teraz."""
    nowa_blokada = datetime.now(STREFA_PL) + timedelta(hours=godziny)
    get_lekcje_ref().document(DOC_LEKCJA_GLOBAL).set({
        "godzina_blokady": nowa_blokada.strftime("%Y-%m-%d %H:%M:%S")
    })
