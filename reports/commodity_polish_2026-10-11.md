# Warensuche: Serveraktivierung und Bedienung

Stand: 11. Oktober 2026. Die Server-API ist aktualisiert. Die App-Änderungen
liegen lokal; es gab keinen Commit, Push oder GitHub-Release. Versionsnummern
bleiben App 1.0.8 und Server 0.9.4.

## Umgesetzte Punkte 1–4

1. **Unbegrenzte Suche aktiv:** Radius „UNBEGRENZT“ entfernt tatsächlich die
   Entfernungsgrenze. Systemkoordinaten, Preise, Mengen, Datenalter und
   Landeplatzfilter bleiben geprüft. Bis zu 100 Angebote werden angezeigt;
   weitere Treffer werden kenntlich gemacht. Globale SQL-Abfragen sind
   lesend, auf zehn Sekunden begrenzt und haben zwei Sekunden Lock-Timeout.
2. **Ausgangssystem wählbar:** Neues Feld unter der Warenauswahl. Leer nutzt
   die Journalposition; „Aktuelles System“ leert das Feld. Ein manuell
   eingegebener genauer Name wird erst beim Suchen im Netzwerk-Worker über
   unseren Server aufgelöst. Die letzte Auflösung wird eine Stunde im RAM
   wiederverwendet. Manuelle Suchen bleiben bei Journalbewegung gültig.
3. **Sortierung:** Bester Preis, nächste oder neueste Angebote. SQL sortiert
   sämtliche passenden Märkte vor dem Ergebnislimit. BUY verwendet den
   günstigsten Kaufpreis/Bestand, SELL den höchsten Verkaufspreis/Nachfrage.
   Die App prüft die Sortierbestätigung des Servers.
4. **Leere Ergebnisse:** Die verwendeten Filter werden aus dem abgeschlossenen
   Suchauftrag angezeigt. Schaltflächen können Carrier einschließen, den
   Radius erweitern, bis sieben Tage alte Daten zulassen oder ab einer Tonne
   suchen. Jede Aktion erfordert einen Klick. Es wird keine unbekannte
   Ursache wie „alle Preise veraltet“ behauptet. Kein Abruf beim Tippen oder
   Ändern eines Filters. In kleinen Fenstern scrollen die Filter; Suchbutton
   und Carrierwahl bleiben erreichbar, Ergebnisse haben eigenen Platz.

Die Oberfläche ist in Deutsch, Englisch, Französisch und Spanisch ergänzt.
Fehler, deaktivierter Server und veraltete Anfragen ersetzen keine vorhandenen
Treffer. Der vorhandene begrenzte Netzwerk-Worker wird weiterverwendet.

## Echte öffentliche Marktdaten

Testursprung Sol, Mindestmenge 1 T, Landeplatz L, Datenalter bis 168 Stunden;
Abruf am 11. Oktober 2026. Bestände und Preise verändern sich laufend.

| Suche | Radius | Sortierung | Treffer | Laufzeit HTTP + App-Prüfung |
| --- | --- | --- | ---: | ---: |
| Lithium Hydroxide kaufen, mit Carriern | 500 LY | Preis | 18 | 1,785 s |
| Lithium Hydroxide kaufen, mit Carriern | unbegrenzt | Preis | 24 | 2,247 s |
| Lithium Hydroxide kaufen, mit Carriern | unbegrenzt | Entfernung | 24 | 0,525 s |
| Lithium Hydroxide kaufen, mit Carriern | unbegrenzt | Aktualität | 24 | 0,297 s |
| Lithium Hydroxide kaufen, ohne Carrier | unbegrenzt | Preis | 0 | 0,345 s |
| Lithium Hydroxide verkaufen | unbegrenzt | Preis | 100, weitere | 1,129 s |
| Gold kaufen | unbegrenzt | Preis | 100, weitere | 3,556 s |
| Gold verkaufen | unbegrenzt | Entfernung | 100, weitere | 6,981 s |
| Gold kaufen | unbegrenzt | Aktualität | 100, weitere | 0,323 s |
| Alle seltenen Waren kaufen | unbegrenzt | Preis | 100, weitere | 3,059 s |

Die Lithium-Kaufangebote stammen sämtlich von Carriern; der entfernteste
Treffer lag bei rund 31.594 LY. Das erklärt, weshalb Carrier-Ausschluss oder
eine enge Entfernungssuche keine Angebote liefern können. Der Katalog enthält
315 auswählbare Waren, darunter 142 seltene Waren. Cubeo wurde live exakt
aufgelöst; eine Goldsuche in 500 LY lieferte 100 Angebote in 0,906 Sekunden.
Alle getesteten Sortierungen, Regionsbestätigungen und App-Projektionen waren
korrekt. Ungültige Sortierung/negative Radien liefern 422. Bestehende Clients
ohne Sortierparameter behalten Preisreihenfolge und positiven Standardradius.

## Server-Rollout und Nachweise

Es wurde ausschließlich die API-Quelldatei auf den Server übertragen und die
API neu gestartet. Image und Quelle sind gesichert; automatische Rücknahme
war vorbereitet. Der erste Aktivierungsversuch stoppte vor dem Neustart wegen
fehlender Betriebsdateien im Testcontainer. Nach Korrektur des Testaufbaus
bestanden alle Containerprüfungen und der isolierte Test mit echten Daten.

Aktives Image: `edframe-catalog-api:0.9.4-commodity-polish-20261011-v2`.
Rückfallsicherung: `/opt/edframe-deploy-backups/commodity-polish-20261011-v2`.
API-Quellhash: `f8140c753774dc670d037e8367ac15f17f4e14bc17c6423f07c49669a14c5798`.
Der bestehende Mining-Snapshot-Schalter wurde erhalten. Collector, Datenbank
und Caddy behielten ihre Container-IDs und Startzeiten. Keine neue Tabelle
oder fachliche Migration war erforderlich. Healthcheck bestand; der bereits
zwischengespeicherte Statistikabruf benötigte 0,039 Sekunden am Server.

Validierung: 1.384 App-Tests bestanden; 177 Servertests lokal und im neuen
Linux-Image bestanden. Die reale QML-Oberfläche wurde zusätzlich in Englisch
1920×1080, Deutsch 1120×700 und Französisch 1366×768 geprüft, einschließlich
manueller Eingabe, Sortierung, Leerzustand und Filteraktionen. 35 Prüfbereiche
der portablen App bestanden, inklusive separater Mining-, Journal- und
Powerplay-Berechnungsprozesse. Eingebettete Python-Logik, aktuelle QML- und
Sprachdateien sowie Abwesenheit privater Profile/Zugangsdaten sind geprüft.
Das mitgelieferte Certifi-CA-Zertifikat entspricht der installierten Bibliothek.

## Lokal testen

Die vollständige Test-App liegt in
`output/ED-Frame-Commodity-Polish-Test-20261011-Windows/ED-Frame/ED-Frame.exe`.
Den gesamten Ordner zusammenlassen. Erst die bisherige App einschließlich
Tray beenden, dann diese EXE starten. Die bereits laufende App wurde nicht
ersetzt oder neu gestartet; sie lädt keinen geänderten Python-/QML-Code nach.

Die EXE trägt weiterhin 1.0.8; der Ordner bezeichnet den lokalen Teststand.
EXE-SHA256: `e5e522f4cb5eee7dc437ff6630fb23b61215b12587130ca9f7629f8b1afd3eba`.
Die letzten QML-Anpassungen liegen als abgeglichene Ressource im Testpaket.
Testaufnahmen verwenden ausdrücklich synthetische Markt- und Profildaten.

Der nächste Ausbau ist im
[Handelsrouten-Konzept](trading_route_design_2026-10-11.md) beschrieben:
inzwischen als lokale Rundtour A → B → A eingebaut; der neue Server-Endpunkt
ist nach freigegebenen isolierten Prüfungen aktiv. Testpaket und Prüfungen
stehen im [Rundtour-Bericht](trade_loops_2026-10-11.md).
Mehrere Stopps bleiben ein späterer Ausbau.
