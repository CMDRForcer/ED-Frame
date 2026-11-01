# Serverausfall und Wiederherstellung · 31.10.2026

Die API ist wieder erreichbar. Öffentliche Prüfungen liefern HTTP 200 für
`/healthz` und `/v1/status`; die Statistikfreigabe für die Projektwebsite
funktioniert ebenfalls. Der Collector empfängt wieder aktuelle EDDN-Nachrichten.
Die API wurde am 31.10. um etwa 15:31 Uhr MEZ wieder gesund.

## Ursache

Die 40-GB-Systemplatte hatte keinen für Dienste verfügbaren Platz mehr.
PostgreSQL und Collector konnten nicht mehr starten; die laufende API meldete
HTTP 500. Ein tatsächlicher Serverausfall war damit die Ursache der Offline-
Anzeige in App und Website. Die separate Backup-Platte war korrekt eingebunden
und hatte noch rund 39 GB frei.

Der wichtigste Platzverbraucher war `markets_search_idx`: 9.212 MB bei nur
9,31 % Blattfüllung. Zwei weitere sekundäre Indizes waren ebenfalls aufgebläht.
Die bisherige wöchentliche VACUUM-Wartung gab diese teilweise belegten
Indexdateien nicht als kleinere Dateien an das Betriebssystem zurück.

## Wiederherstellung ohne Löschen gespeicherter Katalogfakten

1. API und Collector sowie die betreffenden Wartungstimer vorübergehend gestoppt.
2. 272 MB wiederherstellbare Paketmetadaten auf der Backup-Platte archiviert,
   jede Datei per SHA-256 geprüft und erst danach deren Systemplattenkopie entfernt.
   Keine Nutzdaten, Backups, Journals oder Docker-Images wurden dafür gelöscht.
3. PostgreSQL mit diesem kleinen Startpuffer wieder gestartet; Crash-Recovery
   abgeschlossen. Eine neue vollständige Datenbanksicherung erstellt und das
   gesamte Archiv mit pg_restore gelesen, einschließlich SHA-256-Prüfung.
4. Exakte Datensatzzahlen und unveränderte Indexdefinitionen vor dem Eingriff
   gesichert. Da für eine zweite Indexkopie zunächst kein Platz bestand, nur den
   gesicherten, nicht eindeutigen und nicht constrainttragenden Marktsuchindex
   bei gestoppten Schreibern entfernt und mit exakt derselben Definition neu
   erstellt. Danach die zwei weiteren geprüften sekundären Indizes kompaktiert.
5. Alle Indexdefinitionen, Gültigkeit und Bereitschaft erneut geprüft und die
   exakten Tabellenzahlen verglichen. Statistikdaten für den Query-Planer nach
   dem Crash erneuert; API und Collector anschließend wieder gestartet.

Beim Vergleich waren unverändert vorhanden:

| Bestand | Zeilen vor und nach der Indexreparatur |
|---|---:|
| Warenmärkte | 17.003.620 |
| Modulangebote | 21.977.596 |
| Schiffsangebote | 798.761 |
| Mining-Einträge | 3.678.902 |
| Systeme | 891.937 |
| Stationen | 105.748 |

Alle 49 Schiffspreiszeilen blieben auch nach dem Start beider Dienste erhalten.
Der größte Index ist danach etwa 906 MB groß statt 9.212 MB; seine Blattfüllung
liegt wieder bei rund 90 %. Die Systemplatte hatte nach der Reparatur rund
10,8 GB frei; danach laufen die regulären Schreibvorgänge wieder.

Die zusätzliche Sicherung liegt im Incident-Verzeichnis der Backup-Platte.
Größe: 1.245.428.529 Bytes. SHA-256:
`3698024c19d23ac8266025b29505a19834c80306123106817e5a2ef8db06f2d4`.
Vorhandene Sicherungen und Images blieben erhalten. Die Datenbank blieb auf
der schnellen Systemplatte; sie wurde nicht auf die langsamere Backup-Platte
verschoben. Während des Ausfalls nicht empfangene EDDN-Nachrichten können
damit nicht nachträglich als empfangen behauptet werden. Neue Meldungen bauen
die Aktualität wieder auf.

## Vorbeugung und Prüfung

Eine zusätzliche, getestete Indexwartung prüft alle sechs Stunden die drei
freigegebenen sekundären Indizes. Sie baut höchstens einen deutlich aufgeblähten
Index pro Durchlauf online neu auf, nur mit frischer vollständig lesbarer
Sicherung, korrekter Backup-Mount-UUID und ausreichender Platzreserve. Speicher,
Parallelität, Wartezeit und Laufzeit sind begrenzt; bei Fehlern ist eine manuelle
Prüfung erforderlich. Es gibt keinen automatischen Offline-DROP und keine
altersbedingte Löschung von Katalogfakten.

- **239 Servertests bestanden**, darunter 18 neue Schutz- und Policyprüfungen.
- Tatsächlicher Concurrent-Worker in einer eigens erzeugten Testdatenbank
  erfolgreich geprüft; alle 100.000 Testzeilen erhalten und die Testdatenbank
  anschließend wieder entfernt. Produktionsfakten waren nicht Ziel dieses Tests.
- Geprüfter Live-Probelauf: gesunde Indizes, keine Kandidaten und kein unnötiger
  Neuaufbau. Die regulären Backup-/Monitoring-/Wartungstimer sind wieder aktiv.

Die installierten Änderungen betreffen Host-Wartung und Serverbetrieb. App-
Version 1.0.12 und der öffentliche API-Code bleiben unverändert; ein App-Update
ist für die Wiederverbindung nicht erforderlich. Die Ops-Quelldateien und Tests
sind lokal gespiegelt; dieser Incident hat keinen zusätzlichen GitHub-Push oder
App-Release erzeugt.
