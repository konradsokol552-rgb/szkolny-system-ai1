; --- KONFIGURACJA ---
URL := "https://szkolny-system-ai.streamlit.app" ; Adres Twojej aplikacji szkolnej
HasloWyjsciowe := "1234"                       ; Twoje tajne hasło

; Ścieżka do launchera Opery GX (użycie launcher.exe jest kluczowe dla parametrów!)
SciezkaOpery := "C:\Users\" . A_UserName . "\AppData\Local\Programs\Opera GX\opera.exe"

; --- ZABEZPIECZENIE: ZAMKNIĘCIE OPERY DZIAŁAJĄCEJ W TLE ---
; Dzięki temu tryb kiosk/app zawsze uruchomi się poprawnie zamiast nowej karty
Process, Exist, opera.exe
if ErrorLevel
{
    Process, Close, opera.exe
    Sleep, 1000 ; Czekamy sekundę na zamknięcie procesów
}

; --- URUCHOMIENIE PRZEGLĄDARKI W TRYBIE KIOSKU ---
Run, "%SciezkaOpery%" --start-fullscreen --app=%URL%

; Czekamy na uruchomienie i aktywujemy okno
WinWait, ahk_exe opera.exe
WinActivate, ahk_exe opera.exe

Return ; Koniec sekcji startowej

; =========================================================
; --- BLOKADA KLAWISZY I SKRÓTÓW ---
; =========================================================

LWin::Return       
RWin::Return       
!F4::Return        
!Tab::Return       
F11::Return        
^t::Return         
^n::Return         
^w::Return         
^h::Return         
^j::Return         
^+i::Return   
F12::Return        

; =========================================================
; --- SEKRETNY SKRÓT ODBLOKOWUJĄCY (Ctrl + Shift + K) ---
; =========================================================
^+k::
; Używamy trybu AlwaysOnTop dla okna wpisywania, aby przeglądarka go nie przykryła
Gui +OwnDialogs 
InputBox, WpisaneHaslo, Kiosk Mode, Wpisz haslo aby wyjsc:, hide, 220, 140

; Jeśli użytkownik kliknął "Anuluj" lub zamknął okienko krzyżykiem
if ErrorLevel 
{
    Return ; Po prostu wracamy do trybu blokady, skrót zadziała ponownie
}

if (WpisaneHaslo = HasloWyjsciowe)
{
    Process, Close, opera.exe
    ExitApp
}
else
{
    MsgBox, 48, Błąd, Błędne hasło! Spróbuj ponownie.
}
Return