#NoEnv
#SingleInstance Force

; Zmienna globalna przechowująca unikalne ID głównego okna aplikacji
global MainKioskHWND := 0

; 1. Odpalenie Chrome w trybie kiosku
Run, "C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk https://szkolny-system-ai.streamlit.app

; 2. Przechwycenie uchwytu systemowego (HWND) okna Kiosku zaraz po jego aktywacji
WinWaitActive, ahk_exe chrome.exe,, 10
if (!ErrorLevel)
{
    WinGet, MainKioskHWND, ID, A
}

; 3. Ustawienie czasu lekcji na 45 minut
SetTimer, ZamknijKiosk, -2700000

; 4. BEZPIECZNY START: Czekamy 15 sekund na pełne załadowanie aplikacji i stabilizację tytułu okna.
; Przez te 15 sekund uczniowie mają zablokowane klawisze, ale skrypt nie zabije Chrome.
SetTimer, UruchomStraznika, -15000
return

UruchomStraznika:
SetTimer, PilnujAplikacji, 1000
return

; =============================================================================
; 5. BLOKADA KLAWISZY UCIECZKI I OTWIERANIA NOWYCH KART
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
; 6. TAJNY SKRÓT DLA NAUCZYCIELA Z HASŁEM (Ctrl + Shift + K)
; =============================================================================
^+k::
InputBox, WpisaneHaslo, Autoryzacja systemowa, Podaj haslo nauczyciela:, HIDE, 260, 130
if (ErrorLevel) 
    return

if (WpisakaHaslo = "1234" or WpisaneHaslo = "1234") ; Zabezpieczenie przed literówką
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
; 7. FUNKCJE SYSTEMOWE MONITORA
; =============================================================================

ZamknijKiosk:
Process, Close, chrome.exe
ExitApp

PilnujAplikacji:
; Pobieramy ID oraz proces okna, które aktualnie znajduje się na pierwszym planie
WinGet, ActiveHWND, ID, A
WinGet, ActiveProcess, ProcessName, A

; Interweniujemy tylko wtedy, gdy akcja dotyczy przeglądarki Chrome
if (ActiveProcess = "chrome.exe")
{
    ; SCENARIUSZ A: Użytkownik jest w głównym oknie aplikacji
    if (ActiveHWND = MainKioskHWND)
    {
        WinGetActiveTitle, TytulOkna
        StringLower, TytulMaly, TytulOkna
        
        ; Ignoruj puste stany przejściowe
        if (TytulMaly = "")
            return
            
        ; Jeśli tytuł nie zawiera autoryzowanych fraz z konfiguracji Pythona
        if (!InStr(TytulMaly, "szkolny") and !InStr(TytulMaly, "streamlit"))
        {
            ; Zamiast ubijać okno, bezwzględnie cofamy użytkownika wstecz
            Send, !{Left}
        }
    }
    ; SCENARIUSZ B: Otworzyło się NOWE okno Chrome (pop-up, nowa karta z linku zewnętrznego)
    else
    {
        ; Ponieważ to nie jest nasze główne okno aplikacji, bezpiecznie je uśmiercamy
        WinClose, A
        
        ; Wymuszamy powrót fokusu na główne okno egzaminacyjne
        if (MainKioskHWND != 0)
        {
            WinActivate, ahk_id %MainKioskHWND%
        }
    }
}
return