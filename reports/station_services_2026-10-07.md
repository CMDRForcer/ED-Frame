# Stationsdienste-Finder

## Fertig

NAV hat einen Unterbereich STATION SERVICES; Operations enthält einen direkten
Einstieg. Surface Nav, Wegpunkte und Material-Farms bleiben unverändert.
Die Suche nutzt ausschließlich unsere öffentliche Server-API, ohne Fremddatenbank-
Fallback, automatische Abfrageschleifen oder Änderungen an Planern/Queues.

Zwölf Dienste: Reparatur, Auftanken, Aufmunitionieren, Interstellar Factors,
Warenmarkt, Ausrüstung, Schiffswerft, Materialhändler, Techbroker,
Universal Cartographics, Vista Genomics und Schwarzmarkt.

Radius 25/50/100/250/500 LY; benötigter Pad S/M/L oder beliebig.
M akzeptiert auch L, S auch M/L; unbekannte Pads gelten nicht als passend.
Carrier sind standardmäßig ausgeschlossen. Bei eingeschlossenen Carriern steht
ein ausdrücklicher Hinweis, dass der Andockzugang zu prüfen ist.

Sortierung: Systementfernung LY, dann Anflugstrecke LS, dann MarketID.
Maximal 100 nächstgelegene Treffer pro Suche; zusätzliche Treffer werden als
Begrenzung genannt. Station/System, LY/LS, Pad, Typ, Datenalter und Quelle werden
angezeigt; Systemname ist kopierbar.

Die bestehende Permit-/Rangauswertung wird wiederverwendet und liest den aktuellen
Commander-Zustand. Unbekannter Zugang ist keine Freigabe, fehlender Nachweis nicht
automatisch eine Sperre. Bekannte gesperrte Zugänge sind rot markiert. Die vorhandene
Permit-Regeltabelle ist kein vollständiger Katalog sämtlicher Zugangsbeschränkungen.
Verfügbarkeit eines Dienstes kann sich nach der Beobachtung ändern; alte Daten werden
sichtbar gekennzeichnet, nicht gelöscht.

Materialhändler-/Techbroker-Untertypen bleiben ausdrücklich unbekannt. Bestehende
typisierte Suchfunktionen werden deshalb nicht ersetzt.

Die Service-IDs stammen aus realen StationServices im eigenen API-Bestand.
`facilitator` wurde zusätzlich anhand der EDDI-Definition als Interstellar Factors
verifiziert: [EDDI StationService.resx](https://github.com/EDCD/EDDI/blob/develop/DataDefinitions/Properties/StationService.resx).

## Ausführung und Schutz

Netzwerk läuft im vorhandenen Worker-Mechanismus, nur nach Suchklick.
Keine Journal-Identität wird übertragen, nur öffentliche Standort-/Suchparameter.
Bei Fehlern, deaktiviertem Server oder fehlender Position bleiben vorherige
Suchtreffer innerhalb derselben App-Sitzung erhalten und werden als vorherige
Suche kenntlich. Nach Neustart gibt es bewusst noch keinen persistenten Offline-
Stationsdienste-Cache. Profil-/Standortwechsel verwerfen alte Antworten; die
Zugangshinweise eines anderen Commanders werden nicht weiter angezeigt.

## Live-Prüfung

07.10.2026 09:22 UTC, FAUST 3725, 100 LY, benötigtes M-Pad, ohne Carrier:

| Dienst | Treffer | Weiterer Bestand vorhanden |
|---|---:|---|
| Reparatur, Auftanken, Aufmunitionieren | je 100 | ja |
| Interstellar Factors | 100 | ja |
| Warenmarkt, Ausrüstung, Schiffswerft | je 100 | ja |
| Materialhändler | 100 | ja |
| Techbroker | 45 | nein |
| Universal Cartographics, Vista Genomics, Schwarzmarkt | je 100 | ja |

Abfragen inklusive Clientvalidierung: 0,55–0,78 s je Dienst.
Beispiel Reparatur: Wul Port / HIP 64059, L-Pad, 12,42 LY, 235,18 LS;
Stationsmetadaten etwa 35,4 h alt. Beispiel Interstellar Factors:
Brosnatch Enterprise / BD+38 2457, M-Pad, 20,95 LY, 6,44 LS;
Stationsmetadaten etwa 73,6 h alt. Das sind beobachtete Katalogangebote,
keine manuell getesteten Andock-/Dienstnutzungen. Health HTTP 200.

## Tests / Deployment

- 908 App-Tests grün einschließlich echter Main.qml-Smoke-Tests.
- 55 Server-Tests grün, elf neue Client-/Controller- und zwei neue API-Verträge.
- Separater QML-Smoke nach Styling: drei Tests grün.
- Qt-Komponente mit Beispieldaten bei 1100 und 650 px gerendert und geprüft.
  Keine manuelle Ingame-Prüfung; Vorschaubilder enthalten Beispieldaten.
- Nur API neu gebaut/gestartet, keine DB-Migration. DB, Collector, Caddy unverändert.
- Rückfallquelle: /opt/edframe-deploy-backups/station-services-20261007/api-before.tar.gz
- Rückfallimage: edframe-catalog-api:before-station-services-20261007.

Dateien: server/catalog_service/edframe_catalog/api.py, README.md;
navigation/station_services.py; phase14/controller_station_services.py,
controller.py; qml/pages/StationServicesSection.qml, NavPage.qml; Main.qml;
vier Übersetzungskataloge; zwei neue Testdateien.

App-Neustart erforderlich. Kein Commit/Push/Release in diesem Schritt.
