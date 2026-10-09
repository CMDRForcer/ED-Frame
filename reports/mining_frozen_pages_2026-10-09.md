# Stabile Mining-Ringseiten – Umsetzung und Prüfung

## Ergebnis

Der vorbereitete Serverpfad friert die Ringauswahl einer Suche einmal ein.
Neue Collector-Meldungen können laufende Seiten weder vermischen noch einen
Suchneustart auslösen. Die nächste Suche prüft die aktuellen Regionszähler
und sieht neue Daten sofort, unabhängig von der Seiten-Lebensdauer.

**Quellcode umgesetzt und getestet, noch nicht produktiv installiert.**
Keine Migration, kein Dienstneustart, kein Commit/Push/Release in diesem Schritt.
Bestehende AppData-/Katalogdateien und BGS-Prognosen bleiben unangetastet.
Markt- und Powerplay-Abfragen wurden nicht umgebaut; dies ist keine Zusage,
dass die gesamte Mining-Suche bereits einen einzigen gemeinsamen Datenstand hat.

## Funde und Fixes

- Der bisher vorbereitete Start-/Endvergleich musste bei Änderungen zwischen
  Ringseiten mit 409 abbrechen. Häufige Collector-Updates machten Wiederholungen
  wahrscheinlich. Fortsetzungen lesen jetzt nur einen festen Ergebnisbestand.
- Eine einzige kurze PostgreSQL-Transaktion (Repeatable Read, Read Only) umfasst
  Auswahl, Reihenfolge, Ertragsaggregate, Ring-Zusatzdaten und Community-Referenzen.
  Ein benannter Cursor liest jeweils 5.000 Zeilen. Keine offene Transaktion über
  mehrere HTTP-Anfragen und kein kompletter 50.000-Objekte-Heap im API-Worker.
- Beide API-Prozesse teilen einen temporären SQLite-Seitenspeicher. Ein 128-Bit-
  Zufallstoken mit Offset ist an Abfrage, Revision und Projektionsversion gebunden.
  Seiten benötigen nach der ersten Antwort keinen PostgreSQL-Zugriff mehr.
- Veröffentlichung erst nach erfolgreichem Abschluss der Datenbanktransaktion.
  Unfertige Einträge sind unsichtbar; Abbruch oder eine abgestürzte Aufbauinstanz
  gibt ihren begrenzten Platz wieder frei. Prüfsummen sichern Daten, Chunkposition,
  Zeilenzahl, Abfragebindung und Abschneidekennzeichnung gegen beschädigte Einträge.
- Fortsetzungen dürfen die Seitengröße ändern, ohne die Suche zu verändern.
  Community-Referenzen erscheinen weiterhin nur auf der ersten Seite.
  Beobachtungszeiten bleiben Originalzeiten, `snapshotAt` ist nur Diagnostik.
- Höchstens 50.000 Ringzeilen plus ein Sentinel zur Erkennung weiterer Treffer.
  Bei Abschneidung bleiben `hasMore=true` und `snapshotComplete=false` erhalten;
  die bestehende App behandelt das weiterhin als begrenzte, nicht cachebare Auswahl.

## Grenzen und Rückfallweg

Ein Aufbau gleichzeitig, 20 Sekunden Aufbau-Budget, acht Einträge, drei Minuten
Seitenverfügbarkeit. Je Eintrag höchstens 8 MiB komprimiert/64 MiB roh inklusive
Referenz-Metadaten; je Chunk 8 MiB roh, Metadaten 2 MiB roh. SQLite maximal 96 MiB,
kein WAL; Datenbank plus ungünstigster Rollback-Journalfall ungefähr unter 192 MiB.
Im großen Prüflauf belegten die aufgebauten Seitendatenbanken etwa 10,6 MiB.
Unabgelaufene Suchen werden nicht verdrängt, um neue aufzunehmen.

Voll/belegt/zu groß/Timeout liefert 503; die App nutzt ihre frische Legacy-Suche.
Abgelaufene, beschädigte oder anders gebundene Fortsetzungen liefern 409;
partielle Zeilen werden verworfen, einmal frisch versucht, dann gegebenenfalls
der vorhandene begrenzte Rückfallweg verwendet. Ein Neustart des API-Containers
verwirft diesen temporären Speicher, niemals den dauerhaften Katalog.
Seiten-TTL ist **kein** Beleg für unveränderte oder aktuelle Galaxiedaten.

## Gemessener Vergleich

Isolierte Kopie von **1.051.595 öffentlichen Mining-Datensätzen**; kein produktiver
Schreibzugriff. Gleiche Filter, Zeilen, Referenzen und Reihenfolge je Vergleich.
Die folgenden Werte stammen aus dem letzten großen Prüflauf:

| Radius | Ringzeilen | Bisher: alle Seiten | Fest: alle Seiten | Erste Seite bisher → fest |
| --- | ---: | ---: | ---: | ---: |
| 50 LY | 281 | 0,39 s | 0,16 s | 0,39 → 0,16 s |
| 250 LY | 25.249 | 7,75 s | 5,82 s | 4,44 → 5,56 s |
| 500 LY | 50.000, begrenzt | 32,29 s | 14,78 s | 9,66 → 14,40 s |

Weitere Seiten des festen Bestands brauchten etwa 7–91 ms; die unveränderte
Bestätigung 36 ms, ohne Ringtransfer. Ein weiterer isolierter Durchlauf ergab
bei 250 LY 16,31 → 6,34 s und bei 500 LY 25,66 → 9,78 s. Diese Schwankung zeigt:
Cachezustand und Serverlast beeinflussen absolute Zeiten erheblich.

**Nachteil:** Die erste Antwort kann später kommen, weil der feste Bestand zuerst
aufgebaut wird. Die gesamte Seitenabfrage war in diesen Versuchen kürzer und
benötigt bei Collector-Änderungen keine Wiederholung. Dies sind in-process-
API/SQL-Versuche, keine Windows-GUI- oder Internet-End-to-End-Messungen.
Die zuletzt ergänzten Integritätsprüfungen wurden anschließend nochmals mit
kleinen echten PostgreSQL-Fixtures geprüft; obige Lastzeiten stammen aus dem
großen Lauf unmittelbar vor dieser zusätzlichen Cache-Härtung.

## Verifikation

- **1.237 App-Tests** grün (138,7 s), darunter opaque Cursor, Originalzeiten und
  begrenzte Fortsetzungen ohne falsche Komplett-Kennzeichnung.
- **136 Server-Tests** grün, darunter getrennte Prozesse, Kapazität ohne Verdrängung,
  Aufbau-Abbruch, abgelaufene/teilfertige Daten, beschädigte Inhalte und Header.
- **33 echte PostgreSQL-Markerprüfungen** grün: Trigger, MVCC, Rollback, Deletes,
  Verschiebung, Generation, Zeitablauf und gleichzeitige Commits.
- Live-Schreibvorgang zwischen Seiten: laufende Ringzeilen identisch; nächste
  Suche erkennt Einfügen und Löschen sofort.
- Commit während Materialisierung: alte Ertragswerte und alte Ring-Zusatzdaten
  bleiben konsistent; nächste Suche bekommt neue Werte, ohne Quellen neu zu datieren.
  Die Prospector-Gesamtzahl einschließlich Nulltreffern bleibt erhalten.
- Community-Pfad: Zeilen/Reihenfolge/Referenzen identisch, fünf zusätzliche
  Referenzkandidaten im regionalen Test. Fortsetzung über zweite Speicherinstanz
  mit kleinerer Seitengröße ohne PostgreSQL funktioniert. Überfüllung liefert 503.
- Syntaxprüfung und `git diff --check` erfolgreich.

Protokolle: `.test-tmp/mining-frozen-20261009-01/` mit `app-tests.log`,
`server-tests.log`, `postgres-final.jsonl`, `postgres-integrity.jsonl` und
`production-unchanged.jsonl`. Ein früher Harness-Lauf scheiterte, weil er den
nur für die erste Anfrage zulässigen `known_revision`-Hinweis auf Fortsetzungen
mitschickte. Das Testwerkzeug wurde korrigiert; die App entfernt ihn bereits.

Alle generierten Testschemata und Server-Testdateien entfernt. Installierte
API-Prüfsumme unverändert:
`456a691bbfef64654989cb363ab02921fe143dcd697f5f2ac6ac2b76db7b4ee0`.
Produktiv keine Markertabelle und kein Snapshot-Parameter aktiv.

## Nächster Schritt

Separat freizugebender Rollout von passender App/API samt geprüfter Marker-
Migration, Sicherung und standardmäßig zunächst ausgeschaltetem Protokoll.
Erst dann gezielt aktivieren und echte erste Antwort, Gesamtdauer und Collector-
Durchsatz unter Normalbetrieb messen. Die Unterschiede bei erster Antwort und
begrenztem Rückfallweg sind transparent, keine Zusage eines nachteillosen Deployments.

Technische Grundlagen: [PostgreSQL Repeatable Read](https://www.postgresql.org/docs/17/transaction-iso.html),
[Psycopg serverseitige Cursor](https://www.psycopg.org/psycopg3/docs/advanced/cursors.html),
[SQLite Speichergrenzen und Auto-Vacuum](https://www.sqlite.org/pragma.html).
