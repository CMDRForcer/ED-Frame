# Handelsrouten – Rundtour A → B → A

Stand: 11. Oktober 2026. Lokal implementiert; der Server-Endpunkt wurde
nach isolierten Tests und Messungen mit dem echten Bestand aktiviert.

Die gewählte Form orientiert sich an
[Inaras Routenübersicht](https://inara.cz/elite/market-traderoutes/): zwei
Stationen mit Hinfracht und Rückfracht. ED-Frame zeigt beide Handelsstrecken
mit Ware, Menge, Einkaufskosten, Preisen und geschätztem Gewinn. Der neue
Reiter liegt unter Navigation. Die Warensuche kann ihre Ware und ihr
Ausgangssystem direkt übernehmen.

Ein manuelles Ausgangssystem oder die Journalposition, freie Ladekapazität,
Einkaufsbudget, Radius für Station A, maximale Strecke A–B, Datenalter,
Landeplatz und Carrierwahl begrenzen die Suche. Schiffswerte können die
Kapazität und ein bekanntes Budget vorbelegen; den freien Frachtraum muss
der Nutzer prüfen. Eine bestimmte Hinfracht erlaubt weiterhin andere
Waren auf der Rückfahrt. Beide Strecken brauchen einen positiven Gewinn.

```text
Menge = min(Frachtlimit, Kaufbestand, Verkaufsnachfrage,
            floor(verfügbares Budget / Einkaufspreis))
Gewinn = Menge × (Verkaufspreis − Einkaufspreis)
Budget für Rückfracht = Anfangsbudget + Gewinn der Hinfracht
Rundtourgewinn = Gewinn Hinfracht + Gewinn Rückfracht
```

Die Berechnung verwendet beobachtete Angebote, keine Ersatzpreise
und keine erfundenen unendlichen Mengen. Entfernungen stammen aus den
Koordinaten beider Stationen. Bekannte Zugangsprobleme, Carrier und
prohibierte Waren bleiben als Hinweise sichtbar. Gewinn ist eine Schätzung;
eine Verdienstangabe pro Stunde setzt eine belastbare Zeitmessung voraus.

Der neue Server-Endpunkt `/v1/markets/trade-routes` prüft eine begrenzte
regionale Auswahl von bis zu 320 Märkten und 80 Startmärkten. Sämtliche
verwendbaren Warenangebote dieser Märkte gehen in die Rechnung ein;
vollständige Rundtouren werden erst danach sortiert und begrenzt. Die App
kennzeichnet eine Teilauswahl und nennt die Zahl geprüfter Märkte. SQL ist
lesend und zeitbegrenzt. Ein gemeinsamer Lock begrenzt parallele Rundtour-
Berechnungen; ein Cache spart identische Anfragen für 60 Sekunden.

Die App sucht und prüft Preise nur auf Benutzeraktion in einem vorhandenen
Netzwerk-Worker. Sie übernimmt Ergebnisse gebündelt und behält bei Fehlern
den bisherigen Stand. Mengen, Budgets, Gewinne und Geometrie werden auf
Clientseite erneut geprüft. Nach der Suche lassen sich die Filter wieder
aufklappen; in kleinen Fenstern bleiben Suchaktionen und Ergebnisse
erreichbar. Auswahl und Kopieraktionen sind eingebaut.

Die ausdrücklich freigegebene Serveraktivierung ist abgeschlossen: 182 Tests
im getrennten Linux-Image, vier lesende Suchen mit echten Sol-Marktdaten
(6,469–9,048 Sekunden, jeweils 30 Rundtouren), gesicherte Quellen und altes
Image, gezielter Austausch des API-Dienstes und bestandene Healthchecks.
Collector, Datenbank und Caddy behalten ihre bisherigen Container-IDs und
Startzeitpunkte. Die App bleibt ein lokaler Teststand. Einzelheiten und
Prüfungen stehen im [Rundtour-Bericht](trade_loops_2026-10-11.md).

Spätere Ausbaustufen: Fortschritt über Journalereignisse, Favoriten,
gezielte Rückwarenwahl und mehrere Stopps. Diese sind nicht Bestandteil der
jetzigen Rundtour-Version.
