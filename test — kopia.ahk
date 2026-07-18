#NoEnv
#SingleInstance Force

; 1. Odpalenie Chrome w trybie kiosku
Run, "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk https://szkolny-system-ai.streamlit.app

; 2. Ustawienie timera na 45 minut (lekcja)
SetTimer, ZamknijKiosk, -2700000
return

; =============================================================================
; 3. CZYSTA BLOKADA KLAWISZY (Brak jakiegokolwiek monitorowania stron)
; =============================================================================
!F4::return      ; Blokuje Alt + F4
^w::return       ; Blokuje Ctrl + W
LWin::return     ; Blokuje lewy klawisz Windows
RWin::return     ; Blokuje prawy klawisz Windows
!Tab::return     ; Blokuje Alt + Tab

; Blokada kliknięć myszką do otwierania linków w tle:
MButton::return  ; Blokuje kliknięcie kółkiem myszy
^LButton::return ; Blokuje Ctrl + Lewy Klik
+LButton::return ; Blokuje Shift + Lewy Klik

; =============================================================================
; 4. TAJNY SKRÓT DLA NAUCZYCIELA Z HASŁEM (Ctrl + Shift + K)
; =============================================================================
^+k::
InputBox, WpisaneHaslo, Autoryzacja systemowa, Podaj haslo nauczyciela:, HIDE, 260, 130
if (ErrorLevel) 
    return

if (WpisaneHaslo = "1234")
{
    Process, Close, chrome.exe
    ExitApp
}
else
{
    MsgBox, 48, Blad, Niepoprawne haslo!, 2
}
return

; =============================================================================
; 5. FUNKCJE SYSTEMOWE
; =============================================================================
ZamknijKiosk:
Process, Close, chrome.exe
ExitApp