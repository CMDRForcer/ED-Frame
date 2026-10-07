# Community-Hauptschalter

ED-Frame und EDDN haben jeweils einen sofort gespeicherten Hauptschalter. ED-Frame bündelt Katalogabruf, Prospector-Erträge, öffentliche Journal-Signale und Stationspreise. EDDN bündelt Kontaktfreigabe, Upload und Live-Empfang. Die technischen Details und Datenschutzhinweise bleiben verfügbar.

Neue Profile ohne gespeicherte Auswahl starten auf ausdrücklichen Nutzerwunsch aktiviert. Eine bestehende explizite Abschaltung einer Teiloption führt beim Laden zur Abschaltung der gesamten Gruppe; keine heimliche erneute Freigabe. Einschalten in der Oberfläche aktiviert alle Teiloptionen, Ausschalten deaktiviert alle. Vorhandene lokale Daten werden nicht gelöscht. Bereits laufende Requests können beim Ausschalten noch auslaufen.

Keine Serveränderung und keine Änderung an übertragenen Feldern oder EDDN-Queues. Vier Sprachen ergänzt. 33 gezielte Profil-/Hauptschalter-/Signal-/UI-Tests bestanden. Der erste Gesamtlauf hatte ausschließlich eine alte Erwartung für neue Profile (EDDN aus); diese wurde an den gewünschten neuen Standard angepasst. Isolierter QML-Smoke im Gesamtlauf bestanden.

Noch nicht committed oder gepusht.

Abschließender vollständiger App-Lauf: 945 Tests grün, einschließlich echtem isoliertem QML-Smoke.
