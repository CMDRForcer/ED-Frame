# Reparatur der verzögerten Serverstatistik am 12.10.2026

Die Serverstatistik blieb zuletzt auf dem Stand 20:12 Uhr stehen, obwohl der
EDDN-Collector weiter Nachrichten empfing. Die Warenartenzählung über mehr als
8,2 Millionen Marktzeilen überschritt wiederholt ihr 60-Sekunden-Limit. Der
Cache behielt deshalb den letzten erfolgreichen Snapshot; die Webseite zeigte
korrekt einen Rückstand an.

## Änderung und Messung

Die Warenartenzählung sucht die jeweils nächste tatsächlich gespeicherte
Warenart über den bestehenden `markets_search_idx`. Keine neuen Tabellen,
Indizes, Löschungen oder Schätzwerte sind erforderlich. Sie behält die genaue
Semantik für leere Bestände, Duplikate, NULL-Werte und neue Warenkennungen.

| Prüfung | Ergebnis |
|---|---|
| Lokale und isolierte Server-Tests | 187 bestanden |
| SQL-Randfälle gegen PostgreSQL | 6 bestanden |
| Warenartenzählung am Produktionsbestand | 412 Waren; 0,033–0,066 s in den Verifikationstests |
| Ausführungsplan | Bestehender Index; kein Gesamtscan, keine temporären Schreibblöcke |
| Vollständige Statistik, isoliert und lesend | 27,491 s / 20,954 s |
| HTTPS-Abruf nach Aktivierung | 0,064 s; HTTP 200, frischer Snapshot |

Die Messwerte stammen von diesem VPS und den jeweiligen Cache-/Lastzuständen;
sie sind keine allgemeine Laufzeitgarantie. Der vollständige Statistikstand
behält seine ursprüngliche Transaktionszeit. Begrenzungen auf 60 Sekunden pro
Abfrage und 120 Sekunden pro Transaktion bleiben bestehen.

## Rollout und einmalige Sperrkollision

Beim ersten API-Wechsel wurde während der wiederholten Schema-Initialisierung
eine Sperrkollision mit einer Collector-Transaktion festgestellt. Die
Aktivierungsprüfung rollte den API-Wechsel automatisch zurück. Der Collector
lief weiter, meldete jedoch eine fehlgeschlagene Iteration. Es lässt sich nicht
zusichern, dass diese einzelne Nachricht später erneut eingetroffen ist; die
öffentlichen Fehlerzähler wurden nicht zurückgesetzt.

Für den anschließenden Code-only-Wechsel wird die bestätigte vorhandene
Datenbankstruktur über einen exakten Schema-Fingerprint und ihre Tabellen/
Indizes ausschließlich lesend geprüft. Abweichungen verhindern den Start.
Normale Installationen ohne diese explizite Betreiberoption initialisieren
das Schema weiterhin wie bisher. Fünf Tests prüfen beide Startwege, geänderte
Bundles, fehlende Beziehungen und Datenbankfehler.

Aktiv: `edframe-catalog-api:0.9.4-status-index-20261012-v2`.
Sicherung: `/opt/edframe-deploy-backups/status-index-20261012-v2`.
Beim erfolgreichen Wechsel blieb der Collector-Fehlerzähler bei 1; PostgreSQL,
Collector und Caddy behielten ihre Container-IDs und Startzeiten. Der aktivierte
Mining-Snapshot-Modus blieb eingeschaltet. Es wurde nur der API-Container
ersetzt und der ersetzbare Statistikcache erneuert.

## Webseite und Projektstand

Die Webseite erlaubt der regulären Hintergrundberechnung bis zu 120 Sekunden
plus 30 Sekunden Prüfintervall zusätzlich zum Fünf-Minuten-Zyklus, bevor das
serverseitige Fälligkeitsflag als Verzögerung angezeigt wird. Originalzeiten
bleiben sichtbar; tatsächliche Rückstände und Ausfälle bleiben gekennzeichnet.
Die Browserprüfung bestätigte normalen Betrieb bei 330 Sekunden Alter und die
Warnung bei 480 Sekunden Alter. Diese Korrektur wurde als `dec903b` auf der
GitHub-Pages-Seite veröffentlicht.

Die Serverquellen, Tests und dieser Bericht bleiben im App-Repository lokal.
Die App bleibt bei Version 1.0.9; ein App-Update ist nicht erforderlich.
Rohprotokolle und Hilfsskripte liegen im bisherigen Chat-Arbeitsordner unter
`outputs/status-query-fix-20261012`.

## Tatsächliche automatische Aktualisierung nach Aktivierung

Ohne manuellen Neuberechnungsaufruf wechselte `generatedAt` von
`2026-10-12T18:50:23.325543Z` auf `2026-10-12T18:55:24.296452Z`.
Der neue Snapshot wurde beim Kontrollabruf um 20:56 Uhr mit 35 Sekunden Alter
und `cache.stale=false` ausgeliefert. Die Marktzeilenzahl stieg von 8.252.881
auf 8.259.555. Während der Beobachtung kamen 3.972 EDDN-Nachrichten hinzu;
der Collector-Fehlerzähler blieb bei 1. Die öffentlichen Kontrollabrufe
blieben während der Neuberechnung erfolgreich und schnell.

Die veröffentlichte Webseite zeigt den automatisch erneuerten Stand und
`Receiving data`, ohne Verzögerungswarnung. Die 390-Pixel-Ansicht hat keinen
horizontalen Seitenüberlauf. Der GitHub-Pages-Lauf `38293715986` war erfolgreich.
Belegbild: `outputs/status-query-fix-20261012/statistics-fixed-live.jpg`.
