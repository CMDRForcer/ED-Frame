# Handelsrouten – lokaler Rundtour-Teststand

Stand: 11. Oktober 2026. **A → B → A ist lokal eingebaut.** Der neue
Server-Endpunkt wurde nach ausdrücklicher Freigabe isoliert geprüft und
auf dem produktiven Server aktiviert. Die laufende Benutzer-App wurde nicht ersetzt. Kein Commit,
Git-Push oder Release wurde für diesen Ausbau erstellt.

## Bedienung und Ergebnisse

Unter Navigation gibt es den Reiter **Handelsrouten**. Die Darstellung
orientiert sich an [Inaras Rundtour-Übersicht](https://inara.cz/elite/market-traderoutes/)
und verwendet den eigenen ED-Frame-Stil. Zwei Stationskarten und getrennte
Zeilen zeigen die Hinfracht und die automatisch gewählte Rückfracht:
Ware, tatsächlich mögliche Menge, beobachtete Preise, Einkaufskosten,
Bestand, Nachfrage und geschätzten Gewinn. Dazu kommen Anreise, Rundtour-
Entfernung, Alter der ältesten Preisbeobachtung und Zugangshinweise.

Ausgangssystem, Frachtlimit, Einkaufsbudget, Suchradius, maximale Strecke
A–B, Datenalter, Landeplatz, Carrier und Sortierung sind einstellbar.
Schiffswerte können übernommen werden; bekannte 0 Credits bleiben 0.
Die Schiffskapazität ist nicht zwingend der freie Frachtraum. Die
Warensuche kann eine ausgewählte Ware und ihr Ausgangssystem direkt in
die Rundtour-Suche übernehmen. Eine bestimmte Hinfracht schränkt die
Rückfracht nicht auf dieselbe Ware ein.

Nach der Suche klappen die Filter ein, damit mehr Platz für Ergebnisse
bleibt. Sie sind jederzeit wieder erreichbar. Eine Route lässt sich
auswählen; beide Systemnamen können kopiert werden. „Preise erneut prüfen“
wiederholt die letzte abgeschlossene Suche, auch wenn inzwischen andere
Filter eingetragen wurden.

## Überarbeitete Ergebnisdarstellung

Die ausgewählte Rundtour zeigt den geschätzten Gesamtgewinn als große grüne
Zahl. System A und B sowie cyanfarbene Hinfracht und orangefarbene Rückfracht
bilden zwei klare Spalten. Kauf- und Verkaufspreise stehen getrennt; Menge
und Gewinn bleiben je Fracht sichtbar. Anreise, Rundtour, Preisalter und
kombinierte Spanne/T bilden eine eigene Kennzahlenzeile. Weitere Routen
erscheinen kompakter und werden bei Auswahl ausführlich dargestellt.

„Details“ ergänzt Einkaufskosten, Bestand, Nachfrage, Landeplatz und
Stationszugang. Filterbearbeitung, Preisprüfung und Suche stehen in einer
gemeinsamen Leiste. Unveränderte Ergebnisse behalten ihre Karten beim
Wechsel der Auswahl oder des Suchstatus; es entstehen keine zusätzlichen
Serverabfragen. Die Darstellung liegt im selben lokalen Testpaket.

## Berechnung und Last

Beide Richtungen brauchen positive beobachtete Preisunterschiede sowie
bekannten Bestand und Nachfrage. Menge und Budget werden je Strecke
begrenzt. Die Rückfracht kann den Gewinn aus dem ersten Verkauf verwenden.
Ein synthetisches Beispiel: 50 CR Startbudget, 5 T Hinfracht zu 10 CR/T
einkaufen und zu 20 CR/T verkaufen; danach 100 CR verfügbar. Rückfracht
5 T zu 20 CR/T einkaufen und zu 30 CR/T verkaufen. Rundtourgewinn 100 CR,
Endbudget 150 CR. Der Client prüft die Rechnung und Geometrie erneut.

Für eine begrenzte regionale Auswahl werden bis zu 320 Märkte und
80 Startmärkte geprüft. Alle brauchbaren Warenpreise dieser Märkte gehen
in die Rechnung ein; vollständige Rundtouren werden erst danach sortiert.
Die Oberfläche kennzeichnet eine Teilauswahl und nennt die Abdeckung.
Sie verspricht kein vollständiges Optimum über sämtliche Katalogmärkte.
Die kombinierte Spanne/T ist die Summe beider Preisunterschiede; bei
unterschiedlichen Mengen entspricht sie nicht Gesamtgewinn/Frachtlimit.

SQL läuft lesend mit 10 Sekunden Statement- und 2 Sekunden Lock-Limit.
Die Berechnung hat eine 5-Sekunden-Frist. Ein gemeinsamer Datenbank-Lock
begrenzt gleichzeitige Rundtour-Berechnungen über die API-Worker hinweg.
Bis zu acht Suchen je Worker werden 60 Sekunden zwischengespeichert.
Der Snapshot-Zeitpunkt bleibt bei Cache-Treffern erhalten.

Ein lokaler synthetischer Lasttest mit 320 Märkten, 100.800 Preiszeilen
und 12.800 vollständigen Rundtouren benötigte **2,033 Sekunden** für die
Berechnung. Im getrennten Testcontainer mit einem CPU-Limit von einem Kern
dauerten vier lesende Suchen mit echten Sol-Marktdaten **6,469–9,048 Sekunden**.
Alle lieferten 30 Rundtouren: ALL mit 50/100 LY, ALL ohne Carrier und Gold
mit 50 LY. Dabei wurden je Suche 26.182 bzw. 29.343 Preiszeilen geprüft.
Die Cache-Wiederholung im Prozess dauerte 0,0001 Sekunden. Die App
nutzt einen vorhandenen Netzwerk-Worker, startet Suchen nur per Klick
und übernimmt den abgeschlossenen Stand gebündelt. Es gibt keinen neuen
ständigen Rundtour-Abruf.

## Prüfung

- Vollständiger App-Testlauf vor der optischen Überarbeitung: **1.400 Tests
  bestanden** in 238,277 Sekunden.
- 15 gezielte Modell-, Client- und Controller-Tests bestanden.
- Überarbeitete Main.qml-Oberfläche mit 33 Prüfbereichen in EN 1920×1080,
  DE 1120×700, FR 1366×768 und ES 1120×700 bestanden, einschließlich
  Details, Textgrenzen und Auswahlwechsel. Zusammen mit sechs Sprachtests
  bestanden sieben gezielte Unittests in 27,215 Sekunden.
  Die frühere Rundtour-Ansicht bestand auch direkt nach den 43 Prüfbereichen
  für Warensuche, Mining und Diagnose.
- 182 Servertests lokal sowie im getrennten Linux-Image bestanden, mit
  gemockter Datenbank und echtem ASGI-Vertrag einschließlich Eingabevalidierung.
- 35 Prüfbereiche der finalen portablen App bestanden, einschließlich
  vorhandener separater Mining-, Journal- und Powerplay-Berechnungen.
- Alle neun betroffenen QML-/Sprachressourcen und drei eingebettete
  Python-Module stimmen mit dem aktuellen Quellstand überein.
- Keine privaten Profile, Journale, Konfigurationen oder Schlüssel im
  Testpaket; das Certifi-CA-Zertifikat entspricht der Bibliothek.
- Die übernommenen QML-Ressourcen des Testpakets wurden zusätzlich in
  einem frischen Testprofil mit öffentlichen Sol-Marktdaten bei 1920×1080
  und 1120×700 geladen und aufgenommen. Sieben Prüfbereiche bestanden.

## Serveraktivierung und Test-App

Der Benutzer hat den isolierten Test und die anschließende API-Aktivierung
ausdrücklich freigegeben. Im separaten neuen Image liefen zunächst 182 Tests
ohne Netzwerk. Anschließend wurden vier echte Abfragen in einem eigenen
Container mit PostgreSQL-Read-only-Defaults, 500 MB RAM und einem CPU-Kern
geprüft. Ein früher vorgeschlagener Test im produktiven Container wurde
vom automatischen Freigabecheck abgelehnt und nicht ausgeführt.

Nach bestandenen Prüfungen wurden die fünf betroffenen Quellen und das alte
Image unter `/opt/edframe-deploy-backups/trade-loops-20261011-v1` gesichert.
Nur der API-Dienst wurde ausgetauscht. Aktives Image:
`edframe-catalog-api:0.9.4-trade-loops-20261011-v1`.
Container-Healthcheck und öffentlicher Healthcheck bestanden; die öffentliche
Rundtour-Abfrage lieferte 30 Ergebnisse. Collector, Datenbank und Caddy
behalten exakt dieselben Container-IDs und Startzeitpunkte. Das Mining-
Snapshot-Protokoll bleibt 1; es gab keine neue Schema- oder Indexmigration.

Die zusätzliche öffentliche Prüfung mit dem tatsächlichen App-Client
bestand: ALL und Gold bei Sol, 50 LY, L-Pad, 100 T und 10 Mio. CR lieferten
jeweils 30 validierte Rundtouren. Kalte Abrufe dauerten 11,146 bzw. 8,715
Sekunden; die Cache-Wiederholung 0,020 Sekunden. Zeitstempel und Reihenfolge
blieben dabei identisch. Alle Mengen, Budgets, Gewinne und Entfernungen
bestanden die Clientprüfung. Ungültige Kapazität 0 wird mit HTTP 422
abgewiesen; Discovery nennt den neuen Endpunkt. Die gemessenen Suchen
verwenden eine gekennzeichnete Teilauswahl von 320 Märkten/80 Startmärkten.

Die portable App liegt in
`output/ED-Frame-Trade-Loops-Test-20261011-Windows/ED-Frame/ED-Frame.exe`.
Den gesamten Ordner zusammenlassen. Erst die bisherige App einschließlich
Tray beenden, dann diese EXE starten. Der neue Endpunkt ist aktiv;
die Test-App kann echte Rundtour-Ergebnisse vom Server abrufen.

App-Version bleibt 1.0.8; der Ordner bezeichnet einen lokalen Teststand.
EXE-SHA256: `6d938c7bec61bdef837e2f64c416df9eb97ec15678b35c34b3b195aae0487b1a`.
Die optische Überarbeitung betrifft sechs externe QML-/Sprachressourcen;
die EXE und eingebetteten Python-Module sind unverändert. Die vorherigen
Ressourcen wurden vor dem Austausch lokal gesichert.
