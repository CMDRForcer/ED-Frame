# HGE/State Finds: Serverdaten bis zur App geprüft

## Ergebnis

Die zentrale Datenzufuhr war bereits implementiert: EDDN → PostgreSQL
`state_bgs_snapshots` / `state_signals` → `/v1/sync/state-finds` → lokaler
Cache → `stateFindPage`/UI. Sie wird beim Start, nach Server-Statusprüfung
und über REFRESH NOW ausgelöst. Es wurde keine zweite, konkurrierende
Datensynchronisation eingebaut.

Verbessert wurden Herkunftsnachweis und Anzeige: Eingelesene Fakten tragen
`catalog_transport: ED-Frame server`, ohne ihre ursprüngliche Belegklasse,
Identität oder Restlaufzeit zu verändern. Die Seite zeigt Server-BGS- und
Signalzahlen sowie den separaten Synchronisationsstatus. Ein deaktivierter
lokaler EDDN-Empfänger bedeutet nicht mehr optisch, dass der Frame-Server
offline sei. Die Leeransicht erklärt auch bei abgeschaltetem EDDN-Empfänger
die vorhandene Serverquelle und den Unterschied zwischen Prognose und HGE.

## Echte Stichprobe am 7. Oktober 2026

- Öffentliche API: 100 Einträge, alle BGS-Snapshots, keine Signale;
  `hasMore=true`. Eine Stichprobe, nicht der vollständige Serverbestand.
- App-Parser und bestehender Merger: 66 BGS-Beobachtungszeilen aus diesen
  Snapshots mit Server-Herkunftsmarker.
- Echtes Controller-UI-Modell: 65 Einträge, alle **POSSIBLE**, keine als
  VERIFIED/LOCAL LIVE oder aktive EDDN-HGEs dargestellt.
- Beispiele: LHS 3221 und 10 Ursae Majoris, `BGS_PREDICTION`,
  `remainingSeconds=0`.
- Die Prüfung benutzte echte Serverdaten und produktive Parser/Controller-
  Funktionen, aber ein isoliertes Controller-Testobjekt. Kein Commander-
  Profil geschrieben und kein gespielter HGE-Drop getestet.

## Verifikation und Grenzen

11 gezielte State-Finds-Verträge grün: unter anderem Server-Prognose bis
zum UI, lokale Belege behalten Vorrang, alte BGS-Stände werden ersetzt,
Quellobjekte bleiben unverändert und abgelaufene Signale erhalten keine neue
Laufzeit. Abschließende Gesamtregression einschließlich echter QML-Ladetests:
**885 Tests grün**, Exit-Code 0.

Der Server kann derzeit viele BGS-Voraussetzungen liefern, aber die Stichprobe
enthält keine aktuell bestätigten HGE-Signale. Die App darf daraus nur
Suchkandidaten ableiten. Journal/FSS-Beobachtungen bleiben für direkte lokale
Bestätigung entscheidend. Die bestehende cache-before-cursor-Persistenz,
Profilwechsel-Prüfung, 24-h-BGS-Grenze und Signalablaufregeln bleiben erhalten.

## Geänderte Dateien

- `ed_companion/navigation/state_find_catalog.py`: Herkunftsmarker beim Merge.
- `ed_companion/phase14/controller.py`: Server-BGS-/Signalzahlen in Cache-Summary.
- `Main.qml`: sichtbare Serverquelle, Syncstatus und ehrlicher Leerzustand.
- `tests/test_state_find_catalog.py`: Verträge für Herkunft und HGE-Ehrlichkeit.

Die App-Änderungen benötigen einen Neustart des Python-Prozesses, bevor eine
bereits laufende Instanz sie zeigt. Keine App zwangsweise beendet. Kein
Release gebaut, kein Push und kein zusätzlicher Server-Neustart für die
rein clientseitigen HGE-Anzeigeänderungen erforderlich.
