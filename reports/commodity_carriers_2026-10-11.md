# Carrier-Angebote in der Warensuche · 11.10.2026

## Ursache und Korrektur

Die Warensuche schloss Fleet Carrier standardmäßig aus. Außerdem entfernte die frühere Beschränkung auf normale Stationskäufe Bergbau- und Missionswaren aus Katalog, direkter Suche und Ergebnisanzeige. Der Server hatte die Angebote bereits gespeichert.

Lokal sind Carrier jetzt standardmäßig eingeschlossen. Die Suche lässt bekannte Waren der Handelskategorien einschließlich Lithiumhydroxid, Bromellit, Platin, Painit und modularer Terminals zu. Im aktuellen Serverkatalog sind damit **315 statt 269 Waren** auswählbar, also **46 zusätzliche Waren**. Die Einstufung als Handelsware allein erzeugt kein Angebot: Preis, Bestand beziehungsweise Nachfrage, Datenalter, Entfernung und erforderliche Landeplattform werden weiter geprüft.

Wer Carrier bewusst ausschließt, bekommt bei einer Kaufsuche einen erklärenden Hinweis. Beschriftungen und Hilfetexte berücksichtigen Stations- und Carrier-Angebote auf Deutsch, Englisch, Französisch und Spanisch. Seltene Waren behalten ihre eigene Kategorie und Sammelsuche.

## Live-Prüfung

Lesende Abfragen mit dem korrigierten App-Code am 11.10.2026. Vergleichsbedingungen: **Sol als Ausgangspunkt, 500 LY, maximal 168 Stunden Datenalter, mindestens 1 T, Plattform L**.

| Suche | Carrier eingeschlossen | Angezeigte Angebote |
|---|---|---:|
| Lithiumhydroxid kaufen | Ja | 18, sämtlich Carrier |
| Lithiumhydroxid kaufen | Nein | 0 |
| Modulare Terminals kaufen | Ja | 34, sämtlich Carrier |
| Bromellit kaufen | Ja | 79, sämtlich Carrier |
| Lithiumhydroxid verkaufen | Ja | 100, darunter 8 Carrier; weitere Treffer vorhanden |

Alle empfangenen, gültigen Angebote bleiben in der App-Projektion sichtbar. Diese Zahlen gelten für die genannten Vergleichsbedingungen und den Prüfzeitpunkt; engerer Radius, geringeres Datenalter oder höhere Mindestmenge können Treffer weiter begrenzen.

## Prüfung und Testversion

Die gezielten Waren- und Qt-Tests prüfen Carrier-Käufe, Stationsverkäufe von Bergbauwaren, bewusstes Ausschließen von Carriern und die Anzeige von Lithiumhydroxid. Die bisherigen Prüfungen zu Preisen, Mengen, Datenalter, seltenen Waren und Profilwechseln bleiben erhalten.

Alle **1.376 Tests bestehen**. Zusätzlich besteht die neue portable EXE **35 Funktionsprüfungen**, einschließlich der separaten Hintergrundprozesse. Die eingefrorene Warenlogik wurde direkt aus der EXE geprüft: Lithiumhydroxid ist auswählbar, Carrier sind standardmäßig eingeschlossen und gültige Carrier-Angebote bleiben sichtbar. Gebündelte QML- und Sprachdateien stimmen mit dem Quellstand überein; Prüfungen auf private Daten und unerwünschte Laufzeitdateien bestehen.

Die deutschen Vorschauen bei 1280 × 800 und 650 × 850 zeigen Carrier-Angebote und den Hinweis beim bewussten Ausschließen ohne Layoutfehler oder abgeschnittenen Hinweistext. Die Qt-Regression prüft zusätzlich die echte Hauptansicht auf Deutsch, Englisch und Französisch.

Testversion: `output/ED-Frame-Carrier-Test-20261011-Windows/ED-Frame/ED-Frame.exe`. Sie enthält auch die bisherigen lokalen Start- und UI-Verbesserungen. Die bisherige App vollständig beenden, einschließlich Tray, und anschließend diese EXE starten. Der komplette portable Ordner muss zusammenbleiben. Versionsnummer weiterhin 1.0.8, da keine Veröffentlichung erfolgt.

Änderungen bleiben lokal. Kein Commit, Push, Release oder Server-Deployment; die laufende App wurde nicht ersetzt.
