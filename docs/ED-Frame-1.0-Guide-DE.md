# ED-Frame 1.0 — Einstieg und Funktionen

Aktualisiert für App **1.0.8** und den laufenden Katalogserver **0.9.4**.

ED-Frame ist eine kostenlose Windows-Begleitapp für Elite Dangerous mit offenem Quellcode. Dein lokales Journal liefert die Commander-Daten. Unser eigener Community-Server ergänzt sie um gemeinsam gesammelte öffentliche Beobachtungen der Galaxie.

## Installation und Umstieg

1. Lade das Windows-ZIP aus dem [aktuellen ED-Frame-Release](https://github.com/CMDRForcer/ED-Frame/releases/latest) herunter.
2. Entpacke das vollständige Archiv in einen neuen, beschreibbaren Ordner.
3. Starte `ED-Frame.exe`. Der Ordner `_internal` muss daneben bleiben; Python ist enthalten.
4. Wähle deinen Elite-Dangerous-Journalordner, falls er nicht automatisch gefunden wird.
5. Prüfe **Connections / Verbindungen** und öffne den Arbeitsbereich für deine nächste Aktivität.

Voraussetzung ist Windows 10 oder 11. Einstellungen, Zugangsdaten, Baupläne und gespeicherte Beobachtungen liegen unter `%LOCALAPPDATA%\ED-Frame`, außerhalb des Programmordners. Dein vorhandenes Profil wird weiterverwendet; kopiere es nicht ins Programmarchiv. Die neue Veröffentlichungsreihe **1.0 ersetzt die bisherigen EDEC-/ED-Frame-Versionen einschließlich 1.5.43**. Wähle das aktuelle Release und nicht die größte historische Versionsnummer. Die EXE ist nicht signiert; Windows kann einen SmartScreen-Hinweis anzeigen.

## Die Funktionen einzeln

- **Operations:** der nächste Sammel-, Handels-, Freischalt-, Reise- oder Crafting-Schritt für deinen verfolgten Bauplan.
- **Engineering:** Grades und experimentelle Effekte für die tatsächlichen Modulplätze deiner Schiffe planen. Eingebaute Ausrüstung und Plan vergleichen, einschließlich geschätztem Strombedarf.
- **Wishlist:** mehrere Flotten-Baupläne, Materialbereitschaft und vom Journal bestätigten Crafting-Fortschritt verfolgen.
- **Ingenieure:** Fähigkeiten suchen, Freischaltvoraussetzungen verfolgen und passende Ziele finden.
- **Technologie-Broker:** einmalige Human- und Guardian-Freischaltungen mit ihren Anforderungen verfolgen.
- **Materialien:** Bestand, Farmhinweise und Handel prüfen; für Baupläne reservierte Materialien berücksichtigen.
- **MiningFinder:** Rohstoff, Methode, Startsystem und Radius wählen. Fundortbelege, Preis, Nachfrage, Marktalter und Landeplatz vergleichen. Acquire-, Reinforce- und Undermine-Routen planen.
- **Gemessener Mining-Ertrag:** Prospector- und Raffineriebeobachtungen von Hotspotmeldungen und Ringtyp-Schätzungen unterscheiden. Eine Stichprobe garantiert keinen späteren Ertrag.
- **Modul- und Schiffssuche:** beobachtete Stationsangebote und Preise finden; Modulkompatibilität mit deinem aktuellen Schiff und Modulplatz prüfen. Beobachtete und abgeleitete Preise bleiben unterscheidbar.
- **Warensuche:** BUY zeigt Stationsbestand, SELL die Nachfrage. Marktalter, Menge, Landeplatz und Entfernung filtern.
- **Stationsdienste:** in Nav nahe Stationen mit dem gesuchten beobachteten Dienst finden.
- **State Finds und HGE:** Meldungen und verbleibende Signallebensdauer vergleichen. BGS-Prognosen bleiben gesondert gekennzeichnet.
- **Powerplay:** Loyalität, Rang, Merits und ausdrücklich beobachtete Systemkontrolle prüfen.
- **CMDR und Flotte:** Ränge, Ruf, Credits, Vermögen, CR/h und bekannte Schiffe ansehen. Auch geparkte Schiffe planen, ohne im Spiel umzusteigen.
- **Missionen:** Fristen, Ziele, Belohnungen, Massacre-Stapel und erfasste Community Goals verfolgen.
- **Exploration:** unverkaufte Journal-Scans, besondere Himmelskörper und klar als Schätzung ausgewiesene Kartografiewerte prüfen.
- **Exobiologie:** Untersuchungsziele, Probenabstände, abgeschlossene Spezies und beobachtete Einnahmen verfolgen.
- **Oberflächennavigation:** planetare Wegpunkte speichern und per Kompass oder separatem Overlay ansteuern. Live-Führung braucht Koordinaten und Blickrichtung aus Elite; Oberflächenentfernung zusätzlich den Planetenradius.
- **Logbuch:** Flugereignisse durchsuchen und eigene lokale Notizen führen.
- **Darstellung:** sechs Themes, vier Oberflächensprachen, Skalierung, Overlays und Diagnosefunktionen.

## Unser eigener Community-Server

Der Server verarbeitet laufend unterstützte öffentliche EDDN-Beobachtungen. Er liefert Systeme, Stationen, Warenmärkte, Modul- und Schiffsangebote, Ringe/Hotspots, Powerplay-Fakten und State-Finds-Beobachtungen. Unterstützte anonyme Beiträge zu Mining-Ertrag, Signalen und Stationspreisen ergänzen den gemeinsamen Bestand.

**Aktualität richtet sich nach dem Zeitpunkt der Beobachtung.** Ein frisch heruntergeladener alter Preis bleibt alt. MiningFinder prüft Marktbelege und Powerplay-Eignung getrennt. Fehlende Kontrolle, Preise, Nachfrage oder Landeplatzdaten bleiben erkennbar. Eine bestätigte Markt-/Powerplayroute beweist keinen gemessenen Ertrag und garantiert keine im Spiel erhaltenen Merits.

Powerplay-Bestätigungen verwenden bis zu 48 Stunden alte Beobachtungen, unabhängig vom Marktalter-Filter. Geeignete ältere Angaben bis 14 Tage erscheinen mit Originaldatum als **zuletzt bekannt / im Spiel prüfen**; sie zählen nicht als bestätigte Merits. Ausdrücklich unbesetzte Systeme können als Acquire-Ziel dienen, auch ohne Präsenzzeile der gewählten Macht. Fehlende Belege bleiben unbekannt.

App **1.0.8** ergänzt passende Märkte und Ringe, die regionale Toplisten übergehen, mit gebündelten System-/Rohstoffabfragen. Powerplay-Seiten filtern vor der Seitengrenze nach deiner Macht und deinem Ziel. Gezielte öffentliche Spansh-Prüfungen können fehlende Kontrolle ergänzen; Systemidentität, ursprüngliche Quellenzeiten und neuere EDDN-Belege behalten Vorrang. Der Community-Schalter steuert diese Abfragen. Schwere Mining-, Journal- und Powerplay-Vorbereitung läuft in begrenzten Hintergrundprozessen; die Parallelität richtet sich nach verfügbarer CPU und RAM. Große kalte Suchen können weiterhin Zeit benötigen.

Der laufende Server **0.9.4** aktualisiert die gemeinsame Bestandsstatistik ungefähr alle fünf Minuten im Hintergrund. Der Collector-Status bleibt live. Vorhandene App-Installationen 1.0.8 profitieren ohne Neuinstallation.

Bereits gespeicherte Beobachtungen bleiben bei Ausfall oder Abschaltung eines Dienstes lokal nutzbar. Der SQLite-Ringspeicher liest die relevante Region und erhält ursprüngliche Beobachtungen sowie deren Historie. Offline kommen keine bislang unbekannten Live-Meldungen hinzu.

## Verbindungen und Datenschutz

- **ED-Frame-Community-Verbindung:** bei neuen Profilen standardmäßig aktiv. Der Schalter in Connections steuert Katalogzugriff und unterstützte anonyme Beiträge gemeinsam. Abschalten erhält den lokalen Bestand.
- **EDDN:** öffentliche Upload-/Listener-Funktionen sind bei neuen Profilen standardmäßig aktiv und haben einen eigenen Schalter. Unterstützte Meldungen werden gegen ihre Schemas geprüft; private und nicht unterstützte Felder werden ausgeschlossen.
- **Frontier CAPI:** benötigt gesonderte Zustimmung und Frontier-Anmeldung. Ergänzt unterstützte Credits- und Aktivschiffdaten; neuere Journalbelege behalten Vorrang.
- **INARA:** benötigt deine Einrichtung und deinen API-Schlüssel. Kann bei Aktivierung unterstützte Commander-Ereignisse an INARA senden.
- **Spansh und EDSM:** liefern öffentliche Katalogdaten über ihre jeweiligen Verbindungs- und Aktualisierungsoptionen.

Der **ED-Frame-Server** nimmt keine Commander-Namen/FIDs, vollständigen Journaldateien oder Pfade, privaten Baupläne, Wishlists, Zugangsdaten oder Tokens an. Diese Grenze gilt für unseren öffentlichen Dienst; INARA hat eine eigene Commander-Datenintegration. Unterstützte lokale Zugangsdaten werden durch Windows-DPAPI geschützt. Das Abschalten von ED-Frame und EDDN schaltet andere eingerichtete Dienste nicht automatisch ab. Prüfe für rein lokalen Betrieb jede Verbindung.

Die beigefügten **PDF-Handbücher 1.5.5 sind historische Referenzen**. Sie stammen aus der Zeit vor den aktuellen Funktionen und Community-Standardeinstellungen. Für 1.0 gelten diese Anleitung und die [aktuelle README](https://github.com/CMDRForcer/ED-Frame#readme).

[Problem melden](https://github.com/CMDRForcer/ED-Frame/issues) · [Quellcode und Lizenz](https://github.com/CMDRForcer/ED-Frame) · [Website](https://cmdrforcer.github.io/)
