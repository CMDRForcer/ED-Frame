# Unbegrenzte Warensuche · 11.10.2026

## Lokal umgesetzt

Der Suchradius bietet zusätzlich **1.000 LY, 2.000 LY und UNBEGRENZT**. Die bestehenden Auswahlwerte bleiben erhalten; voreingestellt sind weiterhin 100 LY. Beschriftung und Erklärung der unbegrenzten Suche sind auf Deutsch, Englisch, Französisch und Spanisch vorhanden.

„Unbegrenzt“ durchsucht die gespeicherten Märkte mit bekannten Systempositionen ohne Entfernungsfilter. Entfernung und Ausgangspunkt bleiben für die Anzeige und die Reihenfolge bei gleichem Preis erhalten. Preis, Bestand beziehungsweise Nachfrage, Datenalter, Landeplattform und der gewählte Carrier-Filter gelten weiter. Die App zeigt maximal 100 Angebote, sortiert nach Preis; weitere Treffer werden gekennzeichnet. Das gilt auch für die Sammelsuche nach seltenen Waren.

Die Anfrage läuft ausschließlich nach einem Klick im vorhandenen Netzwerk-Worker. Es gibt keine zusätzlichen automatischen Abfragen und keinen Download des gesamten Marktbestands. Globale Serverabfragen verwenden eine lesende Transaktion mit zehn Sekunden SQL-Zeitlimit und zwei Sekunden Sperrzeitlimit. Bei einem Fehler bleiben die vorherigen Ergebnisse erhalten. Ein Orts- oder Profilwechsel verhindert weiterhin, dass eine alte Antwort als aktuelle Suche übernommen wird.

## App und Server

Die API verwendet `max_distance=0` für die unbegrenzte Suche und bestätigt `region.radiusLy: null`. Positive Radien behalten ihren bisherigen Vertrag. Der Client akzeptiert keine kleinere Region als Antwort auf eine globale Suche. Ein alter Server liefert bei Radius 0 HTTP 422; die App erklärt, dass ein Server-Update erforderlich ist, und empfiehlt einen begrenzten Radius.

**Der produktive Server wurde nicht geändert. Die neue Option wird dort erst nach Einspielen der vorbereiteten API-Änderung nutzbar.** Dazu ist keine Datenbankmigration nötig. Alle lokalen Änderungen einschließlich der vorherigen Carrier-, Start- und UI-Verbesserungen bleiben erhalten.

## Prüfung

Gezielte Tests prüfen sehr weit entfernte Angebote, Datenqualität, seltene Waren, Auswahlwerte, Serverbestätigung, alte Server und Ortswechsel. Die HTTP-Vertragstests führen echte Parameterprüfung und JSON-Ausgabe der lokalen API bis zum App-Parser aus, mit synthetischen Datenbankantworten. SQL-Prüfungen sichern Filter, Preisreihenfolge, Zeitlimits und Ergebnisbegrenzung. Eine Laufzeitmessung der globalen Abfrage am produktiven Marktbestand steht aus.

Alle **1.381 App-Tests** und **176 Servertests** bestehen. Die portable EXE besteht zusätzlich **35 Funktionsprüfungen** einschließlich separater Hintergrundprozesse. Die eingefrorene Warenlogik und der Controller wurden direkt aus der EXE mit einer 90.000-LY-Antwort geprüft; gebündelte QML- und Sprachdateien stimmen mit dem Quellstand überein. Prüfungen auf private Daten und unerwünschte Laufzeitdateien bestehen.

Die deutsche Ansicht ist bei 1280 × 800 und 650 × 850 geprüft; die Erklärungen für globale Suche und ausgeschlossene Carrier bleiben vollständig sichtbar. Die Qt-Regression prüft Auswahl und Anfragewerte außerdem in der echten Hauptansicht auf Deutsch, Englisch und Französisch.

Testversion: `output/ED-Frame-Unlimited-Test-20261011-Windows/ED-Frame/ED-Frame.exe`. Bisherige App einschließlich Tray vollständig beenden, dann diese EXE starten. Begrenzte Radien funktionieren am bisherigen Server; für „Unbegrenzt“ ist das oben beschriebene API-Update erforderlich. Den gesamten portablen Ordner zusammenlassen. Versionsnummer weiterhin 1.0.8, da keine Veröffentlichung erfolgt.

Kein Commit, Push, Release oder Server-Deployment. Die laufende App wurde nicht ersetzt.
