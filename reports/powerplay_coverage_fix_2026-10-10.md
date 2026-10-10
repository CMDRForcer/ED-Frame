# Powerplay-Abdeckung: Adressauflösung und fortgesetzte Quellenprüfung

Historischer Zwischenstand vor dem Rollout. Der Server wurde anschließend auf
0.9.3 aktualisiert; siehe [Bericht für 1.0.8](mining_merit_rollout_2026-10-10.md).

Stand: 10. Oktober 2026. Alle Codeänderungen sind lokal, uncommitted und
ungepusht. Keine Serverinstallation, Migration oder Veröffentlichung.
Der öffentliche Server läuft beim Check weiterhin mit Version 0.9.2.

## Befund

Der Datenempfang ist aktiv. Der öffentliche Status meldete zuletzt EDDN-Empfang
um 09:10:43 UTC; die Verkaufsstation in HIP 3254 hat aktuelle Powerplay-Kontrolle.
Eine bestätigte Route benötigt jedoch auch passende Daten für ihren Bergbauort.

Der bisherige Server-Lookup konnte drei Screenshot-Systeme nicht auflösen:
`NO_ADDRESS`. Die öffentliche Mining-API liefert für dieselben Systeme aber
eindeutige Adressen. Der Resolver verwendete nur die Tabelle `systems` und
vorhandene Powerplay-Snapshots, nicht den importierten Mining-Bestand.

Zusätzlich prüfte die App nur sechs fehlende Systeme pro Suchdurchlauf an der
Zusatzquelle. Weitere Systeme wurden vorgemerkt, aber die QML-Seite startete
ohne neue Suche keinen Folgeblock. Die regionale Katalogabfrage und die
gezielte Quellenprüfung sind verschiedene Schritte; eine erfolgreiche
Katalogabfrage bedeutet keine aktuelle Sichtung jedes Systems.

## Live-Prüfung des lokalen Ausweichwegs

Prüfung am 10.10.2026 um 09:34 UTC über die bestehende öffentliche API plus
den neuen lokalen Adress-Ausweichweg. Die ursprünglichen Quellenzeiten bleiben
erhalten. Die folgende Tabelle verwendet UTC, die App zeigt lokale Zeiten.

| System | Ergebnis | Letzte verwertbare Kontrollsichtung |
| --- | --- | --- |
| HIP 3254 | Aktuell: Aisling Duval, Stronghold | 10.10.2026 09:09:17 UTC |
| HIP 92103 | Veraltet: kein neuer Merit-Nachweis | 02.10.2026 23:23:01 UTC |
| Col 285 Sector CG-O d6-62 | Veraltet: kein neuer Merit-Nachweis | 27.09.2026 15:54:06 UTC |
| Swoilz WR-F c17 | Quelle ohne verwertbare Powerplay-Felder | Keine Kontrollsichtung übernommen |
| Col 285 Sector AV-F c11-18 | Veraltet: kein neuer Merit-Nachweis | 08.10.2026 06:24:31 UTC |

Hier konnte **keine zusätzliche aktuelle Bergbau-Kontrolle** gewonnen werden.
Zwei vorher unbekannte Orte lassen sich jetzt als vorhandene, aber veraltete
Sichtung erklären. Dies ist keine neue aktuelle Bestätigung. Der öffentliche
Status und diese Stichprobe belegen keine vollständige galaxieweite Abdeckung.

Quellen: [ED-Frame-Status](https://vps-20b25c36.vps.ovh.net/v1/status),
[HIP 92103](https://spansh.co.uk/api/dump/1384900446587),
[Col 285 CG-O d6-62](https://spansh.co.uk/api/dump/2140814690683),
[Swoilz WR-F c17](https://spansh.co.uk/api/dump/4756978209538),
[Col 285 AV-F c11-18](https://spansh.co.uk/api/dump/5031990334186).
Die [EDDN-Spezifikation](https://github.com/EDCD/EDDN/blob/live/schemas/journal-v1.0.json)
überträgt öffentliche Journal-Ereignisse; sie ist keine vollständige aktuelle
Powerplay-Datenbank aller Systeme.

## Lokale Änderungen

- Der vorbereitete Server-Resolver prüft zusätzlich Mining- und Stationsadressen
  über vorhandene Namensindizes. Identitätskonflikte verhindern einen Abruf.
  Eine Schemaänderung ist nicht nötig. Der neue Resolver ist nicht deployt.
- Meldet der vorhandene Server `NO_ADDRESS`, kann die App eine eindeutige
  bekannte Mining-Adresse direkt an Spansh prüfen. Systemname und id64 müssen
  passen. Keine Namensschätzung, keine zusätzlichen Zielsysteme, keine
  Übernahme fehlender Kontrolle als `Unoccupied`.
- Weiterhin höchstens sechs Zielsysteme je Quellenblock. HTTP bleibt außerhalb
  des UI-Threads; der direkte Ausweichweg läuft innerhalb derselben Prüfung.
  Quellenantworten sind auf 2 MiB, feste HTTPS-Adressen, keine Weiterleitungen
  und begrenzte Verbindungs-/Lesezeiten beschränkt. Das 8-Sekunden-Budget wird
  nach Antwortteilen geprüft; ein laufender Lese-Timeout kann es verlängern.
- Nur aktuelle explizite Fakten innerhalb von 24 Stunden beeinflussen die
  Merit-Bewertung. Veraltete Zeiten bleiben Diagnoseinformationen. Markt- und
  Ringzeiten erneuern keine Powerplay-Sichtung.
- Die sichtbare Mining-Seite setzt vorgemerkte Quellenchecks mit 30 Sekunden
  Abstand fort. Ein laufender Plan, Marktimport oder Quellencheck pausiert den
  Timer. Seitenwechsel, deaktivierte Community-Verbindung und leere Warteliste
  stoppen ihn. Kein dauerndes Polling nach vollständiger Abarbeitung.
- Zurückgestellte Ziele erhalten 20 Sekunden Wiederholungsfrist; tatsächlich
  erfolglose Prüfungen 10 Minuten, Quellenfehler 2 Minuten. Dadurch prüft der
  nächste Block andere Orte, ohne denselben Fehler sofort erneut abzufragen.
- Die Routenkarten zeigen je Bergbau-/Verkaufssystem den Quellenzustand und
  den ursprünglichen Zeitpunkt. Badge-Tooltips liefern dieselbe Erklärung.
  Texte sind in Deutsch, Englisch, Französisch und Spanisch vorhanden.
- Profilwechsel/Reset leeren Warteliste und Diagnosen. Eine neue Suche entfernt
  vorgemerkte Systeme, die nicht mehr zu ihren Ergebnissen gehören.

## Prüfung

- 1.342 App-Tests bestanden, finale Gesamtsuite mit isoliertem Test-Journal.
- 160 Servertests bestanden. Quellen und Datenbank waren simuliert; der native
  ASGI-Test lief außerhalb der Windows-Socket-Sandbox mit lokalem Loopback.
- Echter QML-Test: Folgeblock startet, prüft die große id64 unverändert,
  pausiert bei Arbeit/Seitenwechsel und stoppt bei leerer Warteliste.
  Quellenzeit wird lokal dargestellt; Diagnosen erzeugen keine Kontrollfakten.
- QML-Vorschau mit synthetischem Journal und gesperrten Netzaufrufen visuell
  geprüft. Die Quellendetails sind lesbar und bleiben innerhalb der Karte.
- Live-Ausweichweg für die fünf Screenshot-Systeme ausgeführt; eine aktuelle
  Verkaufs-Kontrolle, drei veraltete Bergbau-Sichtungen, ein Ort ohne Daten.
- Repository-Hygiene und `git diff --check` bestanden.
- Neuer portabler EXE-Build: 35 von 35 Smoke-Prüfungen bestanden, einschließlich
  asynchroner Seiten und echter separater Mining-/Journal-/Powerplay-Rechenjobs.
  Ausführungsende mit Exit-Code 0; keine QML-Laufzeitfehler.

Die lokale App enthält auch die zuvor geprüfte adaptive Lastverteilung.
Der gepackte EXE-Smoke-Test wird separat als JSON mitgeliefert.

## Was offen bleibt

Aktuelle Beobachtungen für die vier Bergbauorte müssen aus echten Journal-/
EDDN-Sichtungen oder frischeren expliziten System-Snapshots eintreffen.
Die API korrigiert die Adressauflösung für alle Nutzer erst nach einem späteren
Server-Rollout. Der lokale App-Ausweichweg funktioniert schon mit dem aktuellen
Server. Eine weitere Quelle darf die Lücke ergänzen, wenn sie eindeutige
Kontrolle, Zustand, Systemidentität und einen belastbaren Beobachtungszeitpunkt
liefert; reine Power-Präsenz oder ein neuer Downloadzeitpunkt reichen nicht.
