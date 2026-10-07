# UI-Vereinheitlichung – 7. Oktober 2026

## Umfang

Erster gemeinsamer Durchgang, keine vollständige Neugestaltung aller Seiten.
Suchlogik, Quellen, Filterwerte, Request-Budgets und Persistenz bleiben unverändert.

- `qml/components/UiMetrics.js`: gemeinsame Caption-/Body-Größen (11/13 px),
  Standardhöhe 42 px, Kontrollradius 8 px.
- `CockpitComboBox.qml`, `StatusBadge.qml`, `WorkspaceHeader.qml`:
  lesbarere Texte; Headerhöhe folgt dem Inhalt, Untertitel darf umbrechen.
- `Main.qml`: gemeinsame Cockpit-Schaltflächen verwenden dieselben Text-/Höhenwerte.
- Shipyard, Mining, Powerplay, Exploration, Exobiology: 136 bisherige feste
  7–10-px-Schriftdeklarationen auf gemeinsame 11-px-Captions angehoben.
- Shipyard: Kategorien umbrechen, Slot-Spalte hat eine flexible Breite;
  gemeinsame Schaltflächenmaße.
- Mining: Filterbereich wird intern vertikal gescrollt und abgeschnitten,
  damit Text nicht in die darunterliegende Statuszeile hineinläuft.

## Verifikation

- Vollständige bestehende Regression: 919 Tests erfolgreich (vor dem letzten
  ScrollView-/Schaltflächen-Feinschliff).
- QML-Verträge danach: 16 Tests erfolgreich.
- Neue Präsentationsverträge: 3 Tests erfolgreich.
- Echter QML-App-Smoke mit temporärem Profil: PASS, Exit-Code 0,
  alle 18 Seiten sowie zusätzliche Dialog-/Interaktionsprüfungen.
- Offscreen-Sichtprüfung mit Testdaten bei 1480 und 1120 px Fensterbreite.
  Kein Zugriff auf das laufende Benutzerprofil. Vorschaufonts teilweise
  explizit geladen; damit kein pixelgenauer Beleg für jeden Windows-Rechner.
- Kein Commit, Push oder Server-Deployment.

## Noch nicht Teil dieses Durchgangs

Mining-Presets, Ergebnis-Ranking, Best-Station-Ansicht, neue Modulbilder,
vollständige Umstellung aller älteren Inline-Seiten und sämtliche Spracheinstellungen.

## Zweiter Durchgang

- Operations, Wishlist und Engineering auf WorkspaceHeader umgestellt.
- Wishlist: Schiffsauswahl und Aktionen stehen in einer separaten Layoutzeile.
- Engineering: Import/Export und Suchfeld in einer Layoutzeile; keine festen
  Suchfeld-Anker mehr. Bestehende Suchzustände und Aktionen bleiben erhalten.
- SettingsHeader folgt der tatsächlichen Höhe des gemeinsamen Headers.
- 97 kleine Caption-Deklarationen in Operations, Wishlist, Engineering,
  CMDR-Übersicht und Fleet auf gemeinsame 11 px angeglichen. Finanzchart
  bewusst nicht pauschal vergrößert.
- Operations: starre Mindestbreiten im Next-Best-Action-Panel reduziert.
  Keine Änderung seiner fachlichen Logik oder Materialberechnung.

Verifikation: 925 Tests erfolgreich, kompletter QML-Smoke erfolgreich,
zusätzliche isolierte Vorschau auf Deutsch bei 1120 px Fensterbreite.
Kein Zugriff auf das Benutzerprofil; simulierte Daten/Offscreen-Rendering.

Weiter offen: dichter Aufbau der unteren Operations-Karten bei kleinen
Fenstern; Finanzchart-/Ticker-Typografie; verbliebene Legacy-Dialoge und
Materials/Engineers/Logbook; gemischte deutsche/englische Statusbegriffe und
vollständiger Abgleich der Statusfarben. Das ist keine Zusicherung, dass
jeder Inhalt in jedem Skalierungsfaktor bereits visuell geprüft wurde.
Kein Commit oder Push.

## Dritter Durchgang

- Operations hat nun einen vertikalen Seiten-Scrollbereich. Material- und
  Händlerkarten stehen im schmalen Layout untereinander, ansonsten nebeneinander.
  Mindesthöhe je Karte 320 px, keine Mindestbreite von 500/650 px mehr.
- Scrollreichweite wirklich geprüft: Inhalt 1228 px, Viewport ca. 747 px;
  beide unteren Karten sind erreichbar. Screenshot `ui-round3-operations-bottom.png`.
- Materials und Engineers verwenden den gemeinsamen WorkspaceHeader und
  layoutgesteuerte Suchfelder statt fester Kopfbereich-Anker.
- Kleine Beschriftungen in Materials/Engineers und Logbook angeglichen.
- Logbook-Suche erhält dieselben Höhe/Schrift/Abstände/Rundung wie die anderen
  Suchfelder. Lange Sitzungskennzahlen werden begrenzt, voller Text per Tooltip.
- Gemeinsame EmptyState-Texte umbrechen innerhalb der verfügbaren Breite.

927 Regressionstests erfolgreich vor dem letzten Logbook-Tooltip-/Suchfeld-
Feinschliff. Zusätzliche deutsche Offscreen-Prüfung bei 1120 px. Keine
Such-, Allokations-, Ranking- oder Datenaktualitätslogik geändert.

Noch offen: Finanzdiagramm-/Ticker-Schriften, verbleibende Dialoge sowie
durchgängige Übersetzung und Statusfarb-Semantik. Keine pauschale Aussage
über alle DPI-Skalierungen oder jede datenreiche Benutzerkonstellation.

## Vierter Durchgang: verbleibende Darstellung und Texte

- Main.qml: verbliebene 7–10-px-Captions in Dialogen, Einstellungen,
  Verbindungsübersicht, Diagnostik und Finanzansicht auf UiMetrics.caption
  umgestellt. Dialogtitel sind auf die verfügbare Breite begrenzt.
- Finanzansicht: Achsen und Canvas-Beschriftungen ebenfalls 11 px; mehr
  Platz für Achsen, Skala und Detailboxen. Legende steht separat, der Zeitraum
  hat einen Tooltip. Kennzahlenkarten 76 px hoch. Finanzinhalt scrollt bei
  Platzmangel; Chart mindestens 320 px hoch. Verlauf, Achsenwerte, Hover-
  Auswahl und Finanzberechnungen wurden nicht verändert.
- MissionsPage, NavPage und MaterialFarmsSection: verbleibende kleine
  Captions auf dieselbe Metrik angeglichen.
- 226 fehlende statische UI-Schlüssel in allen vier Sprachkatalogen ergänzt
  (EN/DE/ES/FR). Zusätzlich 34 Darstellungslabels für Zugang, Erwerb,
  Preisstufen und Modulgruppen. PresentationLabels.js übersetzt ausschließlich
  Anzeigetext; originale Modell-, Filter- und Auswahlwerte bleiben erhalten.
- Shipyard: Sperrfarben folgen dem Theme-Fehlerfarbwert; lokalisierte
  Gruppenschaltflächen passen ihre Breite an den Text an. Waren- und
  Stationsservice-Schaltflächen verwenden den Theme-Hintergrund für Kontrast.
- Verbindungsstatus: deaktiviert gedämpft, laufende Prüfung/Abgleich gelb,
  online grün; bestehende Kriterien dafür unverändert. Fachliche Verified-
  und Sperrbedingungen wurden nicht geändert.

### Verifikation und Grenzen

- 932 Regressionstests erfolgreich im vollständigen Durchlauf; darin
  enthalten ist der echte Main.qml-Smoke mit temporärem Benutzerprofil.
- Zusätzliche Finanzvorschau mit echtem QML und ausdrücklich simulierten
  Zahlen: Deutsch bei 1920 und 1120 px, jeweils PASS und Exit-Code 0.
  Scrollende separat gerendert: 74 bzw. 278 px Scrollreichweite, Chart und
  erklärender Text erreichbar. Screenshots ui-final-finance-wide.png und
  ui-final-finance-narrow-bottom.png (sowie weitere Top/Bottom-Varianten).
- 11 Präsentationsverträge grün; Übersetzungsschlüssel und unveränderte
  Domainwerte werden zusätzlich geprüft. Ein älterer Vertrag verlangte
  exakt 72 px Achsenrand; auf den neuen 90-px-Rand angepasst, die Bedingung
  für nachgewiesene Vermögenswerte bleibt im Test erhalten.
- Erster lokaler Testversuch scheiterte am Sandbox-Tempordner; erfolgreicher
  Wiederholungslauf mit freigegebenem Zugriff. Keine Produktionsdaten geändert.
- Sichtprüfung nicht gegen das laufende Benutzerprofil. Fonts wurden für
  Offscreen explizit geladen; Symbolfont im Test nicht vollständig vorhanden.
  Kein Nachweis für jede DPI-Skalierung oder jede denkbare Datenmenge.
- Dynamische freie Journal-/Servertexte und fachliche Modulnamen werden
  nicht pauschal umgeschrieben. Separate skalierte Ingame-Overlays wurden
  nicht auf neue Schriftgrößen gezwungen.
- Keine Backend-, Datenfluss-, Freshness- oder Serveränderung in diesem
  Durchgang. Kein Commit, Push oder Deployment.
