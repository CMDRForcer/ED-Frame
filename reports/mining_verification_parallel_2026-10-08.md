# Schnellere gezielte Mining-Verifizierung – 8. Oktober 2026

## Ergebnis und Grenzen

Unabhängige Markt-, Ring- und Powerplay-Prüfungen laufen jetzt in höchstens zwei
parallelen HTTP-Arbeitsspuren. Bekannte, validierte Koordinaten des jeweiligen
Abbausystems werden wiederverwendet. Die gezielte Verifizierungsphase wurde im
Live-Erstlauf von 7,326 auf 4,304 Sekunden kürzer; die zugehörigen HTTP-Prüfungen
waren nach 1,748 statt 7,011 Sekunden abgeschlossen.

Die komplette Erstsuche wurde in diesem Live-Vergleich **nicht wesentlich
schneller**: 49,365 gegenüber 49,231 Sekunden bis zum ruhigen Suchzustand. Das
regionale Laden, Zusammenführen und Planen vor der gezielten Prüfung bleibt der
größere Engpass. Der Nachher-Lauf hatte außerdem 629 zusätzliche lokale Ringe und
andere aktuelle Serverantworten. Die Zahlen sind Einzelmessungen, keine Garantie.

Die Messungen erfolgten mit dem Quellcode nach Version 1.5.41, vor der
Auslieferung dieser Änderungen mit **Version 1.5.42**. Die installierte App wurde
dabei nicht verändert. BGS-Prognosen und originale AppData-Dateien bleiben unverändert.

## Ursachen und Fixes

1. Die Marktprüfungen liefen nacheinander und warteten vorher auf andere
   Prüfarten. Jetzt teilen sich alle unabhängigen Jobs einen begrenzten Pool
   mit zwei Threads. Cursor-Seiten und Anbieter-Fallbacks innerhalb eines Jobs
   bleiben in ihrer bisherigen Reihenfolge.
2. Sechs gezielte Marktprüfungen lösten bekannte Abbausysteme erneut nach
   Koordinaten auf. Jetzt wird ausschließlich die gültige Koordinate des
   jeweiligen Abbausystems übernommen – niemals die des Verkaufs- oder
   Suchstartsystems. Fehlende/ungültige Koordinaten behalten den alten Fallback.
3. Einzelne Markt-GETs bauten Verbindungen erneut auf. Jede Arbeitsspur besitzt
   jetzt eine eigene wiederverwendete HTTP-Session. Sessions werden nicht
   zwischen Threads geteilt und nach Abschluss aller Jobs geschlossen.
4. Profilgeneration, Katalogpfad, Reset, Shutdown und Server-Umschalten werden
   vor Jobstart und jedem GET geprüft. Bereits laufende HTTP-Aufrufe behalten
   ihre bisherigen Timeouts; nachfolgende Aufrufe veralteter Jobs werden blockiert.
   Ein Server-Umschalten verwirft auch die alte Veröffentlichung, statt daraus
   negative API-Retry-Caches zu bilden. Abgebrochene CHECKING-Markierungen werden
   entfernt und eine wartende Suche mit der neuen Einstellung gestartet.

Abschlüsse können in beliebiger Reihenfolge eintreffen. Ergebnisse werden danach
in Eingabereihenfolge zusammengeführt, damit gleich datierte Marktwerte,
Persistenz und Ranking nicht vom Netzwerk-Timing abhängen. Bestehende Grenzen
(unter anderem sechs gezielte Marktprüfungen), Filter und Aktualitätsprüfungen
bleiben bestehen. Fehlende Belege bleiben unbekannt, nicht künstlich bestätigt.

## Vergleich mit identischen Antworten

`tools/benchmark_mining_verification.py` führt die echte alte Controller-Methode
aus dem lokalen Tag `1.5.41` und die neue Methode gegen dieselben synthetischen
öffentlichen API-Antworten aus. Kein Netzwerk, kein Benutzerprofil und keine
Persistenz. Pro Request sind 50 ms künstliche Wartezeit vorgegeben; ein Ardent-
Fehler erzwingt den vorhandenen EDData-Fallback.

| Messung | Vorher | Nachher |
| --- | ---: | ---: |
| Prüfphase, synthetisch, Abschlusslauf | 1,0138 s | 0,3547 s |
| HTTP-Aufrufe | 20 | 14 |
| Davon erneute Koordinatenabfragen | 6 | 0 |
| Höchstens gleichzeitig aktive HTTP-Aufrufe | 1 | 2 |
| Erledigte Prüfungen | 13/13 | 13/13 |

Ergebnis-Hash und tatsächliche Markt-/Powerplay-Abfragen inklusive Fallback
stimmen überein. Nur die sechs redundanten Koordinatenabfragen entfallen.
Die künstliche Beschleunigung ist **keine** Behauptung über reale Suchzeiten.

## Live-Test und Bedienbarkeit

Realer Controller und reale QML-Seiten, Windows/PySide, Offscreen-/Software-
Renderer mit 1600 × 1000 Pixeln; isolierte Kopien ausschließlich öffentlicher
Katalogdaten und ein synthetisches Commander-Journal. Automatische Journal-Polls
aktiv; ausschließlich öffentliche GETs, Uploads blockiert. Angefordert sind
100 Ergebnisse mit Powerplay-Merit-Optimierung, Platinum und 250 LY.

| Messung | Vorher | Nachher |
| --- | ---: | ---: |
| Erste lokale Ergebnisse | 2,670 s | 2,595 s |
| Gezielte Prüfung, Erstsuche inkl. Veröffentlichungsvorbereitung | 7,326 s | 4,304 s |
| Gezielte Prüfung, Wiederholung | 5,879 s | 4,578 s |
| Erstsuche vollständig ruhig | 49,365 s | 49,231 s |
| Wiederholung vollständig ruhig | 24,062 s | 22,655 s |

Alle veröffentlichten Listen enthielten 100 Zeilen, keine zwischenzeitliche
Leerung. Alle letzten Ergebniszeilen waren im letzten Verifizierungssnapshot
enthalten; das bedeutet Prüfabdeckung, **nicht** 100 bestätigte Merit-Routen.
Die Erstsuche erledigte 46/46 geplante Prüfungen ohne Verarbeitungsfehler.
40 abgefragte Systeme lieferten keine aktuellen Powerplay-Belege und blieben
entsprechend unbestätigt.

Im zusätzlichen Nachher-Lasttest wurden 45 echte Tabwechsel ausgeführt,
davon 39 bei aktivem regionalem Sync. Median: 35 ms, Maximum: 373 ms.
Keine QML-Fehler, keine Eventloop-Abstände über 500 ms während der beiden Suchen
oder Tabwechsel. Das ist kein hardwareunabhängiges Reaktionszeitversprechen.
Der RAM-Spitzenwert der beiden Suchen blieb vergleichbar (rund 1.061 MiB);
der zusätzliche Tabtest erreichte rund 1.098 MiB. Dies ist kein neuer RAM-Fix.

Messdaten liegen lokal unter `.test-tmp/mining-verification-{before,after,controlled}-20261008/`
und `.test-tmp/mining-verification-controlled-final-20261008/`.
Die großen selbst angelegten Katalog-/Journal-Kopien wurden entfernt (4,088 GiB);
Ergebnis-JSON und Quelleninventare bleiben erhalten. Originaldaten bleiben erhalten.
Der zusätzliche Veröffentlichungs-/Retry-Schutz beim Server-Umschalten wurde
nach dem Live-Lauf ergänzt und gezielt getestet; er ändert die normale parallele
Prüfung bei unveränderter Einstellung nicht.

## Prüfstatus

- Neue Regressionen prüfen Zwei-Thread-Limit, eigene Session je Thread,
  Verbindungsfreigabe, isolierte Fehler, Abbruchgrenzen, Koordinatenvalidierung,
  überlappende Powerplay-/Marktprüfung, deterministische Ergebnisse, externe
  Marktquellen bei deaktiviertem Server sowie cachefreien Abbruch und Neustart
  einer wartenden Suche beim Server-Umschalten.
- Abschließende Gesamtsuite: **1.189 Tests erfolgreich** (136,275 s), darunter
  neun neue Regressionstests und die echten QML-Slot-/Ergebnisstabilitätstests.
  Zusätzlich 101 gezielte Mining-Tests nach dem letzten Abbruchschutz erfolgreich.
- `git diff --check`, Repository-Hygieneprüfung und gesonderte Datenschutzprüfung
  aller neuen Dateien erfolgreich. Der kontrollierte Vorher-/Nachher-Vergleich
  mit identischen Antworten wurde nach der letzten Codeänderung wiederholt.
- Zum Zeitpunkt dieser Messungen keine Commit-, Push-, Release-, Installations-,
  Neustart- oder Shutdown-Aktion. Die anschließende Auslieferung gehört zu 1.5.42.

## Nächster sinnvoller Hebel

Das regionale Datenladen und die Vorbereitung vor dem Start der gezielten
Verifizierung untersuchen. Nicht einfach Prüfbudgets, Marktalter oder Datenumfang
reduzieren: Das würde die Wartezeit mit weniger Leistung erkaufen.
