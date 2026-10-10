# Mining-Abgleich und Server-Rollout für ED-Frame 1.0.8

Die elf zuvor fehlenden vergleichbaren ALL-Systeme werden bei 250 und 500 LY
gefunden. Server 0.9.3 ist am 10.10.2026 ausgerollt; die App-Quelle trägt 1.0.8.
Dieser Bericht ersetzt die offenen Rollout-/Messpunkte der vier historischen
Entwicklungsberichte vom selben Tag.

## Ursache und Änderung

Die regionale Preistopliste enthielt nicht alle geeigneten Märkte. Ungefilterte
Powerplay-Seiten verbrauchten ihr Budget mit anderen Mächten; Rishatkwali fehlte
dadurch trotz expliziter Aisling-Kontrolle. Die letzten Lücken, Kamocan und Orang
bei 500 LY, hatten keine passenden Ringe im begrenzten regionalen Snapshot.

- Powerplay-Seiten werden vor der Pagination nach Macht und Ziel gefiltert.
  Regionaler Cache und Anfrageumfang berücksichtigen beide Filter.
- Die neue öffentliche `POST /v1/mining/merit-markets`-Abfrage ergänzt genaue
  Systeme/Rohstoffe. Sie liefert je Kombination den besten passenden aktuellen
  Verkaufspreis sowie ursprüngliche Powerplay-Beobachtungen und genaue Ringe.
- Passende regional bekannte Powerplay-Systeme mit belegten Koordinaten können
  Ring-Ergänzungen erhalten, auch wenn die regionale Ringliste sie ausgelassen hat.
- Bis 48 Stunden alte explizite Powerplay-Daten sind aktuell; bis 14 Tage alte
  Daten bleiben datierte, unverifizierte Vorschläge. Anwesenheit ersetzt keine
  Kontrolle. Downloadzeiten erneuern keine Beobachtung.
- Hintergrundarbeit teilt sich begrenzte CPU-/I/O-Ressourcen. Leere automatische
  Marktantworten invalidieren keinen unveränderten Plan. Zurückgestellte Pläne
  starten nach dem Ende ihrer Eingaben auch ohne bestehende Mining-QML-Seite.
  Ein alter Cache-Schlüssel allein hält die Oberfläche nicht mehr beschäftigt.

Die Arbeitsschritte umfassen auch die vorher lokal vorbereitete Lastverteilung,
gebündelte Aktualisierungen, zusätzliche Serverstatistik und entfernte dauerhaft
leere Signal-Karte. Keine neue PostgreSQL-Tabelle oder Datenlöschung ist nötig.

## Ergebnisvergleich

HIP 3254, Aisling Duval, REINFORCE, LASER, alle Reserven/Ringe, L-Pad,
Nachfrage mindestens 5.000 t, maximal 48 Stunden Marktalter, kein Nachfrage-Maximum.
Vergleich mit der öffentlichen [MeritMiner-Suche](https://meritminer.cc/).

| Suche | Radius | Gefundene vergleichbare Systeme | Live-Abruf | Rechenschritt |
|---|---|---|---|---|
| Platinum | 250 LY | 2/2 | 22,10 s | 0,46 s |
| Platinum | 500 LY | 2/2 | 23,69 s | 2,39 s |
| ALL COMMODITIES | 250 LY | 25/25 | 23,51 s | 17,95 s |
| ALL COMMODITIES | 500 LY | 25/25 | 23,38 s | 26,22 s |

Platinum lief vollständig über die öffentliche HTTPS-Pipeline. ALL verwendete
die eingefrorenen ursprünglichen, ausdrücklich partiellen Regionalringe und
den gefüllten öffentlichen Marktbestand als lokale Eingaben; Powerplay,
regionale Märkte, genaue Märkte und zusätzliche Ringe kamen über echtes HTTPS
vom ausgerollten Server. Die Berechnung lief anschließend über die tatsächliche
Controller-/SQLite-/Planner-Pipeline in eigenen Testdatenbanken. Jeder Lauf
verwendet eine gespeicherte Vergleichszeit und originale Beobachtungszeiten.
Netzwerk- und Rechenzeiten sind getrennte Einzelmessungen auf diesem PC und
entstanden teilweise während anderer Release-Tests.

MeritMiner lieferte bei ALL 30 Systeme. Fünf betrafen Rohstoffe, die ED-Frames
Katalog nicht der ausgewählten Laser-Asteroiden-Methode zuordnet; der Abgleich
bezieht sich auf die verbleibenden 25. Er bestätigt gleiche Systeme, keine
identische Rohstoffauswahl, vollständige Galaxieabdeckung oder Merit-Auszahlung.
ED-Frame lieferte in beiden ALL-Läufen 100 unterschiedliche verifizierte Systeme
in seinen 100 Ergebnissen. Zusätzliche Systeme allein beweisen keine Überlegenheit.

Der tatsächliche ALL-250-Lauf ergänzte 2.607 Marktzeilen in acht Batches; 14
Systeme blieben zurückgestellt. ALL-500 ergänzte 2.761 Zeilen; 84 Systeme blieben
zurückgestellt. Keine Batchanfrage scheiterte. Die Grenzen bleiben sichtbar:
höchstens acht Batches mit 200 Systemen, 20 Sekunden Dispatch-Budget und
2/12 Sekunden Verbindungs-/Lese-Timeout. Die letzte Anfrage und ihre Verarbeitung
können das Dispatch-Budget überschreiten. Pro Batch sind höchstens 5.000 Ringe
enthalten; abgeschnittene Ringabfragen bleiben partiell. Ein alter Server erhält
weiterhin die begrenzte 64-Paar-Fallback-Abfrage.

## Oberfläche mit gefülltem Bestand

Der native Qt-Test nutzte 185.818 Ringe, 30.193 Marktzeilen und 3.743 öffentliche
Powerplay-Beobachtungen mit einem synthetischen Journal. Er prüfte ALL bei 500 LY,
eine Wiederholung und einen begrenzten Seitenwechselzyklus. Er beendete sich
nach 54,83 Sekunden ohne Fehler und mit 100 verifizierten Ergebnissen.

| Phase | Größter Abstand des 10-ms-UI-Timers | Abstände über 100 ms |
|---|---|---|
| Erste Suche | 47,20 ms | 0 |
| Wiederholte Suche | 49,29 ms | 0 |
| Seitenwechsel während Abgleich | 35,02 ms | 0 |

Das erste Ergebnis erschien nach 21,14 Sekunden, der Ablauf war nach 45,02
Sekunden einschließlich Prüfung fertig. Die Wiederholung zeigte ihr erstes
Ergebnis nach 0,011 Sekunden und endete nach 3,06 Sekunden. Seiten waren nach
32–100 ms bereit. Der App-Prozess blieb unter 200 MiB RSS; der separate große
Rechenprozess erreichte vorübergehend etwa 1,81 GiB RSS.

Der Test lief offscreen mit Software-Rendering und eingefrorenen Anbietern;
er misst die Qt-Ereignisschleife, keine reale Maus-/GPU-Latenz auf allen PCs.
Beim ersten Laden blieb ein Timerabstand von 3,15 Sekunden bestehen. Weitere
Startoptimierung und kalte große Ringdownloads sind offene Verbesserungen.
Adaptive Budgets begrenzen Last, garantieren aber keine gleiche Geschwindigkeit
auf jedem Prozessor oder bei wenig RAM.

## Server und Releaseprüfung

Der [öffentliche Server](https://vps-20b25c36.vps.ovh.net/healthz) wurde nach einem
geprüften PostgreSQL-Custom-Backup (374.155.528 Bytes) und gesichertem bisherigen
Image umgeschaltet. Das Backup wurde vollständig von `pg_restore` gelesen.
Alle 164 Server-Tests bestanden im neuen Linux-Image vor dem Dienstwechsel.
Bestehende Suchendpunkte, Powerplay-Lookup, neue Batchantworten und gefilterte
Powerplay-Seiten bestanden anschließend die Live-Prüfung. API und Collector
nutzen dasselbe neue Image. Der Collector empfing nach dem Wechsel weitere
Nachrichten; sein Fehlerzähler blieb bei null.

Die isolierte App-Quelle besteht 35 native Smoke-Prüfungen einschließlich
separater Mining-/Journal-/Powerplay-Prozesse. Alle 1.371 App-Tests bestanden
abschließend; Repository-Hygiene und `git diff --check` ebenfalls. Die Release-Pipeline für den
[Tag 1.0.8](https://github.com/CMDRForcer/ED-Frame/releases/tag/1.0.8) verlangt
zusätzlich vollständige App-Tests, Repository-Hygiene, Quell- und EXE-Smoke mit
Prozessprüfungen, Archiv-/Datenschutzprüfung und SHA-256-Prüfsummen. Eine laufende
alte EXE erhält Quelländerungen erst nach dem vollständigen Beenden und Start
der neu entpackten Version.
