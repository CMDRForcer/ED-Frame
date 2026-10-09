# ED-Frame 1.5.43 — Rollout und Praxistest

## Ergebnis

Die vier freigegebenen Schritte umfassen Commit/Push, gesicherte Servermigration
mit API-Deployment, passenden Windows-Build mit Praxistests und anschließend die
Veröffentlichung über den bestehenden Release-Workflow. Dieser Bericht hält den
geprüften Stand **vor dem Release-Tag** fest; die GitHub-Veröffentlichung folgt
erst nach den Prüfungen des getaggten Windows-Pakets.

API **0.9.0** ist produktiv gesund, die explizite Mining-Migration abgeschlossen
und `EDFRAME_MINING_SNAPSHOT_PROTOCOL=1` aktiv. Der Collector läuft wieder und
verarbeitet aktuelle EDDN-Meldungen. Bestehende App-Dateien, historische
Beobachtungen, BGS-Prognosen und die installierte Windows-App wurden nicht
gelöscht, komprimiert oder ersetzt.

Die früheren Berichte über die vier Performance-Pakete dokumentieren ihren
damaligen Quellcode-/Teststand. Deren Hinweise „noch nicht deployt“ gelten nicht
mehr für den hier dokumentierten, ausdrücklich freigegebenen Rollout.

## Sicherung und Migration

- Unveränderliches altes API-Image, öffentliche alte Quelldateien und private
  Konfiguration gesichert. Geheimnisse bleiben ausschließlich auf dem Server.
- Konsistenter PostgreSQL-Dump: **329.836.905 Byte**, vor der Migration mit
  `pg_restore --list` und vollständigem Lesen/dekomprimieren geprüft.
  Keine Wiederherstellung in den produktiven Katalog erforderlich.
- SHA-256 des Dumps:
  `e58be2ce1fdab511375949705a7835dfe7466ec46ec76ddefad3f8447b0ee4b6`.
- Sicherungsordner: `/opt/edframe-deploy-backups/mining-1.5.43-20261009`.
  Die bestehenden älteren Sicherungen wurden nicht entfernt.
- API und Collector während der transaktionalen Installation pausiert.
  Fünf additive Markertabellen samt Änderungs-Triggern installiert; danach
  exakte Zeilenzahlen aller zwölf geprüften Katalogtabellen unverändert.

Auszug der unveränderten Bestände am Migrationszeitpunkt: **1.053.378 Miningzeilen,
5.800.763 Marktzeilen, 303.447 Ring-Zusatzdatensätze, 51 Prospector-Proben und
127 Ertragsmaterial-Zuordnungen**. Neue Meldungen nach Wiederaufnahme dürfen
diese Zahlen selbstverständlich erhöhen.

Der Rückweg ist vorbereitet: altes API-Image, alte Quellen und Konfiguration
wieder aktivieren. Kein pauschales Zurückspielen des Dumps, das seitdem neu
eingegangene Beobachtungen verlieren würde. Die additiven Marker bleiben stehen;
bei einer tatsächlichen Datenbank-Wiederherstellung ist deren Generation zu rotieren.

## Produktive HTTP-/Clientprüfung

Öffentliche GET-Abfragen um Shanteneri; keine Spielerdaten und keine Uploads.
Die originale App-Projektion, Seitengrenzen und Quellenzeiten bleiben erhalten.

| Prüfung | Ergebnis | Dauer |
| --- | --- | ---: |
| 250 LY | 25.418 HTTP-Ringzeilen, sechs stabile Seiten, vollständig | 10,68 s |
| 250 LY erneut, Region inzwischen geändert | frischer Bestand statt fälschlicher Wiederverwendung | 8,99 s |
| 500 LY | 50.000 HTTP-Ringzeilen, zehn stabile Seiten, korrekt begrenzt | 14,76 s |
| Unveränderte exakte Systemabfrage | Revision bestätigt, lokaler Cache validiert, kein Ringtransfer | 54 ms |
| Gemeinsamer 250-LY-Refresh | Ringe, Powerplay und Märkte erfolgreich | 9,48 s |

Alle Ringseiten einer Suche hatten dieselbe Revision, ohne 409-Neustarts oder
Legacy-Rückfall. 250 LY ergaben nach bestehender Zusammenführung **24.457
Kandidaten**; 500 LY **48.307**. Unterschiedliche HTTP-/Kandidatensummen entstehen
durch die bestehende Zusammenführung von Beobachtungen, nicht durch stilles
Abschneiden. Die exakte unveränderte Testabfrage enthielt keine Ringtreffer;
ihre 54 ms sind ausdrücklich kein Leistungsversprechen für einen großen Bestand.

Im gemeinsamen Refresh: **32.806 Powerplay-Beobachtungen**, zwölf Seiten mit
vollständiger Abdeckung, und **1.094 Marktangebote** nach Zusammenführung.
ED-Frame und Ardent erfolgreich; EDData-Fallback nicht erforderlich.
Die Domänen dauerten etwa 9,17 s / 2,67 s / 0,91 s und wurden parallel geladen.

Wichtig: Der feste Snapshot schützt die **Ring-Seitenkette**, nicht einen
gleichzeitigen globalen Stand von Ring-, Markt- und Powerplaydaten. Frische
gezielte Verifikationen bleiben erhalten. „Powerplay data missing“ wird nicht
in erfundene Bestätigung umgewandelt.

## Windows-/Oberflächenprüfung

- **1.238 App-Tests** grün, abschließender Gesamtlauf 135,3 s.
- **136 Server-Tests** und die zuvor dokumentierten **33 echten
  PostgreSQL-Integritätsprüfungen** grün.
- Windows-Paket 1.5.43 gebaut; echte asynchrone QML-Smokeprüfung:
  **33 Bereiche PASS**, Prozessende erfolgreich nach rund 32 s.
- Ein zusätzlicher Regressionstest verhindert, dass isolierte Smoke-Builds
  die Windows-OAuth-Verknüpfung auf eine temporäre Test-EXE umstellen.
- Lokaler Build zunächst durch fremde ICU-DLLs aus dem Werkzeug-PATH gestört.
  Mit bereinigtem Build-PATH neu gebaut; beide Fremd-DLLs fehlen und das Paket
  besteht den Test. Der Release-Workflow prüft diese Fremd-DLLs ebenfalls.

Separater Quellcode-Praxistest mit Kopien der öffentlichen Kataloge:
**391.212 Ringe, 150.000 lokal gehaltene Marktzeilen und 91.575
Powerplay-Katalogeinträge**, synthetisches Journal, 100 Ergebnisse, 250 LY.
Offscreen-/Software-Rendering; kein Test gegen das persönliche Profil und keine
Messung von GPU- oder Maus-bis-Bild-Latenz.

**30 Tabwechsel**, auch während neuer Serverabfragen: Median **43 ms**,
größter gemessener Wechsel **410 ms**, keine QML-Laufzeitfehler.
Qt-Timerabstand während Sync: 95. Perzentil **14,5 ms**, Maximum **442 ms**.

Erste lokale Ergebnisanzeige nach **2,27 s**, letzte Änderung nach **31,93 s**;
warme Suche zeigt vorhandene Ergebnisse sofort weiter und ist nach **15,81 s**
zuletzt geändert. „Beruhigt“ wurde jeweils erst nach zusätzlich drei Sekunden
ohne Aktivität gemessen. Diese Zahlen schließen gezielte Prüfungen ein; sie
zeigen gerade nicht, dass bereits die erste Anzeige vollständig verifiziert ist.

## Verbleibende Grenzen, keine verdeckte Funktionskürzung

Die vollständige Materialisierung kann die **erste** Serverantwort verzögern.
Weitere Seiten sind billig und werden durch neue Collector-Meldungen nicht
vermischt. Eine inzwischen geänderte Region muss erneut gelesen werden; TTL
allein ist kein Aktualitätsbeleg. Die bisherige 50.000-Zeilen-Grenze bleibt.

Der große globale JSON-Bestand wird nun erst bei Bedarf im Hintergrund geladen.
Das spart Start-RAM auf anderen Seiten, beseitigt aber nicht seinen Speicherbedarf
nach dem ersten Mining-Aufruf. Der Live-Test lag nach vollständigem Laden bei
etwa **618 MiB**, am Ende mit aktiver Suche bei **1.064 MiB**, Spitze **1.176 MiB**.
Eine regionale, direkt abfragbare Ring-Speicherung ist deshalb weiterhin ein
sinnvoller nächster Architektur-Hebel. Keine heimliche Datenlöschung als „Optimierung“.

## Serverzustand nach Aktivierung

Stand 12:18 UTC: API und PostgreSQL gesund, Collector aktiv, laufender Empfang;
Collector-Fehlerzähler **0**, in den letzten fünf Minuten keine API-/Collector-
Fehlerzeilen. Die neue Generation ist bereit, unbekannte Änderungsrevision **0**.
Marker einschließlich Indizes etwa **40,2 MiB**, temporäre Seiten etwa **4,4 MiB**.
Freier Server-Festplattenplatz etwa **10,1 GiB** nach Sicherung und neuem Image.

Die temporäre Seitenablage und ihre Aufbauzeiten sind begrenzt. Bei Kapazitäts-
oder Versionsproblemen bleibt der vorhandene frische Rückfallweg verfügbar;
unabgelaufene Seitenketten werden nicht zugunsten neuer Suchen verdrängt.

Messprotokolle lokal unter `.test-tmp/release-1.5.43/`: `app-tests-final.log`,
`live-check.json`, `server-health.json`, `server-migration.log`,
`packaged-validation-clean/stdout.log` und `gui-live-complete/result.json`.
