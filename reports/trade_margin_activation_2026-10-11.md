# Aktivierung der Rundtour-Spannenberechnung
11. Oktober 2026 · vom Benutzer ausdrücklich beauftragt

Die korrigierte Warenauswahl für **Spanne pro Tonne** ist auf dem ED-Frame-Server
aktiv. Das Antwortformat bleibt gleich; hierfür sind keine weiteren Änderungen
oder ein neuer Build der App erforderlich. Vorhandene Ergebnisse werden durch
eine neue Rundtour-Suche aktualisiert.

## Änderung und Absicherung

Genau eine Datei wurde ausgetauscht:
`ed_companion/navigation/trade_route_model.py`. Das neue Image basiert direkt auf
dem vorher laufenden API-Image. Die übrigen geprüften API- und Clientquellen
entsprechen dem bisherigen Serverstand.

Die Auswahl berücksichtigt die kombinierte Spanne von Hin- und Rückfracht sowie
das nach dem ersten Verkauf verfügbare Budget. Bestand, Nachfrage, Frachtlimit
und Einkaufskosten bleiben begrenzend.

Altes Modell, altes Image und Rückkehrkonfiguration sind gesichert unter
`/opt/edframe-deploy-backups/trade-margin-20261011-v2`. Nur der API-Container wurde
ersetzt. Container-IDs und Startzeiten von Datenbank, Collector und Caddy sind
unverändert. Das Mining-Snapshot-Protokoll bleibt 1.

Aktives Image: `edframe-catalog-api:0.9.4-trade-margin-20261011-v2`.
Modell-SHA256: `1cf89ef6b375d9488e4a9040113250a0d91cc0300d93ff5bb02f5bed20d2bba5`.

## Nachweise

- Im getrennten Image bestanden **182 Servertests und 11 Modelltests**,
  einschließlich 120 Vergleichen mit einer vollständigen Warenpaar-Suche.
- Drei echte Sol-Marktabfragen liefen in einem getrennten Container mit
  PostgreSQL-Read-only-Vorgabe, einem CPU-Kern und 500 MB RAM.
- Gesamtgewinn und Entfernung liefern für denselben jeweiligen Marktbestand
  exakt dieselben Ergebnisse wie das vorige Modell.
- Bei Spanne pro Tonne stieg der höchste Wert in der geprüften Auswahl von
  **47.390 auf 64.142 CR/t**. 14 der 27 in beiden Top-30-Listen enthaltenen
  Stationspaare verbesserten ihre Spanne. Dies ist eine Momentaufnahme,
  kein Versprechen für spätere Preise oder höheren Gesamtgewinn.
- Container- und öffentlicher Healthcheck bestanden. Der unveränderte echte
  App-Client validiert für alle drei Sortierungen jeweils **30 Rundtouren**
  einschließlich Mengen, Budgets, Gewinne und Entfernungen.
- Die öffentliche Cache-Wiederholung dauerte 0,017 Sekunden und behielt
  Zeitstempel und Ergebnisse. Ungültige Frachtkapazität 0 ergibt HTTP 422.

Die untersuchte Auswahl umfasst 320 Stationen, 80 Startstationen und
24.380 Marktzeilen. Sie bleibt als Teilauswahl gekennzeichnet. Kalte öffentliche
Abrufe benötigten 6,665–9,989 Sekunden; SQL- und Netzlaufzeit sind darin enthalten.

Ein Parameterfehler im ersten zusätzlichen Prüfskript stoppte den ersten
Versuch vor jeder Aktivierung. Nach Korrektur wurden alle isolierten Prüfungen
wiederholt und bestanden. Es gab keinen Produktions-Rollback.

Die App bleibt im lokalen Teststand. Kein Commit, Git-Push oder Release wurde
erstellt. Rohprotokolle, geprüfter Transfer und öffentliche Prüfergebnisse:
Aktivierungsartefakte: `outputs/trade-margin-rollout-20261011` (lokales Prüfartefakt).
