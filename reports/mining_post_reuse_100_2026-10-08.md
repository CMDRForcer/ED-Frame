# MiningFinder: 100-Routen-Messung nach Slot-Fix und regionaler Wiederverwendung

8. Oktober 2026. Punkt 3 des Fahrplans: echte Erst-/Folgesuche einschließlich
gezielter Nachprüfung, RAM, Ergebnisänderungen und Tabwechsel messen.

## Ergebnis

Die regionale Wiederverwendung greift. Sie beseitigt jedoch weder die späte
Nachprüfung noch wiederholte Planungen: Erste 100 Treffer erscheinen nach
**3,2 Sekunden**, die letzte Änderung erst nach **58,3 Sekunden**. Bei der
Folgesuche bleibt die vorherige Liste sofort sichtbar, wird aber bis
**25,6 Sekunden** weiter aktualisiert. Einzelne Tabwechsel stocken während des
Zusammenführens weiter; der RAM-Bedarf bleibt hoch.

Der QML-Slot-Fix funktioniert im echten Suchablauf: Die gezielte Nachprüfung
startet und beendet ihre vorgesehenen Aufgaben ohne QML-/Netzfehler.
**Ein abgeschlossener Prüflauf ist nicht gleichbedeutend mit 100 vollständig
verifizierten Routen.** Die bestehende Marktprüfung ist auf sechs neue Ziele
pro Durchlauf begrenzt. Unbekannte Fakten werden weiterhin nicht bestätigt.

## Messbedingungen

- Quellstand: HEAD `1a59605fa05e646cea7d7d4189011deeffb789d0` mit dem noch
  nicht committeten regionalen Reuse aus Punkt 2. Nicht die installierte EXE.
  Exakte Quellhashes und Git-Status stehen in den Rohdaten.
- Echte Controller, Arbeiter und asynchrone QML-Seiten, Qt/PySide6 6.11.2,
  Python 3.13.15; separater Prozess, offscreen/Software-Renderer, 1600 × 1000.
  Keine Aussage über D3D-Frametimes oder reale Maus-bis-Bild-Latenz.
- Shanteneri, Platinum, Laser, Powerplay Merits / Aisling Duval / Reinforce,
  250 LY, 100 Ergebnisse, Large Pad, Nachfrage 5.000–500.000 t, Marktalter 1 h.
- Finaler Prozess: 331.560 Ringkandidaten, 150.000 Marktzeilen und 91.575
  Powerplay-Katalogzeilen, zusätzlich gespeicherte öffentliche Beobachtungen.
  Startbereitschaft nach 5,937 s. Frischer Prozess und frische Profilkopie,
  aber keine geleerten Windows-/Server-Caches.
- Nur öffentliche GETs; Uploads blockiert. Nur benannte öffentliche Kataloge
  kopiert, SQLite über ein konsistentes Read-only-Backup. Synthetischer
  Commander/Journal, keine echte Commanderhistorie oder Upload-Warteschlange.
- Listener, Sharing und ausgewählte periodische Jobs unterdrückt. Normaler
  State-Finds-Startsync lief mit; dessen HTTP-Verkehr ist separat ausgewiesen.
  Keine BGS-Prognosen verändert.
- „Ruhig“ erfordert tatsächliche Verification-Signale, nicht nur den QML-Marker,
  und drei Sekunden ohne Sync, Planung, Merge, Projektion oder wartende Arbeit.
  Diese zusätzliche Sicherheitszeit ist nicht Bestandteil der letzten Änderung.

## Erst- und Folgesuche

Alle Zeiten ab Auslösen der jeweiligen Suche.

| Messgröße, finaler Kontrolllauf | Erstsuche | Folgesuche |
| --- | ---: | ---: |
| Erste sichtbare Liste | 3,232 s | 0,003 s, vorherige Liste |
| Erste neue Listenveröffentlichung | 3,232 s | 9,198 s |
| Gezielte Prüfung beginnt | 49,619 s | 17,791 s |
| Gezielte Prüfung beendet | 56,752 s | 24,095 s |
| Letzte Listenänderung | 58,250 s | 25,587 s |
| Einschließlich 3 s Ruhe bestätigt | 61,259 s | 28,595 s |
| Neue Listenveröffentlichungen | 6 | 4 |
| Aufrufe der Planungsfunktion | 8 | 5 |
| Kumulierte Planungslaufzeit | 14,886 s | 10,933 s |
| Davon Powerplay-Index, ebenfalls 8 / 5 Aufrufe | 5,366 s | 2,803 s |

Planungszeiten sind Hintergrund-Laufzeiten, keine reine CPU-Zeit. Die
Indexzeiten sind darin enthalten und dürfen nicht zusätzlich addiert werden.

Alle beobachteten Listen hatten 100 Zeilen; kein Leeren auf null wurde in
diesen beiden Suchen erfasst. Die Erstsuche hatte zwei unterschiedliche
Mining-Reihenfolgen; Platz 1 blieb gleich. Die Folgesuche blieb in einer
Reihenfolge. Status-/Preis-/Verkaufsdaten änderten sich trotzdem. Zwei
Veröffentlichungen der Erstsuche waren bezüglich des aufgezeichneten dünnen
Zeilensnapshots unverändert. Das beweist keine vollständige Bytegleichheit
aller QML-Felder. Der Order-Hash verfolgt Mining-Identitäten, nicht allein
die Verkaufsstation.

Der vorausgehende Messlauf bestätigt die Größenordnung: erste Liste 3,357 s,
letzte Änderung 57,686 s; Folgesuche letzte Änderung 25,597 s. Seine Tabzeiten
werden nicht als finale Werte verwendet: Die Zeitnahme unterschlug synchron
im selben Poll abgeschlossene Navigation. Das Messwerkzeug wurde korrigiert
und der gesamte Lauf mit frischer Profilkopie wiederholt.

## Datenabruf und tatsächlicher Reuse

| Domäne | Erstsuche | Folgesuche |
| --- | ---: | ---: |
| Regionale Ringe | 37,260 s, 26 Seiten | 0,603 s, Cachetreffer |
| Regionale Powerplay-Fakten | 7,942 s, 59 Seiten | 5,214 s, 59 neue Seiten |
| Regionale Märkte | 1,628 s | 1,002 s |
| Parallele regionale Gesamtphase | 37,270 s | 5,216 s |
| Regionale GETs ohne gezielte Prüfung | 87 | 61 |
| Mining-GETs einschließlich gezielter Prüfung | 106 | 80 |
| Dekomprimierte Mining-Antwortkörper | 27,593 MiB | 12,218 MiB |

Die Domänen laufen parallel; Zeiten nicht addieren. „Ringe“ umfasst die
Arbeit des Abrufpfads, nicht nur Übertragung auf dem Draht.

24.455 regionale Ringzeilen wurden vollständig wiederverwendet. Das
Powerplay-Reuse-Fenster beträgt bewusst nur 60 s **ab Abrufbeginn** und war
bei dieser Folgesuche bereits abgelaufen (Ring-Cachealter 61,7 s). Deshalb
wurden die rund 33.300 Powerplay-Zeilen korrekt neu geladen. Der kleine
50-LY-Abruftest aus Punkt 2 mit 5 → 2 GETs ist nicht auf diesen vollständigen
100-Routen-Ablauf übertragbar.

Zur Erstsuche kamen 27 State-Finds-Seiten hinzu; zwei weitere waren bereits
beim Start gelaufen. Insgesamt 133 GETs in der Erstsuchphase. Diese Konkurrenz
ist kein zusätzlicher Mining-Abruf. Alle aufgezeichneten Antworten waren
erfolgreich; keine HTTP-Fehler, Timeout-Fehler oder QML-Diagnosen.

## Verifizierung und unbekannte Daten

- Erstsuche: ein gezielter Powerplay-Batch mit 39 deduplizierten Systemen,
  sechs neue Marktziele, zusammen 45 abgeschlossene Checks. Der Batch lieferte
  für diese 39 Systeme keine ausreichend aktuellen Powerplay-Beobachtungen.
  Das ist fehlende Evidenz, kein erfolgreicher Nachweis der Merit-Eignung.
- Folgesuche: ein neues Powerplay-Ziel, sechs neue Marktziele und sechs
  bereits gecachte Marktchecks, zusammen 13 Checks. Ein abgeschlossenes
  negatives Ergebnis ist ebenfalls keine verfügbare Markt-/Powerplay-Bestätigung.
- Finale Erstliste: 3 `VERIFIED`, 8 `POWERPLAY_DATA_MISSING`, 32
  `MARKET_TOO_OLD`, 2 `NO_MARKET_DATA`, 55 `NOT_YET_CHECKED`.
- Finale Folgeliste: 3 `VERIFIED`, 9 `POWERPLAY_DATA_MISSING`, 32
  `MARKET_TOO_OLD`, 3 `NO_MARKET_DATA`, 53 `NOT_YET_CHECKED`.
- In beiden Listen sind auf der unabhängigen Powerplay-Achse 97 von 100
  Routen unbekannt; der kombinierte Hauptstatus kann stattdessen zunächst
  fehlende/veraltete Marktdaten anzeigen. Die Zahlen nicht addieren.
- Alle final angezeigten Mining-Identitäten waren im beim jeweiligen
  Verifizierungsstart beobachteten QML-Eingabestand vorhanden. Das bestätigt
  keinen Einzelcheck jeder Route: Ziele werden dedupliziert und budgetiert.

Ein im vorausgehenden Lauf beobachteter Status „12/12 systems verified“
bezeichnete abgeschlossene/gecachte Checks, obwohl unbekannte Fakten in der
Liste blieben. Die zwei Abschlusszweige in `controller_navigation.py`
verwenden noch „verified“, wenn kein neuer Powerplay-Lookup beteiligt ist.
Diese Formulierung ist zu stark und sollte künftig Checks, Abdeckung und
tatsächlich bestätigte Routen getrennt benennen. In diesem Messschritt wurde
kein Anwendungstext oder Prüfverhalten geändert.

## Speicher und Bedienbarkeit

| RSS des isolierten Testprozesses | Wert |
| --- | ---: |
| Bei Katalogbereitschaft | 946,9 MiB |
| Spitze bis Ende der Erstsuche | 1.257,1 MiB |
| Spitze über beide Suchen | 1.277,3 MiB |
| Spitze einschließlich zusätzlichem Sync/Tabstress | 1.309,0 MiB |
| Am Prozessende | 1.240,3 MiB |

Auch ohne echte Commanderhistorie ist das weiterhin viel RAM. Daraus folgt
noch kein bewiesenes Speicherleck. Regionale Reuse spart Netzwerk-/Abrufarbeit,
ersetzt aber nicht den großen residenten Katalog.

Präziser Qt-Timer, Sollintervall 10 ms; Abstände der Ereignisschleife,
keine Render-Frametimes:

| Phase | p95 | Größter Abstand | Abstände > 500 ms |
| --- | ---: | ---: | ---: |
| Erstsuche | 12,3 ms | 1.310 ms | 4 |
| Folgesuche | 13,8 ms | 1.006 ms | 5 |
| Zusätzlicher Sync mit Tabwechseln | 12,7 ms | 575 ms | 1 |

Nach beiden Suchen wurde ausschließlich im isolierten Controller der regionale
Reuse verworfen und ein weiterer vollständiger Sync ausgelöst. Zehn Runden
über fünf reale asynchrone Seiten, 50 Wechsel, bis nach Merge/Projektion zur
Ruhe. Bereitschaft bedeutet Loader vorhanden/sichtbar, nicht alle Folgearbeit
oder eine gemalte Bildschirmansicht; Pollintervall 25 ms.

| Zielseite | Median | Maximum |
| --- | ---: | ---: |
| Operations | 30 ms | 38 ms |
| Materials | 127 ms | 368 ms |
| Engineering | 43 ms | 1.607 ms |
| CMDR | 32 ms | 61 ms |
| MiningFinder | 32 ms | 162 ms |

Der 1,6-s-Wechsel zu Engineering fiel in den aktiven Merge. Das ist eine
belegte Verzögerung während der Zusammenführung, aber noch kein Beweis für
eine einzelne verursachende Codezeile. Loaderwartezeit und einzelne
Ereignisschleifenpausen sind unterschiedliche Messgrößen. CMDR enthält keine
echte Fleet-Historie; der Wert entkräftet keine Probleme mit großen Nutzerprofilen.

## Nächste Schritte und Nachteile

1. Planungsanlässe zusammenfassen und den Powerplay-Index revisionsgebunden
   wiederverwenden. 8 + 5 Vollplanungen sind der klar messbare Ansatzpunkt.
   Neue Fakten, Profilwechsel und Zeit-/Frischegrenzen müssen Cacheeinträge
   zuverlässig invalidieren; Ranking und Evidenzregeln unverändert lassen.
2. Merge-/Projektionsarbeit gezielt profilieren und die belastenden Abschnitte
   verkleinern oder vom UI-Thread entkoppeln. Für RAM anschließend bedarfsgeladenen
   Ringzugriff prüfen, ohne Historien oder Offline-Abdeckung zu löschen.
3. Danach Abruf, budgetierte Nachprüfung und finale Planung koordinieren;
   vorherige Liste währenddessen stehen lassen und eine neue Ergebnisrevision
   einmal veröffentlichen. Abbrechen, Fortschritt und Fehlerzustände erhalten.

Nachteil einer ausschließlich finalen neuen Anzeige: Mit dem heutigen Ablauf
käme die neue Erstliste erst nach rund 58 s statt 3 s, die Folgeliste nach
rund 26 s statt sofortiger Zwischenergebnisse. Zuerst die wiederholte Arbeit
reduzieren. „Komplett“ muss auch abgeschlossene Unbekannt-/Budgetzustände
enthalten; sämtliche 100 Routen einzeln vollständig abzufragen wäre eine
separate Kosten-/Funktionsentscheidung, nicht bloß eine Anzeigeänderung.

Die alte 1.5.40-Baseline ohne funktionierenden QML-Nachprüfungsaufruf ist kein
gleichwertiger Endzeitvergleich. Katalogbestand, Live-Märkte und Rechner-/
Serverlast haben sich zudem verändert. Einzelmessungen sind keine garantierte
Beschleunigung und isolierte Offscreen-Werte kein Vollprofil-Praxistest.

## Artefakte und Umfang

Messwerkzeug: `tools/benchmark_mining_baseline.py`. Rohdaten und öffentliche
Quellinventare bleiben lokal in `.test-tmp/mining-post-reuse-100-20261008-b/`
und `.test-tmp/mining-post-reuse-100-20261008-c/` erhalten, jeweils `result.json`
und `source-inventory.json`. Der finale Bericht verwendet Lauf `c`.

Die selbst erzeugten Profil-/Journalkopien beider Prozesse und eine gescheiterte
Vorbereitung wurden nach Prozessende entfernt, zusammen rund **4,52 GiB**.
Sie sind aus den öffentlichen Quellkatalogen erneut erzeugbar; Messdaten bleiben.
Keine vorhandenen ED-Frame-AppData-Dateien gelöscht, komprimiert oder migriert.

Dieser Schritt hat nur das Diagnosewerkzeug erweitert und diesen Bericht
erstellt. Die beiden vollständigen Messprozesse endeten erfolgreich.
Die zuvor dokumentierten 1.146 App-Tests wurden nicht erneut ausgeführt;
in diesem Schritt gab es keine zusätzliche Produktionscodeänderung.
Kein Commit, Push, Release, Serverdeploy, Neustart der installierten App oder
Herunterfahren des Rechners.
