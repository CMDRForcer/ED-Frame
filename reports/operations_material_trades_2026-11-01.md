# Operations: Materialtausch für den vollständigen Build

## Ursache

Die Materialtauschkarte hatte keine bevorzugte oder implizite Breite. Im
zweispaltigen Qt-Layout erhielt die Händlerroute dadurch praktisch den gesamten
Platz; die Tauschkarte war im reproduzierten Fall nur 3 Pixel breit. Zusätzlich
beschränkte der voreingestellte AUTO-Filter die Liste auf die Kategorie des
ersten Händlers.

## Lokale Korrektur

- Die Tauschkarte erhält eine eigene bevorzugte Breite und genügend Listenhöhe.
  Kleine Fenster zeigen die Karten weiterhin untereinander.
- ALLE ist die Voreinstellung. AUTO und die drei Materialkategorien bleiben als
  zusätzliche Filter verfügbar.
- Die Liste benennt ihren Geltungsbereich ausdrücklich als gesamten ausgewählten
  Build. Der Modul-/Experimental-Fokus von Next Best Action schränkt sie nicht ein.
- Jede Zeile zeigt getrennt Material und Menge zum Abgeben und Erhalten. Lange
  Namen werden umgebrochen. Unvermeidliche Überschüsse werden erklärt.
- Ein leerer Kategorienfilter verweist auf ALLE. Händler, Materialdetails und die
  vorhandene Sammelliste bleiben erhalten.
- Texte wurden in Deutsch, Englisch, Spanisch und Französisch ergänzt.

Die bestehende Tauschberechnung wurde nicht verändert: Sie verwendet nur Bestand
oberhalb der für den vollständigen Build reservierten Mengen. Bestätigte
Journal-Ereignisse aktualisieren weiterhin Bestand und Plan.

## Prüfung

- 30 gezielte Tests: Operations-Darstellung, Übersetzungen, UI-Konventionen und
  Prioritätsplanung bestanden.
- 125 weitere Tests: aktualisierte Qt-Regression, allgemeine Qt-Darstellung und
  Interaktionen, Release-Verträge und Materialmonitor bestanden.
- Qt-Darstellung mit synthetischen Daten bei 1920 × 1080 (Englisch) und
  1120 × 700 (Deutsch) visuell geprüft. Alle drei Kategorien erscheinen; Mengen,
  Textumbruch, Kategorienwechsel und eine verkürzte Liste nach Modelländerung
  sind zusätzlich automatisch geprüft.
- Keine echten Materialien getauscht und kein Servereingriff. Zunächst lokal
  geprüft; die Korrektur ist Bestandteil von App 1.0.13. Beim Quellstand genügt
  ein vollständiger Neustart der App.
