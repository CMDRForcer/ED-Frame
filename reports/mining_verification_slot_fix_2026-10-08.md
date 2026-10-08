# MiningFinder: QML-Nachprüfung repariert

8. Oktober 2026. Behebt den in der Ausgangsmessung von 1.5.40 nachgewiesenen
Typfehler; kein Umbau der Suchpipeline oder Datenhaltung.

## Ursache und Änderung

`verifyCurrentSearch()` kopiert Routen vor dem verzögerten Aufruf in ein neues
JavaScript-Array. Die bisherige Qt-Signatur mit `PyObject` akzeptierte dieses
Array nicht. Der Aufruf scheiterte vor Eintritt in die Python-Methode, während
der QML-Suchrevisionsmarker bereits gesetzt war.

Beide Produktionsüberladungen von `verifyMiningRoutes` sind nun mit
`QVariantList` statt `object` registriert. Qt konvertiert das kopierte Array
dadurch zu einer Python-Liste mit den enthaltenen Routendictionaries.
Die eigentliche Nachprüfungslogik und ihre Schutzmechanismen sind unverändert.

## Nachweise

- Der neue Test `test_mining_verification_qml.py` reproduzierte vor dem Fix
  exakt `Passing incompatible arguments to C++ functions from JavaScript`.
  Mit dem Fix besteht derselbe echte QML-Aufruf gegen den Produktionscontroller.
- 100 Routen erreichen die Prüfung vollständig: 101 deduplizierte Mine-/Sale-
  Powerplay-Ziele, unverändert maximal sechs gezielte Marktabfragen und keine
  zusätzlichen Ringabfragen für diese Powerplay-Routen.
- Commodity, Startsystem, Marktalter, Mindestnachfrage und Pad bleiben erhalten;
  ebenso verschachtelte Arrays und unbekannte (`null`) Werte in einer später
  vorgemerkten Suche. Die Zweiparameter-Überladung und leere Listen funktionieren.
- Der bestehende Test der echten MiningFinder-QML-Seite leitet den Aufruf jetzt
  an den Produktionscontroller weiter, statt ihn nur mit einer JavaScript-
  Funktion zu zählen. Er weist den Start des Hintergrundarbeiters nach und
  prüft weiterhin, dass regionale Synchronisierung zuerst abgeschlossen ist,
  Ergebnisse und Scrollposition stabil bleiben und keine Prüfschleife entsteht.
- Gesamte App-Testsuite: **1.126 Tests erfolgreich**, Laufzeit 117,596 Sekunden.
  Repository-Hygieneprüfung und `git diff --check` ebenfalls erfolgreich.

Die QML-Integrationstests verwenden isolierte Testkontexte und erfassen den
Arbeiterstart, ohne echte Serverabfragen oder Schreibzugriffe auf Nutzerdaten.
Ein neuer Live-Performancevergleich inklusive vollständiger Nachprüfung steht
noch aus; die ursprünglichen 1.5.40-Baseline-Zeiten sind dafür kein Nachweis.

## Auslieferungsumfang

Nur Client-Slotvertrag, Regressionstests und Dokumentation geändert.
Keine Änderung an Server, BGS-Prognosen, Ranking, Frischegrenzen oder Datenbestand.
Kein Serverdeploy erforderlich. Kein Push oder Release; die laufende App wurde
nicht neu gestartet.
