# Speicherreserve und sparsamere Ausstattungsverarbeitung – 12.10.2026

Die beauftragte Indexpflege und Collector-Optimierung sind auf dem Server aktiv.
Die App 1.0.9 verwendet die unveränderten öffentlichen Endpunkte; kein App-
Update, Commit, Push oder Release. Alle Angaben zum Platz verwenden dezimale GB.

## Speicherreserve

Zwei temporäre Stichproben bestätigten deutlich größere Suchindizes als für
den aktuellen Bestand nötig. Ein vollständiges aktuelles Datenbank-Backup wurde
mit pg_restore gelesen und per SHA-256 dokumentiert. Beide Suchindizes wurden
einzeln mit REINDEX INDEX CONCURRENTLY neu aufgebaut, mit unveränderten
Definitionen, 128 MB Wartungsspeicher, ohne parallele Wartungsworker und mit
Platzwächter bei vier GB Mindestreserve.

| Index | Vorher | Danach | Frei geworden | Dauer |
| --- | ---: | ---: | ---: | ---: |
| markets_search_idx | 1,193 GB | 0,440 GB | 0,753 GB | 32,7 s |
| station_module_offers_search_idx | 2,655 GB | 0,832 GB | 1,823 GB | 48,5 s |

Zusammen wurden 2,575 GB Indexplatz zurückgewonnen. Frei waren direkt danach
15,442 GB, bei der abschließenden Prüfung 15,392 GB; etwa 62 % belegt.
Katalogdaten und inventarisierte Backups behielten ihren Bestand.
Indexdefinitionen und Dienstidentitäten blieben während des Neuaufbaus gleich.

## Ursache und Änderung

Ausstattungslisten bestätigten bei jedem neueren Zeitstempel sämtliche
normalisierten Module erneut. Das erzeugte unnötige Zeilenversionen und neue
Einträge im großen Suchindex, auch bei unveränderten Angeboten.

Die aktuelle Verfügbarkeit wird jetzt einmal im vollständigen Stations-
Inventar gespeichert. Die API nutzt diesen gemeinsamen Zeitstempel zusammen
mit der bisherigen Modulzeile. Nur tatsächliche Änderungen an Modul-ID oder
Preisbelegen aktualisieren bestehende normalisierte Modulzeilen. Ein neuer
Preisbeobachtungszeitpunkt bleibt eine Änderung, auch bei gleichem Preis.

Preis, alternative Merc-Coin-Preise, Preiszeitpunkt und Quelle behalten ihre
Merge-Regeln. Fehlende Werte und ältere Preisbelege überschreiben keine
bekannten neueren Fakten. Entfernte bzw. neu verfügbare Module werden weiterhin
verarbeitet. Vollständige Stationslisten und ihre Empfangs-/Sync-Zeitstempel
werden weiterhin aktualisiert. Schiffe, Teilkäufe und Marktzeilen behalten ihr
bisheriges Schreibverhalten.

Die Zusammenführung älterer Preisobjekte mit einer EDDN-Verfügbarkeitsliste
nutzt zusätzlich eine einmal aufgebaute JSON-Zuordnung statt einer erneuten
Suche durch die gesamte Liste pro Modul. Bei doppelten Namen bleibt wie zuvor
das erste passende Objekt erhalten.

## Prüfungen

- 208 Servertests lokal und im isolierten Linux-Kandidaten bestanden.
- 70 bestehende App-Tests bestanden.
- Zwei zusätzliche Tests für Speicherschwellen und ausschließlich eigene
  Bericht-Aufbewahrung bestanden.
- Separate PostgreSQL-17-Testdatenbank mit alter und neuer Implementierung:
  17 Abläufe, vollständige logische Daten und Eltern-Snapshots verglichen;
  34 Vergleiche von Such- und Synchronisationsantworten.
- Fälle: neue Beobachtung bei gleichem Inventar, Preis-/ID-Korrekturen,
  ältere Meldungen, gleiche Zeitstempel, fehlende IDs, neue Preisbeobachtung
  bei unverändertem Preis, Preisbeleg-Erhalt bei EDDN v2, Inventarentfernung,
  Wiederauftauchen, leere Listen, doppelte Preisobjekte und Teilkäufe.
- Eine neue Verfügbarkeitsbestätigung von 1.200 vorhandenen Angeboten erzeugte
  null Modul-Updates statt 1.200. In diesem synthetischen Einzellauf dauerte
  die Verarbeitung rund 375 ms statt 1.019 ms. Kleine Listen waren teils etwas
  langsamer; es wird keine generelle Beschleunigung jedes Schreibvorgangs
  behauptet.
- Sechs lesende Suchvergleiche am echten Bestand: vollständige Felder und
  ausgewählte Stationen identisch, gleiche Reihenfolge nach Aktualität.
  Gleich alte Angebote haben bereits im alten Endpoint keinen Tie-Breaker;
  ihre Reihenfolge innerhalb eines Gleichstands kann sich unterscheiden.
- Der unveränderte App-Client lud 200 Modulangebote und eine Marktseite mit
  1.000 Zeilen erfolgreich. Synthetische Datenbank und Testnetz entfernt.

## Aktivierung und Rückfall

Aktives API-/Collector-Image:
edframe-catalog:0.9.4-outfitting-sparse-20261012.

Zuerst wurde die API mit kompatibler Aktualitätsberechnung aktiviert; danach
der opt-in Collector. Dessen Start prüft die interne API-Fähigkeit, bevor
sparsame Schreibvorgänge erlaubt sind. Die API verarbeitet eigene Uploads
weiter im bisherigen Schreibmodus; der EDDN-Collector nutzt den neuen Modus.

Collector-Wechsel bis zur verifizierten Wiederaufnahme: etwa 5,7 Sekunden,
einschließlich geordnetem Stop und Prüfungen. Der externe Live-Feed wurde dabei
kurz unterbrochen; vollständige Wiederzustellung lässt sich nicht garantieren.
Gespeicherte Katalogdaten wurden nicht verworfen. PostgreSQL und Caddy behielten
Container, Image, Volumen und Startzeiten. Fehlerzähler blieb bei 1.

Sicherung:
`/opt/edframe-deploy-backups/outfitting-write-20261012`.
Ein Collector-Rollback deaktiviert den Schreibmodus und behält die kompatible
API. Nach sparsamen Schreibvorgängen darf der alte API-Reader nicht blind
zurückgespielt werden, weil rohe Modul-Zeitstempel dann nicht allein die letzte
Verfügbarkeitsbestätigung darstellen. Der vollständige Zeitstempel bleibt im
Stations-Inventar gespeichert.

Ein privates serverseitiges compose.override.yaml hält Images und Protokollflags
für gewöhnliche Compose-Neustarts fest; es enthält keine Zugangsdaten.

## Kontrolle und Grenzen

Alle zwei Stunden werden kurze, lesende Platz-/Tabellen-/Indexmessungen
gespeichert. Aufbewahrung der eigenen Messberichte: 31 Tage. Warnung ab 70 %,
kritischer Dienststatus ab 85 %. Diese Meldungen bleiben im Serverprotokoll;
keine externe Benachrichtigung eingerichtet. Der Monitor führt keine
Index-Neuaufbauten oder Kataloglöschungen aus. Bestehende Backup-, Log- und
Wartungsregeln bleiben erhalten.

Abschluss um 22:40 Uhr: Collector-Eingang etwa 0,08 Sekunden alt, seit der
Aktivierungsprüfung 7.781 weitere Nachrichten. 161 vorhandene Stationslisten
wurden aktualisiert, 13 hinzugefügt. Es gab 6.948 echte Modul-Updates und
7.481 Modul-Neuanlagen. Diese kurze Stichprobe ist kein belastbarer Nachweis
einer langfristigen täglichen Wachstumsrate.

Ein aktuelles Inventar bestätigte 389 Angebote um 20:40:26 UTC. Deren
gespeicherte Modul-Zeitstempel durften unverändert bleiben; die API lieferte
korrekt die aktuelle Verfügbarkeit. Preisbeobachtungszeiten blieben getrennt.
Serverstatistik automatisch erneuert, Cache-Alter 66 Sekunden.

Der Marktbestand und neue Systeme/Stationen wachsen weiterhin. Mehrtägige
Messungen müssen zeigen, welche dauerhafte Reserve nun entsteht. Es wurden
keine zusätzlichen Speicherprodukte gebucht oder Backups ausgelagert.

Rohmessungen und Helfer:
`outputs/storage-write-20261012` im Fortsetzungstask.
