# Öffentliche Serverstatistik auf der Projektseite

Die GitHub-Pages-Seite zeigt den öffentlichen Katalogbestand: Systeme und
Stationen, Warenmärkte samt Aktualität, Mining-Belege, Module, Schiffe sowie
BGS-Snapshots und Signalsichtungen. Dazu kommen empfangene, verwendete und
nicht projizierte EDDN-Nachrichten, Verarbeitungsfehler und eine aufklappbare
Aufschlüsselung nach Nachrichtentyp für die letzten 24 Stunden-Buckets.

Der Browser fragt den vorhandenen `/v1/status`-Cache alle fünf Minuten ab,
pausiert in versteckten Tabs und verhindert überlappende Abrufe. Unbekannte
Werte bleiben unbekannt; fehlgeschlagene Abrufe erhalten die zuletzt geladenen
Zahlen mit ihrem ursprünglichen Datum. Die Webseite ist auf App-Version 1.0.9
aktualisiert. Eine zusätzliche App-Version ist hierfür nicht erforderlich.

## Prüfung und Serveränderung

- JavaScript-Syntax, HTML-Verweise und strukturierte Metadaten geprüft.
- Desktop- und Mobilansicht (390 px), aktuelle/veraltete Antworten,
  ungültige Antworten und Ausfall mit erhaltenen Zahlen im Browser geprüft.
- Caddy-Konfiguration vor Aktivierung validiert. Erlaubt ausschließlich
  credential-freie Browserabrufe von `GET /v1/status` durch
  `https://cmdrforcer.github.io`; keine Wildcard und keine Credentials-Freigabe.
- HTTPS-Statusabruf liefert 200 und die passende Origin; `/healthz` liefert
  weiterhin 200 ohne CORS-Freigabe. Fremde Origins erhalten keine passende
  Freigabe.
- Datenbank, API, Collector und Caddy wurden nicht neu gestartet.

Die erste Reload-Prüfung erkannte einen veralteten Docker-Datei-Bind-Mount und
stellte automatisch die vorherige Konfiguration wieder her. Anschließend wurde
die validierte Konfiguration direkt aus dem persistenten Caddy-Verzeichnis
geladen. Host-Quelldatei und aktiv geladene Konfiguration sind synchronisiert.
Sicherung auf dem Server:
`/opt/edframe-deploy-backups/website-statistics-20261011-v2`.

Website: <https://cmdrforcer.github.io/#server-statistics>
