import requests
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime
from airport_config import AIRPORTS
from threshold_config import THRESHOLDS


MAX_RADIUS_METERS = 48280  # ~30 mi


def haversine(lat1, lon1, alt1, lat2, lon2, alt2):
    # 3D ECEF (WGS-84)
    A = 6378137.0
    F = 1.0 / 298.257223563
    E2 = F * (2.0 - F)

    def to_ecef(lat, lon, alt):
        alt = 0.0 if alt is None else float(alt)
        phi, lam = radians(lat), radians(lon)
        sphi, cphi = sin(phi), cos(phi)
        slam, clam = sin(lam), cos(lam)
        N = A / sqrt(1.0 - E2 * sphi * sphi)
        x = (N + alt) * cphi * clam
        y = (N + alt) * cphi * slam
        z = (N * (1.0 - E2) + alt) * sphi
        return x, y, z

    x1, y1, z1 = to_ecef(lat1, lon1, alt1)
    x2, y2, z2 = to_ecef(lat2, lon2, alt2)
    dx, dy, dz = x1 - x2, y1 - y2, z1 - z2
    return sqrt(dx*dx + dy*dy + dz*dz)

def ground_distance(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = p2 - p1
    dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(p1)*cos(p2)*sin(dl/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def is_ground(plane):
    alt = float(plane.get("Altitude") or 0.0)      # meters
    vel = float(plane.get("Velocity") or 0.0)      # m/s
    vr  = float(plane.get("VerticalRate") or 0.0)  # m/s

    MPS_TO_KT, MPS_TO_FPS = 1.9438444924, 3.28084
    vel_kt, vr_fps = vel * MPS_TO_KT, vr * MPS_TO_FPS

    if alt < 15.0:  # ~0–50 ft: definitely ground
        return True
    if alt < 60.0 and not (vel_kt >= 40.0 or abs(vr_fps) >= 2.0):
        return True
    if alt < 120.0 and vel_kt < 25.0 and abs(vr_fps) < 1.5:
        return True
    return False

def is_airborne(plane):
    return not is_ground(plane)

def fetch_planes_near_airport(airport_code):
    airport = AIRPORTS[airport_code]
    lat, lon = airport["lat"], airport["lon"]

    params = {"lamin": lat - 0.5, "lamax": lat + 0.5, "lomin": lon - 0.5, "lomax": lon + 0.5}

    try:
        resp = requests.get("https://opensky-network.org/api/states/all", params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        aircraft = []

        for ac in data.get("states", []) or []:
            ac_lat, ac_lon = ac[6], ac[5]
            if ac_lat is None or ac_lon is None:
                continue

            # prefer baro (7), fallback geo (13)
            alt = (ac[7] if len(ac) > 7 and ac[7] is not None
                   else (ac[13] if len(ac) > 13 and ac[13] is not None else 0.0))
            if alt is None or alt< 0:
                alt = 0.0

            # 30-mi horizontal filter
            dist_h = ground_distance(lat, lon, ac_lat, ac_lon)
            if dist_h > MAX_RADIUS_METERS:
                continue

            p = {
                "ICAO24": ac[0],
                "Callsign": ac[1].strip() if ac[1] else "N/A",
                "Origin Country": ac[2],
                "Last Contact": datetime.fromtimestamp(ac[4]).isoformat() if ac[4] else None,
                "Longitude": ac_lon,
                "Latitude": ac_lat,
                "Altitude": round(float(alt)),
                "DistanceFromAirport": round(dist_h),
                #"OnGround": ac[8],                 # kept for debugging
                "Velocity": float(ac[9] or 0.0),   # m/s
                "Heading": ac[10],
                "VerticalRate": float(ac[11] or 0.0),  # m/s
                "AlertLevel": "NONE",
                "Conflicts": []
            }
            
            p["Status"] = "In Air" if is_airborne(p) else "On Ground"
            aircraft.append(p)

        return aircraft

    except requests.RequestException as e:
        print(f"[ERROR] Fetch failed: {e}")
        return []

def check_proximity_alerts(planes):
    def sev(lvl): return {"NONE": 0, "WARNING": 1, "ALERT": 2, "ALARM": 3}[lvl]

    # ensure tooltips stay in sync
    for p in planes:
        p["Status"] = "In Air" if is_airborne(p) else "On Ground"

    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            p1, p2 = planes[i], planes[j]
            if None in (p1["Latitude"], p1["Longitude"], p2["Latitude"], p2["Longitude"]):
                continue
            if p1.get("ICAO24") == p2.get("ICAO24"):
                continue

            d = haversine(p1["Latitude"], p1["Longitude"], p1["Altitude"],
                          p2["Latitude"], p2["Longitude"], p2["Altitude"])

            # category (altitude-only ground logic)
            g1, g2 = is_ground(p1), is_ground(p2)
            if g1 and g2:
                cat = "Ground-Ground"
            elif not g1 and not g2:
                cat = "Air-Air"
            else:
                cat = "Air-Ground"

            thr = THRESHOLDS[cat]
            if d <= thr["high"]:
                alert = "ALARM"
            elif d <= thr["medium"]:
                alert = "ALERT"
            elif d <= thr["low"]:
                alert = "WARNING"
            else:
                continue

            for p in (p1, p2):
                if sev(alert) > sev(p["AlertLevel"]):
                    p["AlertLevel"] = alert

            p1["Conflicts"].append({"Callsign": p2["Callsign"], "Distance": round(d), "Alert": alert, "Category": cat})
            p2["Conflicts"].append({"Callsign": p1["Callsign"], "Distance": round(d), "Alert": alert, "Category": cat})