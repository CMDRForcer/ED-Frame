# Serverkatalog und Speicherbereinigung — 21.10.2026

Der Serverkatalog enthält jetzt die vollständigen Referenzdaten zur Anaconda
Mk II sowie die ergänzten Moduldefinitionen: **49 Schiffe und 980 Module**.
Die Systemplatte hat nach Abschluss **14,63 GB statt 4,44 GB frei**. Rund
**10,20 GB zusätzlicher freier Platz** wurden gewonnen, ohne gespeicherte
Markt-, Mining-, Stations- oder Beobachtungsdaten zu löschen.

## Katalogabgleich ohne Dienstunterbrechung

- Sechs Referenzdateien wurden vorab semantisch gegen ihren bisherigen
  Serverstand geprüft. Unabhängige Serveränderungen lagen darin nicht vor.
- Das Image `edframe-catalog:0.9.5-reference-20261021` baut auf dem tatsächlich
  laufenden 0.9.5-Image auf und ergänzt ausschließlich diese Referenzdateien.
  Der laufende Servercode wurde nicht durch den abweichenden lokalen
  App-Checkout ersetzt. API- und Datenbankcode-Hashes des Images wurden geprüft.
- Der Abgleich lief zunächst in einem eigenen, anschließend vollständig
  zurückgerollten PostgreSQL-Testschema. Auch künstlich gesetzte vorhandene
  Preise blieben darin erhalten. Diese Testpreise gelangten nicht in den
  produktiven Katalog.
- Der produktive Abgleich aktualisierte ausschließlich Identitäts- und
  Referenzdaten. Alle vier Preisfelder sämtlicher **49 bestehenden
  Schiffskatalogzeilen** wurden vor/nach dem Abgleich verglichen und erhalten.
  Für die Anaconda Mk II wurde kein unbekannter Kreditpreis erfunden.
- Quelldateien auf dem Host und Referenzdateien in beiden laufenden
  App-Containern sind aktualisiert. Das neue Image ist für künftige
  Container-Neuerstellungen in Compose hinterlegt. Alle übrigen aufgelösten
  Compose-Einstellungen blieben identisch, einschließlich der bestehenden
  Schema- und Mining-Protokollfreigaben.
- API, Collector, PostgreSQL und Caddy behielten ihre Container-IDs,
  Startzeiten und laufenden Prozesse: **kein Produktionsdienst wurde neu
  gestartet**. Die Server-API-Version bleibt 0.9.5, da ihr Code unverändert ist.

Öffentliche Abfragen bestätigen Schiffsnamen, Hersteller und das neue
Klasse-6-Mk-II-Cargo-Rack. Der Statistikcache zeigt ebenfalls 49/980. Der
Website-CORS-Abruf funktioniert und der Collector-Eingangszeitstempel läuft
weiter. Alle geprüften Indizes sind gültig; keine Testschemas blieben zurück.

## Frische und geprüfte Sicherung

Vor dem Indexneuaufbau wurde eine zusätzliche Datenbanksicherung erstellt:

`/var/backups/edframe-catalog/catalog-manual-20261021T201335Z.dump`

- Größe: **789.205.262 Bytes**.
- SHA-256: `1c001deff05d6a3785e21865e475ac522add66b617024873b6ddefcbe392b453`.
- Das vollständige Archiv wurde mit `pg_restore --exit-on-error
  --file=/dev/null` gelesen und entpackt. Es wurde dabei nichts in die
  Datenbank zurückgespielt; ein vollständiger Wiederherstellungstest in einer
  zweiten Datenbank wurde nicht ausgeführt.
- Sämtliche vorher vorhandenen Sicherungsdateien blieben erhalten. Der
  tägliche Backup-Timer ist weiterhin aktiv.

Katalogdateien, vorherige Referenzzeilen, Compose-Konfiguration und
Rückfall-Image-Verweise liegen zusätzlich unter:

`/opt/edframe-deploy-backups/catalog-reference-20261021`

Ein bloßer Katalog-Rollback erfordert keine Wiederherstellung der gesamten
Datenbank. Eine solche würde spätere Beobachtungen zurücksetzen und wurde
deshalb nicht als Bereinigung oder Deployment-Schritt verwendet.

## Sicherungen verlagert, nicht verworfen

**180 Deployment-Sicherungsdateien mit 2.549.849.671 Bytes** wurden auf die
vorhandene 50-GiB-Zusatzplatte kopiert. Jede Datei wurde mehrfach per SHA-256
mit dem Original verglichen. Erst nach vollständiger Prüfung wurden die
Duplikate auf der Systemplatte entfernt.

Neuer Speicherort:

`/var/backups/edframe-catalog/deployment-archives`

Der ursprüngliche Pfad `/opt/edframe-deploy-backups` bleibt als symbolischer
Link nutzbar. Der Zielmount wurde anhand seiner bisherigen UUID geprüft.
Die Datenbank bleibt auf dem schnellen bisherigen Datenträger. Alle vorher
vorhandenen Docker-Images und Rückfallversionen wurden erhalten.

## Zwei dünn gefüllte Indizes im laufenden Betrieb verdichtet

Die Füllung wurde mit `pgstatindex` gemessen. Die dafür vorübergehend
angelegte Diagnose-Erweiterung samt Schema wurde wieder zurückgerollt.

| Index | Vorher | Nach Neuaufbau | Freigegeben |
|---|---:|---:|---:|
| `station_module_offers_price_idx` | 1.885.020.160 B | 148.856.832 B | 1.736.163.328 B |
| `markets_search_idx` | 7.038.763.008 B | 711.098.368 B | 6.327.664.640 B |

Zusammen: **8.063.827.968 Bytes Indexplatz**. Die ursprüngliche
Blattfüllung lag bei rund 9 %. Es wurden ausschließlich diese beiden
nachweislich stark aufgeblähten Indizes mit `REINDEX INDEX CONCURRENTLY`
erneuert. Definition, Tabellenzuordnung und Eindeutigkeitsmerkmale wurden
vorher/nachher verglichen; beide Indizes sind bereit und gültig. Es wurden
keine Tabellenzeilen gelöscht oder umgeschrieben und kein `VACUUM FULL`
ausgeführt.

Der Neuaufbau lief einzeln, ohne parallele Wartungsworker und mit 64 MiB
Wartungsspeicher. Ein Wächter hätte bei weniger als 2 GiB freiem Platz die
eigene Wartungsabfrage abgebrochen. Tatsächlich blieben selbst am niedrigsten
Messpunkt über 6,4 GB frei. Beide Neuaufbauten waren zusammen nach etwa
57 Sekunden fertig; HTTPS-Healthchecks waren erfolgreich.

Grundlagen: [PostgreSQL 17: pgstattuple](https://www.postgresql.org/docs/17/pgstattuple.html),
[REINDEX CONCURRENTLY](https://www.postgresql.org/docs/17/sql-reindex.html).

## Abschlussprüfung und Grenzen

- **221 lokale Servertests bestanden**, einschließlich des auf 49 Schiffe
  erweiterten Referenzkatalogtests.
- Öffentliche Schiff-/Modulsuche, Healthcheck, Statistik und Website-CORS
  geprüft; Collector-Eingang fortlaufend.
- Kein ungültiger öffentlicher Index und keine temporären Testschemas.
- Auf der Backup-Platte verbleiben etwa **40,68 GB frei**.
- Repository-Hygiene und Whitespace-Prüfung bestanden. Kein Git-Commit,
  Push, App-Paket oder Release wurde für diese Arbeiten erstellt.
- Die Zahlen sind eine Momentaufnahme bei weiterlaufender EDDN-Aufnahme.
  Die Bereinigung ersetzt keine langfristige Kapazitätsplanung; vorhandene
  Storage-Monitore und Wartungs-/Backup-Timer wurden nicht umkonfiguriert.
