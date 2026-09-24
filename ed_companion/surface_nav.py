"""Planetary waypoint validation and great-circle guidance."""

import math


def parse_coordinate(value, limit):
    """Accept signed decimal degrees, including a decimal comma."""
    try:
        number = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a valid decimal coordinate.") from exc
    if not math.isfinite(number) or abs(number) > limit:
        raise ValueError(f"Coordinate must be between -{limit} and {limit} degrees.")
    return number


def surface_guidance(status, target):
    """Point from the current surface position to a waypoint on this body."""
    try:
        latitude = parse_coordinate(status.get("Latitude"), 90)
        longitude = parse_coordinate(status.get("Longitude"), 180)
        target_latitude = parse_coordinate(target.get("latitude"), 90)
        target_longitude = parse_coordinate(target.get("longitude"), 180)
    except ValueError:
        return {}

    lat1, lat2 = math.radians(latitude), math.radians(target_latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(target_longitude - longitude)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    central_angle = 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))
    east = math.sin(delta_lon) * math.cos(lat2)
    north = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )
    bearing = math.degrees(math.atan2(east, north)) % 360
    result = {"bearingDeg": round(bearing, 1)}

    radius = status.get("PlanetRadius")
    if isinstance(radius, (int, float)) and math.isfinite(radius) and radius > 0:
        result["distanceM"] = round(radius * central_angle)
        result["arrived"] = result["distanceM"] <= 20

    heading = status.get("Heading")
    if isinstance(heading, (int, float)) and math.isfinite(heading):
        result["headingDeg"] = round(heading % 360, 1)
        result["turnDeg"] = round((bearing - heading + 180) % 360 - 180, 1)
    return result
