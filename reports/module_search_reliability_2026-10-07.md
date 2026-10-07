# Modulsuche: Einbauprüfung und Vergleichsliste

Stand: 7. Oktober 2026. Lokal umgesetzt; kein Push und kein Server-Deployment.

## Umsetzung

- Konkreter Slot statt nur größtem Slot des Schiffes: Typ, Klasse, Sensor-/Lebenserhaltungsklasse, Militär- und reservierte Slots.
- Schiffsspezifische Zulassung für Hangars, Luxus-Kabinen und weitere reservierte Module aus versionierten Regeln. Unbekannte Schiffe/Regeln bleiben ungeprüft.
- Schiffsspezifische Panzerungen ergänzt; die Hull-ID bleibt erhalten, fremde Panzerung passt nicht. Lightweight Alloys mit Referenzpreis 0 werden nicht als unbekannter Preis behandelt.
- Installationsgrenzen je Modulgruppe: ausgewählten Slot ersetzen erlaubt, zusätzliche Installation über dem Limit gesperrt. Unbekannte vorhandene Module und Weapon-Stabiliser-Ausnahmen bleiben ungeprüft.
- Schildgenerator: maximale Hull-Masse gegen bekannte Hull-Masse. Antrieb: maximale Masse gegen passenden Journal-Loadout inklusive voller Treibstoff-/Frachtkapazität und Ersatzmodul-Massendifferenz. Fehlende/stale Snapshots und unklare Engineering-Masse bleiben ungeprüft.
- Energie ist eine Warnung, kein harter Ausschluss. Referenz-Ziehbedarf gegen Reaktorleistung nur mit ausreichenden Standarddaten; Cargo Hatch, Prioritäten und Engineering sind nicht enthalten.
- Vergleichszeilen statt Variantenkacheln: Klasse/Rating, Modul/Aufhängung/Bezug, slotbezogener Status und eigener Referenzpreis. Sortierung Klasse numerisch, Rating A aufwärts, Aufhängung.
- Unpassende Varianten optional einblendbar; keine Angebotssuche dafür bei aktivem Follow-current-ship. Grund und Energiewarnung im Tooltip.
- Laufzeit ohne Fremdabfragen. Referenzdatei einmal geladen; Projektion gecacht und bei Hull-/Loadout-/Masseänderung invalidiert.

## Referenzdaten

`ed_data/module_fit_reference.json`: 1.208 Moduleinträge, inklusive Hull-Panzerungen und zusätzlichen Regelidentitäten; ca. 276 KB. 75 Hull-Kennungen enthalten auch Alias-/Referenzkennungen, nicht 75 unterschiedliche kaufbare Schiffe.

Quellen und exakte Commits stehen in der JSON-Datei. Standardpreise und Basiseigenschaften stammen aus EDCD/coriolis-data, Reservierungen/Limits und Panzerungsdaten aus der EDSY-Spielreferenz. Referenzpreise sind keine Stationspreisbeobachtungen. Der Importgenerator ist separat, wird nicht beim App-Start ausgeführt.

## Verifikation

| Prüfung | Ergebnis |
| --- | --- |
| Vollständiger Regressionstest | 875 Tests, OK, Exit 0 |
| Finale gezielte Einbau-/QML-Prädikat-/Finder-Tests | 38 Tests, OK |
| Echte Main.qml im isolierten Qt-Smoke-Test | PASS, Exit 0; Shipyard-Seite und befüllte FSD-Vergleichsliste geprüft |
| Cache-Mikrobenchmark, 1.201 Katalogzeilen / 27 Krait-Slots | Erstprojektion ca. 27,6 ms; Wiederholung ca. 0,009 ms; identisches Cacheobjekt |
| Diff-Whitespace-Prüfung | Keine Fehler |

Tests verwenden simulierte Journal-Snapshots und echte gebündelte Referenzdaten. Keine Live-Kaufprüfung, keine Live-Server-Verifikation. Der Qt-Offscreen-Screenshot hatte fehlende Schriftglyphen und erlaubt deshalb keine Freigabe der optischen Lesbarkeit auf dem realen Desktop; er wurde als temporärer Prüfoutput entfernt. Die befüllten Qt-Delegates und ihre Breiten wurden tatsächlich geprüft, nicht nur der QML-Quelltext.

Die ersten Gesamtdurchläufe deckten unübersetzte UI-Texte bzw. einen Fehler im Zugriff des Smoke-Tests auf Qt-Delegates auf. Beide behoben; obige Werte stammen aus erfolgreichen Wiederholungen. Nach dem letzten Gesamtdurchlauf wurde die Preisquellen-Zuordnung der Panzerung präzisiert und mit den 38 gezielten Tests erneut geprüft.

## Bewusste Grenzen

Nicht garantiert: komplette Energie-/Prioritätenplanung, engineered Ersatzmodule, Spezialausnahmen mit fehlender Referenz und sofortige automatische Aktualisierung nach Frontier-Neuerungen. Solche Nachweise werden nicht erfunden. Marktverfügbarkeit und Erwerbs-/Permit-/Unlock-Status bleiben getrennt von physischer Einbaubarkeit.

Keine Änderungen an Servercode, DB-Schema, INARA/EDDN-Queues, atomarer Persistenz, Wishlist/Matching, Material-Allokation oder Journal-Slot-Replay. App neu starten, damit der ergänzte Katalog initialisiert wird.
