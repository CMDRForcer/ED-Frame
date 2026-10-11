# Datenzufluss, Aktualität und Dauerbetrieb
11. Oktober 2026 · lesende Prüfung um 19:54–19:56 Uhr MESZ

Der Server wird weiterhin automatisch mit EDDN-Meldungen versorgt und baut
seinen Bestand aus. Collector, API und Datenbank laufen; der Collector meldet
keine protokollierten Fehler. Dies belegt den Empfang und die Verarbeitung,
aber keine vollständige Abdeckung aller Spielsysteme oder aller Rohmeldungen.

## Bestand und Zuwachs

Die folgenden Bestandszahlen stammen aus dem Statistikstand vom
11.10.2026, 17:50:17 UTC. Der live gelesene Collector-Zähler wurde beim Abruf
separat aktualisiert; die Bestandsstatistik wird etwa alle fünf Minuten erneuert.

| Datenart | Gespeicherter Stand |
|---|---:|
| Warenzeilen je Station/Ware | 7.437.876 |
| Systeme | 303.936 |
| Stationen | 48.690 |
| Mining-Einträge, einschließlich Katalogkandidaten | 1.352.682 |
| Modulangebote | 10.679.389 |
| Schiffsangebote | 399.541 |

Seit dem dokumentierten Stand vom 10.10.2026, 14:19:42 UTC stieg der
Marktbestand von 6.499.291 um **938.585 Warenzeilen**. Das ist ein Zuwachs
unterschiedlicher Stations-/Warenkombinationen, keine Zahl neuer Preisversionen.
Zusätzlich werden bestehende Datensätze laufend aktualisiert.

Im erfassten 24-Stunden-Statistikfenster kamen 2.107.061 EDDN-Meldungen an;
66,1 % davon wurden in mindestens eine von uns verwendete Datenart projiziert.
Die übrigen Meldungen sind überwiegend derzeit nicht ausgewertete Schemas.
Die Stundenstatistik verwendet die aktuelle und 23 vorherige UTC-Stunden.
Protokollierte Fehler: 0. Rohmeldungen werden nicht als Archiv gespeichert.

## Zusammenführen und Haltbarkeit

Stationen und Waren werden über stabile Identitäten zusammengeführt. Ältere
Meldungen verdrängen keine neueren Warenbeobachtungen. Fehlende Stationsfelder
können vorhandene Informationen erhalten; fehlende neue Preise werden nicht
erfunden. Der Server hält normalerweise den letzten Stand je Identität, keine
vollständige historische Preisreihe.

EDDN liefert laufende Beobachtungen. Ein vorheriger Spansh-Import ergänzt
Ring-Geografie und Metadaten; dieser Bulk-Import wird nicht automatisch
periodisch wiederholt. Gezielte Powerplay-Lookups können Spansh-Fakten ergänzen
und speichern, wenn sie neuer sind als der vorhandene Stand.

Es gibt kein gemeinsames Ablaufdatum des gesamten Katalogs. Suchen begrenzen
das Beobachtungsalter; die Wartung löscht deshalb keine alten Markt-, Stations-,
System-, Ring- oder Powerplay-Fakten. Entfernt werden explizit abgelaufene
Signale sowie alte Betriebsmetriken. Angebotslisten können bei neuen
vollständigen Inventarbeobachtungen korrigiert werden.

1.999.377 Warenzeilen, **26,9 %**, wurden innerhalb von 24 Stunden beobachtet;
245.463 innerhalb einer Stunde. Der Rest bleibt gespeichert, ist aber nicht
automatisch für eine aktuelle Route geeignet. Am 11.10.2026, 17:55 UTC enthielt
Powerplay 31.668 Systemdatensätze, davon 17.135 mit Beobachtung innerhalb von
24 Stunden und 31.458 innerhalb von sieben Tagen. Diese Zahlen zählen
Datensätze, keine garantierten vollständigen Kontroll- oder Merit-Nachweise.
Die aktuelle App verwendet für aktuelle Powerplay-Bewertung ein 48-Stunden-Fenster.

## Konkrete Grenzen und Betriebsrisiken

- Daten ohne Spielerbeobachtung können fehlen oder altern. Der aktuelle
  Collector besitzt keinen automatischen Nachholmechanismus für Meldungen,
  die während eines Empfangsausfalls nicht ankamen.
- Die Mining-Abdeckung enthält nur bei 8,6 % der Einträge Hotspot-Evidenz.
  Gemessener Ertrag ist mit 135 Proben aus vier Orten noch dünn. Ringkandidaten
  sind keine bestätigten Hotspots oder Ertragsmessungen.
- Die Platte ist zu **70,9 %** belegt; frei sind **11,73 GB**. Die Datenbank
  einschließlich ihrer Indizes belegt 15,26 GB. Die zwei stark aktualisierten
  Suchindizes sind seit der gestrigen Bereinigung wieder von etwa
  0,344/0,669 GB auf 2,564/3,752 GB gewachsen. Alle sieben geprüften Indizes
  sind gültig. Der Anteil unnötiger Belegung wurde in dieser Prüfung nicht
  vermessen; Größe allein beweist keinen exakt bestimmbaren Bloat-Anteil.
- Tägliches Backup und wöchentliche Wartung sind aktiviert und liefen zuletzt
  erfolgreich. Letztes tägliches Backup: 11.10.2026, 04:01 UTC, 405,25 MB.
  Der geprüfte Backup-Job schreibt auf denselben VPS und hält Backups etwa
  14 Tage. Eine externe Backup-Kopie ist in diesem Job nicht eingerichtet.
  Die Katalogdaten selbst haben diese 14-Tage-Grenze nicht.

Eine verbleibende Laufzeit in Tagen lässt sich aus den kurzen Messungen nicht
zuverlässig ableiten: Tabellen, Indizes, WAL und Backups wachsen verschieden.
Der Server ist für fortlaufenden Betrieb eingerichtet; die beobachtete
Speicherentwicklung sollte zeitnah behandelt werden. Priorität haben
Index-/WAL-Wachstum, häufigere Betriebsalarme und eine externe Backup-Kopie.
Diese Prüfung hat keine Dienste, Daten, Wartungsregeln oder Zeitpläne verändert.

Die Prüfsummen des laufenden Collectors, der Datenbank-/Projektionslogik und
der beiden Wartungsskripte stimmen mit den gelesenen Repository-Quellen überein.
Rohmessungen und Zusammenfassung: `outputs/server-data-health-20261011` (lokales Prüfartefakt).
