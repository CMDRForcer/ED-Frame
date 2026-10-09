# Lokale Powerplay-Ergänzung durch Spansh

Stand: 2026-10-09. Änderungen sind lokal und uncommitted. Kein Git-Push,
kein neues Release und keine Aktualisierung des Produktivservers.
Die veröffentlichten Versionsnummern bleiben App 1.0.6 und Server 0.9.1.

## Verhalten

Bei fehlender Powerplay-Kontrolle fragt die App zuerst den vorhandenen
ED-Frame-Katalog ab. Eine separate neue Serverabfrage kann anschließend bis zu
sechs fehlende Systeme über öffentliche Spansh-System-Snapshots ergänzen.
Bereits vorhandene Ringe verhindern diese Abfrage nicht; aktuelle eindeutige
Kontrolldaten vermeiden unnötige Zusatzabfragen.

Übernommen werden nur passende Systemnamen und Adressen, gültige Koordinaten,
explizite Kontrolle beziehungsweise ausdrücklich gemeldetes `Unoccupied`,
gültiger Powerplay-Zustand und ursprünglicher System-Zeitstempel. Die
24-Stunden-Grenze bleibt bestehen. Fehlende Angaben sind unbekannt; Ring- und
Marktzeitstempel erneuern keine Powerplay-Fakten. Ohne Teilnehmerliste wird
keine Beteiligung der ausgewählten Power erfunden.

Der Server speichert ausschließlich die öffentliche Projektion in der
bestehenden Tabelle. Ältere oder gleich datierte Spansh-Snapshots verdrängen
keine vorhandenen EDDN-Fakten. Nach dem Schreiben wird der maßgebliche
gespeicherte Stand erneut gelesen. Während HTTP bleibt keine Datenbanktransaktion
offen. Unbekannte oder mehrdeutige Systemadressen starten keinen Quellenabruf.

Begrenzte Parallelität, Antwortgrößen, Zeitbudgets, Rate-Limits und Caches
begrenzen Quellenabfragen. Ausfälle erhalten eine kurze Wiederholungsfrist.
Zurückgestellte Systeme werden beim nächsten Check zuerst geprüft; die
Warteliste wird bei Profilwechsel oder Reset geleert. Die Zusatzabfrage folgt
dem bestehenden Schalter für die Community-Verbindung.

## Öffentlicher Quellencheck

Nur lesender Check mit dem lokalen neuen Lookup am 2026-10-09 um 20:02:56 MESZ.
Keine Produktionsdatenbank wurde dabei beschrieben.

| System | Ergebnis | Originaler Quellstand |
|---|---|---|
| HIP 100305 | `MISSING`: Spansh liefert keine verwertbaren Powerplay-Felder. | Kein Powerplay-Zeitstempel übernommen. |
| HIP 104026 | `FETCHED`: Aisling Duval, Stronghold, eine gültige öffentliche Kontrollzeile. | 2026-10-09 14:50:40 UTC / 16:50:40 MESZ |

Quellen: [HIP 100305](https://spansh.co.uk/api/dump/143048819908) und
[HIP 104026](https://spansh.co.uk/api/dump/2381299288443).
Der zweite Befund prüft die Zusatzquelle; bereits frische Serverkontrolle
würde im normalen App-Ablauf wiederverwendet. Hieraus wird keine Zunahme der
galaxieweiten Abdeckung abgeleitet. Marktpreise und Markt-Altersfilter wurden
in diesem Schritt nicht geändert.

## Prüfungen

- 1.299 App-Tests außerhalb des dynamischen QML-Smoke-Moduls: bestanden.
- Die fünf dynamischen QML-Tests sind in getrennten Läufen abgedeckt. Im ersten
  Gesamtlauf mit 1.302 Tests bestanden 1.300; zwei vorhandene asynchrone
  QML-Tests meldeten Ladezeitüberschreitungen bei Exploration beziehungsweise
  Engineers. Beide bestanden danach im getrennten Lauf mit dem isolierten
  Test-Journal. Anschließend hinzugefügte Wartelisten-/Profilprüfungen bestehen
  im finalen App-Testlauf; insgesamt umfasst die App-Suite nun 1.304 Tests.
- Zusätzlicher echter App-Start mit isoliertem Profil und Journal:
  QML-Smoke `PASS` für alle 33 Bereiche, einschließlich Powerplay und Mining.
- 158 Servertests: bestanden, einschließlich nativer ASGI-Anfrage an die neue
  Route, Quellenvalidierung, Cache-Ablauf, Einzelabrufschutz, Parallelitätsbudget,
  Antwortgrößen, Fehlerbehandlung und maßgeblichem Stand nach Schreibkonflikten.
- Repository-Hygiene und `git diff --check`: bestanden.

Dies war der Prüfstand vor der anschließenden Release-Vorbereitung. In der
[vollständigen Messreihe](mining_complete_benchmark_2026-10-09.md) wurden danach
24 echte PostgreSQL-Prüfassertionen in einem entfernten isolierten Testschema
bestanden; das Schema wurde entfernt und Produktivtabellen blieben unverändert.
Der lokale Windows-Kandidat 1.0.7 ist gebaut und besteht den asynchronen
Smoke-Test für alle 33 Bereiche. Der gemeinsame App-/Server-Rollout bleibt
ein späterer Schritt; die produktive API ist weiterhin 0.9.1.
