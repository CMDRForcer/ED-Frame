# Rare Goods – ALL

- Rare-Goods-Warenauswahl bietet ALL plus einzelne Waren.
- Ein einziger Gruppenrequest mit maximal 200 Symbolen; weiterhin 100 Ergebnisse
  je Suche und sichtbarer Hinweis bei weiteren Treffern. Kein Fan-out je Ware.
- Bestehende Radius-, Preisrichtung-, Mindestbestand-, Alter-, Pad- und
  Carrierfilter gelten weiter. Angebote tragen den Warennamen zur Unterscheidung.
- Der Client bestätigt Gruppe und Region und verwirft fremde/nicht-seltene Ware.
- Nur API aktualisiert, keine Migration/DB-Löschung, Collector unverändert.
  Vorherige API und Image gesichert unter
  `/opt/edframe-deploy-backups/rare-goods-all-20261007` bzw.
  `edframe-catalog-api:before-rare-goods-all-20261007`.
- 13 Clienttests, 3 APItests und isolierte breite/schmale QML-Vorschau bestanden.
- Echtprüfung: /healthz HTTP 200; ALL für 142 seltene Warensymbole,
  BUY um Sol, 500 LY, 168 h: 84 Angebote, hasMore=false.
  Diese Suchparameter sind Testwerte, nicht neue App-Defaults.
- Kein Commit/Push. Lokal heruntergeladene API-Vergleichskopie nach Prüfung
  entfernt; die wiederherstellbare Server-Sicherung bleibt erhalten.
