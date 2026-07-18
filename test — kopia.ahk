#NoEnv
#SingleInstance Force

; 1. Odpalenie Chrome w trybie kiosku
Run, "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk https://szkolny-system-ai.streamlit.app

; 2. Ustawienie timera na 45 minut (lekcja)
SetTimer, ZamknijKiosk, -2700000

; ZABEZPIECZENIE LINKÓW: Sprawdzaj co 1 sekundę, czy uczeń nie uciekł ze strony
SetTimer, PilnujAplikacji, 1000
return

; =============================================================================
; 3. BLOKADA KLAWISZY UCIECZKI I OTWIERANIA NOWYCH KART
; =============================================================================
!F4::return      ; Blokuje Alt + F4
^w::return       ; Blokuje Ctrl + W (zamknięcie karty)
LWin::return     ; Blokuje lewy klawisz Windows (menu Start)
RWin::return     ; Blokuje prawy klawisz Windows
!Tab::return     ; Blokuje Alt + Tab (przełączanie okien)

; Blokada sprytnych kliknięć myszką do otwierania linków w tle:
MButton::return  ; Blokuje kliknięcie kółkiem myszy (Middle Click)
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
; 5. FUNKCJE SYSTEMOWE (TIMERY)
; =============================================================================

; Funkcja wywoływana automatycznie po 45 minutach
ZamknijKiosk:
Process, Close, chrome.exe
ExitApp

; Nowa funkcja - zawraca użytkownika zamiast zamykać aplikację
PilnujAplikacji:
IfWinExist, ahk_exe chrome.exe
{
    WinGetActiveTitle, TytulOkna
    StringLower, TytulMaly, TytulOkna
    
    ; Jeśli okno jest aktywne, ale w tytule NIE MA ściśle nazwy Twojej aplikacji
    ; Oznacza to, że uczeń przeszedł na inną stronę (np. GitHub lub logowanie Streamlit)
    if (TytulMaly != "" and !InStr(TytulMaly, "szkolny system ai"))
    {
        ; Wyślij skrót Alt + Strzałka w lewo (wstecz w przeglądarce)
        Send, !{Left}
        
        ; Dodatkowo na wypadek gdyby otworzyło się nowe okno (pop-up), zamykamy je
        ; bez ubijania głównego procesu Chrome
        IfWinNotActive, Szkolny System AI
        {
            WinClose, A
        }
    }
}
return