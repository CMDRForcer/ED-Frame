# Lokaler Mining-/Powerplay-Abgleich – 10.10.2026

Historischer Zwischenstand vor dem Rollout. Der abschließende Abgleich und die
Veröffentlichung sind im [Bericht für 1.0.8](mining_merit_rollout_2026-10-10.md)
dokumentiert; die folgenden Messwerte beschreiben den damaligen Ausgangsstand.

Die Platinum-Suchen finden jetzt beide aktuellen MeritMiner-Systeme bei 250 und
500 LY mit denselben Preisen und Nachfragen. ALL COMMODITIES liefert deutlich
mehr brauchbare Systeme, erreicht aber noch keine vollständige Trefferparität.
Der Stand ist lokal, basiert auf App-Version 1.0.7 und wurde nicht veröffentlicht.

## Umgesetzte Änderungen

- Zeitabhängige Powerplay-Bewertung: bis 48 Stunden aktuell; bis 14 Tage explizit
  „zuletzt bekannt / im Spiel prüfen“. Originaldaten bleiben datiert. Solche
  Vorschläge zählen nicht als verifizierte Merits. Präsenz allein bleibt unbekannt.
- Begrenzte regionale Preislisten werden durch gezielte, regelkompatible
  System-/Rohstoff-Abfragen ergänzt. Zwei Verbindungen, bei knappen Ressourcen
  eine; maximal 64 Abfragen und 20 Sekunden Dispatch-Zeit pro Block.
- Vorhandene Märkte und kurze Caches vermeiden Wiederholungen. Gefüllte
  Antworten werden fünf Minuten, erfolgreiche leere Antworten zehn Minuten
  wiederverwendet; Fehler und abgebrochene Prüfungen gelten nicht als Abwesenheit.
- ALL lädt alle Ringtypen unabhängig vom ersten Rohstoff der Markt-Vorbereitung.
  Das Budget beträgt 200.000 rohe Regionaldatensätze; konkrete Suchen behalten
  50.000. Cursor-Fortsetzung funktioniert über die numerische Offset-Grenze hinaus
  auf kompatiblen älteren Servern. Teilabdeckung bleibt sichtbar.
- ALL-Merit-Suchen zeigen zunächst die beste Route pro System und berücksichtigen
  bei gleicher Eignung den tatsächlichen Verkaufspreis. Weitere Ringe folgen.
- Eine frische Kontrollmacht ohne Systemzustand verhindert keine gezielte
  Powerplay-Ergänzung mehr. Fehlende Zustände werden weiterhin nicht erfunden.
- Die neue Quellenanzeige bleibt auch bei 1366 Pixel Fensterbreite in ihrer Karte.
  Deutsch, Englisch, Französisch und Spanisch enthalten die neuen Hinweise.

Die beigefügte PNG-Quellenanzeige stammt aus einem isolierten synthetischen
Journal. „SERVER OFFLINE“ entsteht durch gesperrte Netzaufrufe dieser UI-Prüfung;
Example Port und die dortigen Beobachtungen sind Testbeispiele.

Painite-Lasersuche bleibt auf Metallic-Ringe begrenzt; ein Metal-Rich-Hotspot
belegt dort keine Laser-Ausbeute. Siehe die [Beobachtungen im Frontier-Forum](https://forums.frontier.co.uk/threads/mining-hotspots.574896/).

## Tatsächlicher Ergebnisabgleich

Start HIP 3254, Aisling Duval, REINFORCE, Laser, alle Reserven/Ringe,
L-Pad, Nachfrage mindestens 5.000 t, maximal 48 Stunden Marktalter, kein
Nachfrage-Maximum. Öffentliche [MeritMiner-Suche](https://meritminer.cc/) und
[ED-Frame-Katalog](https://vps-20b25c36.vps.ovh.net/health), mit gespeicherten
Originalbeobachtungen und der echten Controller-/SQLite-/Planner-Pipeline.

| Rohstoff | Radius | Vergleichssysteme gefunden | Eigene verifizierte Systeme in den 100 Ergebnissen | Rechenschritt |
|---|---|---|---|---|
| Platinum | 250 LY | 2/2 | 7 | 0.76 s |
| Platinum | 500 LY | 2/2 | 7 | 1.10 s |
| ALL | 250 LY | 14/25 | 61 | 17.48 s |
| ALL | 500 LY | 14/25 | 65 | 22.46 s |

Die Rechenzeiten enthalten weder Netzwerkabruf noch Markt-Import. ALL wurde mit
dem gefüllten öffentlichen Marktbestand aus dem vorhandenen App-Cache getestet;
dieser wurde ausschließlich lesend geöffnet. Die Ergebnisse entstehen in eigenen
Test-Datenbanken. Rechenzeiten sind Einzelmessungen auf diesem PC.

Platinum: Rautandji / Tarter City, 58.486 CR/t und 5.945 t; CD-86 4 /
Cummings Dock, 53.763 CR/t und 22.115 t. Die ursprüngliche regionale Top-Liste
hatte beide übergangen. Mit demselben eingefrorenen Ausgangsbestand fehlen sie
ohne die gezielte Ergänzung weiterhin; der Vergleich ist reproduzierbar.

ALL: Der eigene beste aktuelle Treffer ist HIP 104026 / Tomorrow’s Harvest,
Platinum für 280.890 CR/t und 206.627 t Nachfrage. Kontrollbeobachtung
10.10.2026 09:59:30 UTC, Marktbeobachtung 06:14:09 UTC. Das ist ein Vergleich
des Verkaufspreises, keine berechnete oder garantierte Merit-Auszahlung.

MeritMiner gab bei ALL jeweils 30 Systeme aus. Fünf Angebote betreffen Rohstoffe,
die unser Katalog nicht der ausgewählten Laser-Asteroiden-Methode zuordnet;
diese sind in der JSON-Datei separat aufgeführt. Von den verbleibenden 25 sind
14 auch in den eigenen aktuellen Ergebnissen vorhanden. Zusätzliche eigene
Systeme beweisen allein keine Überlegenheit; Auswahl und Sortierung unterscheiden
sich. Gleiche Systeme können bei ALL unterschiedliche Rohstoffe vorschlagen.

## Verbleibende Grenzen

Die breite Suche erreicht noch keine vollständige Gleichwertigkeit. Es fehlen
einige konkrete Marktangebote im lokalen Bestand, und die 64 gezielten Abfragen
prüfen nur einen Teil der möglichen Kombinationen. Die sichtbaren offenen
Prüfungen laufen in Sechserblöcken weiter, wenn die Mining-Seite sichtbar und
idle ist. Nicht alle Tausende von Kandidaten werden automatisch nachgeladen.

Große Ringabfragen können nach Änderungen während der Seitenausgabe oder beim
Erreichen eines Server-/Client-Limits nur Teilabdeckung liefern. Die gemessenen
ALL-Ringsnapshots waren so gekennzeichnet; sie sind kein vollständiger regionaler
Beweis. Kalte Abrufe können mehrere Minuten dauern. Diese Arbeit läuft außerhalb
des UI-Threads; eine komplette UI-Latenzmessung für den großen ALL-Bestand ist
noch offen. Der nächste wesentliche Schritt ist eine serverseitige,
nach Powerplay und Mining-Methode vorgefilterte Markt-Abfrage, die die Preis-
Toplisten und vielen Einzelabfragen ersetzt. Aktuelle fehlende Powerplay-Fakten
benötigen weiterhin echte, datierte Beobachtungen.

## Prüfung und Verwendung

- 1.364 App-Tests bestanden; ergänzende Mining-/QML-Prüfungen ebenfalls bestanden.
- Die portable EXE besteht 35 Smoke-Prüfungen einschließlich echter separater
  Mining-/Journal-/Powerplay-Rechenprozesse; das aktuelle Protokoll liegt daneben.
- Repository-Hygiene und git diff --check bestanden. Begrenzte Ressourcen sind
  durch simulierte CPU-/RAM-Szenarien geprüft; keine Messung auf jedem fremden PC.
- Die zuvor umgesetzte adaptive Hintergrundverteilung ist im Paket enthalten.
  In diesem Schritt wurde kein Server-Rollout vorgenommen.

Für die neue laufende App ED-Frame vollständig beenden, auch im Tray. Die ZIP
vollständig in einen eigenen Ordner entpacken und ED-Frame.exe daraus starten.
Das vorhandene Commander-Profil wird weiter benutzt. Die bereits laufende alte
EXE übernimmt geänderten Quellcode nicht automatisch.
