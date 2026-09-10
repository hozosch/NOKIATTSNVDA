#!/usr/bin/env python3
"""Shared practical text coverage for the native Nokia frontends.

The reference sentences in the per-model smoke tests verify exact PCM, but a
single sentence covers only a small part of a language frontend.  These cases
exercise the kinds of independent utterances that NVDA and Windows actually
send while navigating, as well as character classes and longer free text.
"""
from __future__ import annotations


COMMON_CASES = (
    ("desktop", "Desktop"),
    ("start", "Start"),
    ("start-menu", "Startmenü"),
    ("taskbar", "Taskleiste"),
    ("search", "Suchfeld"),
    ("settings", "Einstellungen"),
    ("system", "System"),
    ("display", "Anzeige"),
    ("sound", "Sound"),
    ("notifications", "Benachrichtigungen"),
    ("quick-settings", "Schnelleinstellungen"),
    ("file-explorer", "Datei-Explorer"),
    ("this-pc", "Dieser PC"),
    ("downloads", "Downloads"),
    ("documents", "Dokumente"),
    ("recycle-bin", "Papierkorb"),
    ("button", "Schaltfläche"),
    ("checked", "Kontrollkästchen aktiviert"),
    ("not-checked", "Kontrollkästchen nicht aktiviert"),
    ("edit", "Bearbeitungsfeld"),
    ("list", "Liste mit fünf Einträgen"),
    ("tab", "Registerkarte Allgemein ausgewählt"),
    ("dialog", "Dialogfeld Eigenschaften"),
    ("window", "Fenster"),
    ("link", "Link"),
    ("heading", "Überschrift Ebene eins"),
    ("table-cell", "Zeile eins Spalte zwei"),
    ("nvda-menu", "NVDA Menü"),
    ("options-submenu", "Optionen Untermenü"),
    ("tools-submenu", "Werkzeuge Untermenü"),
    ("umlauts", "Ärger, Öl, Übergröße, äußerst, Straße und Grüße."),
    ("pangram", "Franz jagt im komplett verwahrlosten Taxi quer durch Bayern."),
    ("lowercase", "abcdefghijklmnopqrstuvwxyz"),
    ("uppercase", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ("digits", "null eins zwei drei vier fünf sechs sieben acht neun"),
    ("number-sequence", "0 1 2 3 4 5 6 7 8 9 10 42 100 1000 1234567890"),
    ("signed-decimal", "minus zweitausendzwei, plus zwölf Komma fünf Prozent"),
    ("date-time", "Donnerstag, 10. September 2026, 12 Uhr 34"),
    ("file-path", "C Doppelpunkt Backslash Benutzer Backslash Dokumente Backslash test.txt"),
    ("url", "https Doppelpunkt Schrägstrich Schrägstrich www Punkt example Punkt com"),
    ("email", "max Punkt mustermann at example Punkt com"),
    ("identifier", "nokia_runtime_n85_arm64ec.dll"),
    (
        "stored-settings",
        "Aktuell gespeicherte Einstellungen für die Anmeldung und "
        "Sicherheitsmeldungen verwenden, benötigt Administratorberechtigungen.",
    ),
    (
        "long-paragraph",
        "NVDA ist ein freier Bildschirmleser für Windows. Beim Navigieren "
        "werden Fenstertitel, Menüs, Schaltflächen, Tabellen, Links und "
        "Statusmeldungen gesprochen. Dieser längere Absatz prüft, ob die "
        "native Nokia-Sprachausgabe verschiedene Wörter, Umlaute, Zahlen wie "
        "2026 und mehrere Satzgrenzen ohne einen Laufzeitfehler verarbeitet.",
    ),
    (
        "runtime-error",
        "RuntimeError: Native runtime error -2002; model=n85, "
        "runtimeArch=arm64ec, runtimeDll=nokia_runtime_n85_arm64ec.dll, "
        "failedPc=0x82048502, failedYieldReason=0x00000003, failedStage=5.",
    ),
    (
        "reported-6650-runtime-error",
        "RuntimeError: Native runtime error -2002; model=6650, "
        "runtimeArch=arm64ec, runtimeDll=nokia_runtime_6650_arm64ec.dll, "
        "klattFailure=0x00000000, klattR0=0x00000000, "
        "klattR1=0x00000000, klattR2=0x00000000, "
        "klattR3=0x00000000, klattRSp=0x00000000, "
        "klattCount=0x00000000, klattGain=0x00000000, "
        "klattLastPc=0x00000000, klattLastR0=0x00000000, "
        "klattLastR7=0x00000000, klattBadAddress=0x00000000, "
        "failedLastPc=0x82a5b482, failedPc=0x82a5b454, "
        "failedLr=0x82a5b481, failedSp=0x600fed68, "
        "failedFlags=0x60000000, failedBadAddress=0x00000000, "
        "failedYieldPc=0x82a5b454, failedYieldReason=0x00000003, "
        "failedEntry=0x823de64d, failedStage=0x00000005, "
        "finalLastPc=0x823e0f22, finalBadAddress=0x00000000, "
        "finalYieldPc=0x82a5b454, finalYieldReason=0x00000003",
    ),
    (
        "reported-n85-runtime-error",
        "RuntimeError: Native runtime error -2002; model=n85, "
        "runtimeArch=arm64ec, runtimeDll=nokia_runtime_n85_arm64ec.dll, "
        "klattFailure=0x00000000, klattR0=0x00000000, "
        "klattR1=0x00000000, klattR2=0x00000000, "
        "klattR3=0x00000000, klattRSp=0x00000000, "
        "klattCount=0x00000000, klattGain=0x00000000, "
        "klattLastPc=0x00000000, klattLastR0=0x00000000, "
        "klattLastR7=0x00000000, klattBadAddress=0x00000000, "
        "failedLastPc=0x82047ede, failedPc=0x82047eb0, "
        "failedLr=0x82047edd, failedSp=0x600fed68, "
        "failedFlags=0x60000000, failedBadAddress=0x00000000, "
        "failedYieldPc=0x82047eb0, failedYieldReason=0x00000003, "
        "failedEntry=0x81c2c81d, failedStage=0x00000005, "
        "finalLastPc=0x81c2f102, finalBadAddress=0x00000000, "
        "finalYieldPc=0x82047eb0, finalYieldReason=0x00000003",
    ),
)


MODEL_LANGUAGE_CASES = {
    "6650": {
        10: (
            ("native-plain", "The quick brown fox jumps over the lazy dog."),
            ("native-ui", "Settings, notifications, tools, options, and help."),
            ("native-mixed", "NVDA version 2026.3, file test.txt, value 42 percent."),
        ),
        51: (
            ("native-plain", "Portez ce vieux whisky au juge blond qui fume."),
            ("native-ui", "Paramètres, notifications, outils, options et aide."),
            ("native-accents", "À bientôt, élève, Noël, français, cœur et où."),
        ),
        76: (
            ("native-plain", "A rápida raposa marrom pula sobre o cão preguiçoso."),
            ("native-ui", "Configurações, notificações, ferramentas, opções e ajuda."),
            ("native-accents", "Olá, ação, coração, manhã, você, avô e avó."),
        ),
        83: (
            ("native-plain", "El veloz murciélago hindú comía feliz cardillo y kiwi."),
            ("native-ui", "Configuración, notificaciones, herramientas, opciones y ayuda."),
            ("native-accents", "Árbol, niño, corazón, pingüino, acción y México."),
        ),
    },
    "n85": {
        39: (
            ("native-plain", "Kumusta, nagsasalita ako ng Tagalog sa Nokia N85."),
            ("native-ui", "Mga setting, abiso, kasangkapan, pagpipilian at tulong."),
            ("native-mixed", "NVDA bersyon 2026.3, file test.txt, bilang 42."),
        ),
        96: (
            ("native-plain", "Xin chào, tôi nói tiếng Việt trên Nokia N85."),
            ("native-ui", "Cài đặt, thông báo, công cụ, tùy chọn và trợ giúp."),
            ("native-accents", "Tiếng Việt có dấu: ă â đ ê ô ơ ư á à ả ã ạ."),
        ),
    },
}


def cases_for(model: str, language_id: int):
    """Yield labelled, non-empty utterances for one model/language."""
    yield from COMMON_CASES
    yield from MODEL_LANGUAGE_CASES[model][language_id]
