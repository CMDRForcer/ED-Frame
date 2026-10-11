.pragma library

// Original ED-Frame pictograms on a shared 24-unit grid. No icon font,
// remote asset, shader or additional Qt module is required.
var paths = {
    "operations": '<path d="M3 10 12 3l9 7v10H3Z M8 20v-7h8v7"/>',
    "engineering": '<path d="m4 20 9-9 M14 4a6 6 0 0 0-4 9l-7 7 3 1 7-7a6 6 0 0 0 8-7l-4 4-4-4 4-4Z"/>',
    "wishlist": '<path d="M6 5h12v16H6Z M9 3h6v4H9Z m0 9 2 2 4-4 M9 18h6"/>',
    "engineers": '<circle cx="12" cy="7" r="3"/><path d="M5 21v-3a7 7 0 0 1 14 0v3 M9 16l3 3 3-3"/>',
    "materials": '<path d="m12 3 9 5-9 5-9-5Z m-9 10 9 5 9-5 M3 18l9 5 9-5"/>',
    "mining-finder": '<path d="M4 6c5-3 11-1 16 4 M11 5l4 3-9 13-3-2Z M16 8l5 4"/>',
    "shipyard": '<path d="M8 5h8v4l5 5-9 7-9-7 5-5Z M5 13h14 M12 3v6 M12 13v8"/>',
    "state-finds": '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v4 M12 19v4 M1 12h4 M19 12h4 m-7-7 4-4"/>',
    "powerplay": '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z m1 4-4 6h4l-2 4 5-7h-4Z"/>',
    "cmdr": '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/>',
    "logbook": '<path d="M4 4h7l2 2h7v15h-7l-2-2H4Z M12 6v13 M7 8h2 M7 12h2 M15 10h2 M15 14h2"/>',
    "exploration": '<circle cx="12" cy="12" r="9"/><path d="m16 7-3 7-6 3 3-7Z"/>',
    "exobiology": '<path d="M7 3c0 7 10 11 10 18 M17 3c0 7-10 11-10 18 M8 4h8 M8 8h8 M8 16h8 M8 20h8"/>',
    "missions": '<path d="M5 3h14v18H5Z m3 6 1 1 2-2 M13 9h3 m-8 6 1 1 2-2 M13 15h3"/>',
    "nav": '<path d="m12 3 9 18-9-5-9 5Z M12 3v13"/>',
    "settings": '<circle cx="12" cy="12" r="4"/><path d="M9 2h6l1 3 3 1 3 3-2 2v2l2 2-3 3-3 1-1 3H9l-1-3-3-1-3-3 2-2v-2L2 9l3-3 3-1Z"/>',
    "connections": '<rect x="3" y="3" width="18" height="7" rx="2"/><rect x="3" y="14" width="18" height="7" rx="2"/><path d="M7 6h1 M7 17h1 M12 10v4"/>',
    "diagnostics": '<path d="M2 12h4l3-8 5 16 3-8h5"/>',
    "trade": '<path d="M4 6h16l-4-4 M20 18H4l4 4 M20 6l-4 4 M4 18l4-4"/>',
    "goods": '<path d="m12 3 9 5v9l-9 5-9-5V8Z M3 8l9 5 9-5 M12 13v9 M8 5l9 5"/>',
    "station": '<path d="M4 21V7h6V3h10v18Z M8 21v-5h8v5 M6 10h1 M6 13h1 M13 7h1 M17 7h1 M13 11h1 M17 11h1"/>',
    "market": '<path d="M3 5h2l3 11h11l2-8H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
    "credits": '<ellipse cx="9" cy="6" rx="6" ry="3"/><path d="M3 6v5c0 4 12 4 12 0V6 M3 11v5c0 3 5 4 9 3"/><circle cx="17" cy="17" r="5"/><path d="M17 14v6 M15 16h4"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v7c0 4 16 4 16 0V5 M4 12v7c0 4 16 4 16 0v-7"/>',
    "refresh": '<path d="M20 8a8 8 0 0 0-14-3L3 8 M3 3v5h5 M4 16a8 8 0 0 0 14 3l3-3 M16 16h5v5"/>',
    "search": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M5 16H3V3h13v2"/>',
    "pin": '<path d="M19 10c0 5-7 12-7 12S5 15 5 10a7 7 0 0 1 14 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
    "check": '<path d="m5 12 5 5L20 7"/>',
    "warning": '<path d="m12 3 10 18H2Z M12 9v5 M12 17v1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6 M12 7v1"/>',
    "chevron": '<path d="m6 9 6 6 6-6"/>',
    "heart": '<path d="M12 21 3 12C-2 5 7 0 12 7c5-7 14-2 9 5Z"/>'
}

function svg(name, tint) {
    var rgb = [tint.r, tint.g, tint.b].map(function(value) {
        return Math.round(value * 255).toString(16).padStart(2, "0")
    }).join("")
    return "data:image/svg+xml;utf8," + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#'
        + rgb + '" stroke-opacity="' + tint.a + '" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
        + (paths[name] || paths.info) + '</svg>')
}
