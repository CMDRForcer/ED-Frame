# Engineers: Loader-Diagnose korrigiert — 8. Oktober 2026

## Befund

Der zuvor gemeldete `Cannot create delegate`-Fehler ließ sich beim Verlassen
der Engineers-Seite reproduzieren. Qt 6.11.2 gab unmittelbar nacheinander aus:

```text
Main.qml:4474: QML Loader (parent or ancestor of Component): Cannot create delegate
Main.qml: Object or context destroyed during incubation
```

Ein Rohmeldungs-Trace über 75 schnelle Wechselzyklen zeigte sechs solcher
Paare. Auch der vollständige Seiten-Smoke-Test reproduzierte ein Paar beim
Wechsel von Engineers zu Settings. Die einzelnen Seitenprüfungen waren grün;
die Diagnose wertete dennoch die erste Meldung als Laufzeitfehler.

Der vorhandene Filter erkannte nur die ältere Schreibweise
`QML Component: Cannot create delegate`. Qt bezeichnet hier stattdessen den
Loader als Vorfahren der anonymen Component. Das Meldungspaar entsteht beim
Abbruch noch laufender Delegate-Erzeugung während des Seitenabbaus. In diesem
Fall wurde kein bleibend defektes Engineers-Modell nachgewiesen.

Zum Lebenszyklus: Ein deaktivierter Loader gibt sein geladenes Objekt frei;
asynchrones Laden verteilt die Erzeugung über mehrere Frames.
[Qt-Loader-Dokumentation](https://doc.qt.io/qt-6/qml-qtquick-loader.html#active-prop).

## Änderungen

- Diagnose erkennt die exakte Component- und Loader-Vorfahren-Schreibweise.
- Live-Filter akzeptiert nur unmittelbar aufeinanderfolgende Paare aus
  derselben QML-Datei innerhalb von 50 ms, in beiden Reihenfolgen.
- Ein Abbruch kann höchstens einen Erzeugungsfehler erklären. Die frühere
  globale Ein-Sekunden-Schonfrist entfällt.
- Unverbundene, verspätete oder aus einer anderen QML-Datei stammende
  Erzeugungsfehler bleiben sichtbar und lassen Tests scheitern.
- Verzögerte Diagnosen kopieren Dateiname und Zeile aus dem kurzlebigen
  Qt-Kontext. Ein älterer Timer kann keine neuere Meldung vorzeitig ausgeben.
- Der vollständige synchrone QML-Smoke-Test hat keinen Wiederholungsversuch
  mehr. Ein einziger fehlgeschlagener Durchlauf ist wieder ein Testfehler.
- Neuer realer Wechseltest prüft Übersicht, Unlock Guide und Tech Brokers:
  jeweils 75 Zyklen mit synchronen und produktionsnahen asynchronen Loadern.
  Er verlangt vorhandene Listeneinträge und ein tatsächlich erzeugtes
  `currentItem`, nicht lediglich die Sichtbarkeit der Seite.
- Der Wechseltest wartet separat auf die Veröffentlichung des initialen
  Hintergrundzustands. Der leichtgewichtige Erstzustand hat absichtlich noch
  keinen Tech-Broker-Guide; dies ist nicht mit einem Delegate-Fehler gleichzusetzen.

## Abgrenzung

Keine Änderungen an BGS-Prognosen, Spiel- oder Ingenieursberechnungen,
Serverdaten oder vorhandenen Profildateien. Kein Server-Deployment und kein
Commit, Push oder App-Release in diesem Durchgang. Eine installierte ältere
EXE enthält diese Quellcodeänderungen noch nicht.

## Prüfung

- Gezielter Lauf: **15 Tests grün** in 120,1 Sekunden, einschließlich
  Diagnose-Sicherheitsfällen und realen QML-Seitenprüfungen.
- Wechsel-Stresstest: **600 Aktionen** (75 vollständige Zyklen pro Loader-Art),
  alle geprüften Listen mit erzeugtem Eintrag wiederhergestellt.
- Vollständiger App-Testlauf: **1.125 Tests grün** in 134,3 Sekunden, ohne
  globalen `PHASE14_SMOKE_ASYNC_PAGES`-Ausweichmodus. Der synchrone und der
  produktionsnahe asynchrone QML-Smoke-Test bestanden jeweils ohne Wiederholung.
- Absichtlich injizierter QML-Laufzeitfehler: weiterhin erkannt; der zugehörige
  negative Test verlangt einen fehlgeschlagenen Smoke-Report und Exit-Code.
- Unverbundene Fehler, fremde Quelldateien, verspätete Paare, doppelte Fehler,
  veraltete Timer und kurzlebige Qt-Kontexte sind separat abgesichert.
- `git diff --check`: erfolgreich.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p 'test_*.py'
```

Die QML-Unterprozesse verwenden `offscreen` und jeweils ein temporäres
`LOCALAPPDATA` mit eigenem Single-Instance-Namen. Die installierte App und ihr
Benutzerprofil werden dadurch nicht übernommen oder umgeschaltet.
