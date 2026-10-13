# ED-Frame: lokales Onboarding, 13.10.2026

Das bisherige Begrüßungsfenster wurde durch neun Seiten ersetzt: Willkommen,
Journal, Verbindungen, Darstellung und fünf Tour-Seiten. Alle 16 tatsächlichen
Sidebar-Bereiche erscheinen genau einmal, mit ihren Sidebar-Namen und
Piktogrammen. Unbekannte zukünftige Bereiche werden automatisch unter
„Weitere Bereiche“ ergänzt.

Überspringen und Esc schließen die Einführung sofort ab. Änderungen bleiben
gespeichert. Zurück/Weiter, Abschluss und direkte Bereichssprünge funktionieren.
Die Darstellung folgt der UI-Skalierung; lange Seiten haben eine Scrollbar,
während die Bedienknöpfe sichtbar bleiben. Die Nutzungszählung ist ausschließlich
ein deaktivierter Platzhalter. Bereits abgeschlossene Profile erhalten beim
Versionsstand 1 keine neue Einführung; ein künftiges bewusstes Erhöhen von
ONBOARDING_VERSION kann sie erneut anbieten. Der Preview-Schalter bleibt erhalten.

Geänderte bzw. neue Quelldateien:

- `Main.qml`: kurze Wizard-Anbindung; Einstellungsänderungen öffnen einen bereits
  sichtbaren Wizard nicht erneut. Insgesamt 108 Zeilen weniger.
- `qml/components/OnboardingWizard.qml`: Oberfläche und Bedienung.
- `qml/components/OnboardingTour.js`: Gruppierung aus der Standard-Sidebar,
  Reihenfolge und Auffangseite.
- `qml/components/CockpitDialog.qml`: vorhandenen Dialogstil aus Main ausgelagert.
- `ed_companion/phase14/onboarding.py`: Versions- und Migrationsregel.
- `ed_companion/phase14/controller.py`: Profilinitialisierung.
- `ed_companion/phase14/controller_ui_settings.py`: Versionsspeicherung und
  Adapter vom Ordnerdialog auf die vorhandene Journal-Pfadlogik.
- `ed_data/i18n/en.json`, `de.json`, `es.json`, `fr.json`: 66 neue übersetzte Keys,
  korrigierte alte Onboarding-Texte und passende Settings-Bezeichnungen.
- `qml/pages/TradeRoutesSection.qml`: beim Bereichswechsel entdeckten verzögerten
  Einstellungsaufruf korrigiert; nach dem Entladen wird nicht mehr auf die
  zerstörte Handelsrouten-Seite zugegriffen.
- `tests/test_onboarding.py`: Versions-, Übersetzungs- und echte QML-Tests.

Bestandene Prüfungen:

- 114 Tests aus `tests.test_onboarding`, `tests.test_i18n`,
  `tests.test_persistence_save_results` und `tests.test_release_contracts`.
- Wizard: alle neun Seiten in allen sechs Themes; zusätzlich vier Sprachen bei
  100, 115 und 150 Prozent in einem schmalen Fenster. Insgesamt 162 Seitenprüfungen,
  einschließlich Textumbrüchen, Scrollbarkeit und tatsächlichen Fenstergrenzen.
- Überspringen auf Seite 1, Seite 3 und mitten in der Tour; Esc; Tab und Leertaste;
  erhaltene Sprache, Theme, Journal-Automatik und Verbindungseinstellungen.
- Alle Sidebar-Bereiche einmalig und in ihrer Standardreihenfolge pro Gruppe;
  Auffangseite für neue Bereiche; alle 16 Öffnen-Buttons mit richtigem Seitenziel.
- Abgeschlossene alte Profile und Preview-Skip öffnen keinen Wizard.
- Zwei vollständige Offline-App-Smokes: synchrone und asynchrone Seitenlader,
  je 33 Prüfpunkte, ohne QML-Laufzeitfehler.
- `git diff --check` ohne Fehler.

Tests nutzten temporäre Profile und blockierte HTTP-Verbindungen. Produktive
Profile wurden nicht geändert. Vorhandene lokale Serveränderungen bleiben wie
vorgefunden. Kein Commit, Push, Tag, Release oder Deploy wurde vorgenommen.

Für deinen manuellen Test die laufende App schließen und `phase14_main.py` aus
diesem Projekt mit `.venv/Scripts/python.exe` starten. Unter Einstellungen →
„EINFÜHRUNG ÖFFNEN“ vor allem den echten Windows-Ordnerdialog, Scrollen mit Maus
bzw. Touchpad, Tab/Esc und die Darstellung bei deiner üblichen Skalierung prüfen.
Der native Ordnerdialog selbst wurde nicht durch einen Bildschirmtest bedient;
seine Anbindung an die vorhandene Pfadlogik ist automatisiert geprüft.

Vorschaubilder und Testprotokolle liegen lokal unter `outputs/onboarding-*`.
