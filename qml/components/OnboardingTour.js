.pragma library

// Membership uses stable IDs; titles, icons, page numbers and ordering come
// from Main's standard sidebar model. Unassigned future areas remain visible.
var groups = [
    {id: "planning", areas: ["operations", "engineering", "wishlist", "engineers"]},
    {id: "resources", areas: ["materials", "mining-finder", "state-finds"]},
    {id: "navigation", areas: ["shipyard", "nav"]},
    {id: "commander", areas: ["powerplay", "cmdr", "missions", "logbook", "exploration", "exobiology"]},
    {id: "setup", areas: ["settings"]}
]

function pages(navigation) {
    var assigned = {}
    var result = groups.map(function(group) {
        var entries = navigation.filter(function(entry) {
            if (group.areas.indexOf(entry.id) < 0 || assigned[entry.id]) return false
            assigned[entry.id] = true
            return true
        })
        return {id: group.id, entries: entries}
    })
    var remaining = navigation.filter(function(entry) {
        if (assigned[entry.id]) return false
        assigned[entry.id] = true
        return true
    })
    if (remaining.length) result.push({id: "other", entries: remaining})
    return result
}

function descriptionKey(id) {
    var known = groups.some(function(group) { return group.areas.indexOf(id) >= 0 })
    return known ? "onboarding.area." + id : "onboarding.area.other"
}
