import QtQuick

ListView {
    id: view
    property var sourceRows: []
    property int queryRevision: 0
    property int previousQueryRevision: -1
    property var keyForRow: function(row) { return String(row.system || "") + "|" + String(row.ring || "") }
    model: ListModel { id: routeModel; objectName: "qa-stable-mining-route-model"; dynamicRoles: true }

    function updateRows() {
        forceLayout()
        const sameQuery = previousQueryRevision === queryRevision
        const oldY = contentY
        let anchor = ""
        let offset = 0
        if (sameQuery) {
            for (let i = 0; i < count; ++i) {
                const item = itemAtIndex(i)
                if (item && item.y + item.height > contentY) {
                    anchor = routeModel.get(i).routeKey
                    offset = contentY - item.y
                    break
                }
            }
        }
        const rows = sourceRows || []
        // Update/move only changed records. Never clear a populated model for
        // a same-query refresh, so delegates, selection and viewport survive.
        for (let i = 0; i < rows.length; ++i) {
            const row = rows[i]
            const key = String(keyForRow(row))
            const signature = JSON.stringify(row)
            let existing = i
            while (existing < routeModel.count
                   && routeModel.get(existing).routeKey !== key)
                ++existing
            if (existing === routeModel.count) {
                routeModel.insert(i, {routeKey: key, route: row,
                                  verificationGroupLabel: String(row.verificationGroupLabel || ""),
                                  rowSignature: signature})
            } else {
                if (existing !== i) routeModel.move(existing, i, 1)
                if (routeModel.get(i).rowSignature !== signature)
                    routeModel.set(i, {routeKey: key, route: row,
                                      verificationGroupLabel: String(row.verificationGroupLabel || ""),
                                      rowSignature: signature})
            }
        }
        if (routeModel.count > rows.length)
            routeModel.remove(rows.length, routeModel.count - rows.length)
        forceLayout()
        let restored = sameQuery ? oldY : originY
        if (sameQuery && anchor) {
            for (let i = 0; i < count; ++i) {
                if (routeModel.get(i).routeKey === anchor) {
                    positionViewAtIndex(i, ListView.Beginning)
                    forceLayout()
                    const item = itemAtIndex(i)
                    if (item) restored = item.y + offset
                    break
                }
            }
        }
        contentY = Math.max(originY, Math.min(restored,
                            originY + Math.max(0, contentHeight - height)))
        previousQueryRevision = queryRevision
    }
    onSourceRowsChanged: Qt.callLater(updateRows)
    onQueryRevisionChanged: Qt.callLater(updateRows)
}
