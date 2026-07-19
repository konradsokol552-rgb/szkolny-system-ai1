#NoEnv
#SingleInstance Force
Process, Close, chrome.exe
Sleep, 300

; 1. Odpalenie Chrome w trybie kiosku
Run, "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk --incognito --disable-session-crashed-bubble https://szkolny-system-ai.streamlit.app

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
; Agresywne ukrycie paska zadań i przycisku Start przed pokazaniem okna hasła
WinHide, ahk_class Shell_TrayWnd
WinHide, ahk_class Start

InputBox, WpisaneHaslo, Autoryzacja systemowa, Podaj haslo nauczyciela:, HIDE, 260, 130

; Jeśli nauczyciel kliknie "Anuluj" (Cancel) lub zamknie krzyżykiem
if (ErrorLevel) 
{
    ; Przywracamy pasek, bo wracamy do systemu/kiosku, Chrome znowu go zasłoni
    WinShow, ahk_class Shell_TrayWnd
    WinShow, ahk_class Start
    return
}

if (WpisaneHaslo = "1234")
{
    Process, Close, chrome.exe
    ; Przywracamy pasek zadań pracowni szkolnej do normalnego stanu
    WinShow, ahk_class Shell_TrayWnd
    WinShow, ahk_class Start
    ExitApp
}
else
{
    MsgBox, 48, Blad, Niepoprawne haslo!, 2
    ; Jeśli hasło było błędne, upewniamy się, że pasek nadal jest ukryty
    WinHide, ahk_class Shell_TrayWnd
    WinHide, ahk_class Start
}
return

; =============================================================================
; 5. FUNKCJE SYSTEMOWE
; =============================================================================
ZamknijKiosk:
Process, Close, chrome.exe
ExitApp