import zipfile
import io
from lxml import etree
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from models import Track, TrackPoint

# Robust namespace handling for different KML versions
NAMESPACES = {
    'kml': 'http://www.opengis.net/kml/2.2',
    'kml23': 'http://www.opengis.net/kml/2.3',
    'gx': 'http://www.google.com/kml/ext/2.2',
    'atom': 'http://www.w3.org/2005/Atom',
    'opentracks': 'http://opentracksapp.com/xmlschemas/v1'
}


def parse_kmz_file(file_content: bytes, db: Session, user_id: int) -> Track:
    """
    Main entry point to parse a KMZ file and save it to the DB.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(file_content)) as z:
            # Find the main KML file (usually doc.kml)
            kml_filename = next(name for name in z.namelist() if name.endswith('.kml'))
            with z.open(kml_filename) as f:
                kml_content = f.read()
                return parse_kml_content(kml_content, db, user_id)
    except StopIteration:
        raise ValueError("Invalid KMZ: No .kml file found inside.")
    except zipfile.BadZipFile:
        raise ValueError("Invalid KMZ: Not a valid zip file.")


def parse_kml_content(kml_content: bytes, db: Session, user_id: int) -> Track:
    """
    Parses the raw KML XML content.
    """
    try:
        # Recover=True allows the parser to handle minor XML errors gracefully
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(kml_content, parser=parser)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid KML XML: {e}")

    # 1. Find the main Placemark
    track_placemark = find_track_placemark(root)

    if track_placemark is None:
        raise ValueError("No suitable Track Placemark found in KML (looked for Track, MultiTrack, or gx:Track).")

    # 2. Extract Track Metadata
    name = get_text(track_placemark, 'kml:name') or get_text(track_placemark, 'kml23:name') or "Unknown Track"
    description = get_text(track_placemark, 'kml:description') or get_text(track_placemark, 'kml23:description')

    # Create the Track object linked to the user
    db_track = Track(
        name=name,
        description=description,
        user_id=user_id  # <--- NEW: Link to user
    )

    # Save track first to get an ID
    db.add(db_track)
    db.commit()
    db.refresh(db_track)

    # 3. Extract Track Points
    track_node = track_placemark.find('.//kml23:Track', NAMESPACES)
    if track_node is None:
        track_node = track_placemark.find('.//gx:Track', NAMESPACES)
    if track_node is None:
        track_node = track_placemark.find('.//kml:Track', NAMESPACES)

    if track_node is not None:
        parse_complex_track_points(track_node, db_track, db)
    else:
        # Fallback to simple LineString
        line_string = track_placemark.find('.//kml:LineString', NAMESPACES) or \
                      track_placemark.find('.//kml23:LineString', NAMESPACES)
        if line_string is not None:
            parse_linestring_points(line_string, db_track, db)
        else:
            print("Warning: Found placemark but no recognized Track geometry.")

    # 4. Calculate summary stats from the inserted points
    update_track_stats_from_data(db_track, db)

    return db_track


def find_track_placemark(root):
    """
    Scans for a Placemark containing track data.
    """
    possible_paths = [
        './/kml23:Placemark',
        './/kml:Placemark',
        './/gx:Placemark'
    ]

    for path in possible_paths:
        for placemark in root.findall(path, NAMESPACES):
            # Check if this Placemark contains a Track or MultiTrack
            if (placemark.find('.//kml23:Track', NAMESPACES) is not None or
                    placemark.find('.//kml23:MultiTrack', NAMESPACES) is not None or
                    placemark.find('.//gx:Track', NAMESPACES) is not None or
                    placemark.find('.//kml:Track', NAMESPACES) is not None or
                    placemark.find('.//kml:LineString', NAMESPACES) is not None or
                    placemark.find('.//kml23:LineString', NAMESPACES) is not None):
                return placemark

    return None


def get_text(node, tag):
    """Helper to get text safely from a direct child"""
    found = node.find(tag, NAMESPACES)
    return found.text if found is not None else None


def parse_complex_track_points(track_node, db_track: Track, db: Session):
    """
    Parses <Track> elements.
    """
    whens = track_node.findall('./kml23:when', NAMESPACES) or track_node.findall('./kml:when',
                                                                                 NAMESPACES) or track_node.findall(
        './gx:when', NAMESPACES)
    coords = track_node.findall('./kml23:coord', NAMESPACES) or track_node.findall('./kml:coord',
                                                                                   NAMESPACES) or track_node.findall(
        './gx:coord', NAMESPACES)

    if not whens or not coords:
        return

    sensor_data = extract_sensor_arrays(track_node)
    points = []
    count = 0
    limit = min(len(whens), len(coords))

    for i in range(limit):
        try:
            dt_str = whens[i].text
            if not dt_str: continue
            dt_str = dt_str.replace("Z", "+00:00")
            time_obj = datetime.fromisoformat(dt_str)

            coord_text = coords[i].text
            if not coord_text or not coord_text.strip(): continue

            parts = coord_text.strip().split()
            if len(parts) < 2: continue

            lon = float(parts[0])
            lat = float(parts[1])
            alt = float(parts[2]) if len(parts) > 2 else None

            speed_val = get_array_value(sensor_data, 'speed', i)
            speed_kmh = (float(speed_val) * 3.6) if speed_val is not None else None
            heart_rate = get_array_value(sensor_data, 'heartrate', i) or get_array_value(sensor_data, 'heart_rate', i)
            cadence = get_array_value(sensor_data, 'cadence', i)

            geom_wkt = f'POINT({lon} {lat})'

            points.append(TrackPoint(
                track_id=db_track.id,
                time=time_obj,
                latitude=lat,
                longitude=lon,
                elevation_m=alt,
                speed_kmh=speed_kmh,
                heart_rate=int(float(heart_rate)) if heart_rate else None,
                cadence=int(float(cadence)) if cadence else None,
                geom_point=geom_wkt
            ))

            count += 1
            if count >= 1000:
                db.bulk_save_objects(points)
                points = []
                count = 0

        except (ValueError, IndexError) as e:
            continue

    if points:
        db.bulk_save_objects(points)
    db.commit()


def extract_sensor_arrays(track_node) -> dict:
    data = {}
    schema_data = track_node.find('.//kml23:SchemaData', NAMESPACES)
    if schema_data is None:
        schema_data = track_node.find('.//kml:SchemaData', NAMESPACES)
    if schema_data is None:
        schema_data = track_node.find('.//gx:SchemaData', NAMESPACES)

    if schema_data is None:
        return data

    for array in schema_data.findall('.//kml23:SimpleArrayData', NAMESPACES) + \
                 schema_data.findall('.//kml:SimpleArrayData', NAMESPACES) + \
                 schema_data.findall('.//gx:SimpleArrayData', NAMESPACES):
        name = array.get('name')
        values = []
        for val in array.findall('.//*', NAMESPACES):
            if 'value' in val.tag:
                values.append(val.text)
        data[name] = values
    return data


def get_array_value(sensor_data, key, index):
    if key in sensor_data and index < len(sensor_data[key]):
        val = sensor_data[key][index]
        if val and val.strip():
            try:
                return float(val)
            except ValueError:
                return None
    return None


def parse_linestring_points(linestring_node, db_track: Track, db: Session):
    coords_text = linestring_node.findtext('kml:coordinates', namespaces=NAMESPACES) or \
                  linestring_node.findtext('kml23:coordinates', namespaces=NAMESPACES)
    if not coords_text: return

    points = []
    for coord_str in coords_text.strip().split():
        try:
            parts = coord_str.split(',')
            lon = float(parts[0])
            lat = float(parts[1])
            alt = float(parts[2]) if len(parts) > 2 else None
            geom_wkt = f'POINT({lon} {lat})'

            points.append(TrackPoint(
                track_id=db_track.id,
                time=datetime.now(),
                latitude=lat,
                longitude=lon,
                elevation_m=alt,
                geom_point=geom_wkt
            ))
        except ValueError:
            continue

    if points:
        db.bulk_save_objects(points)
    db.commit()


def update_track_stats_from_data(track: Track, db: Session):
    db.execute(
        text("""
        UPDATE opentracks_tracks
        SET geom_track = (
            SELECT ST_MakeLine(geom_point::geometry ORDER BY time)
            FROM opentracks_track_points
            WHERE track_id = :track_id
        )
        WHERE id = :track_id
        """),
        {'track_id': track.id}
    )

    stats = db.query(
        func.min(TrackPoint.time),
        func.max(TrackPoint.time),
        func.max(TrackPoint.speed_kmh),
        func.avg(TrackPoint.speed_kmh),
        func.max(TrackPoint.elevation_m),
        func.min(TrackPoint.elevation_m)
    ).filter(TrackPoint.track_id == track.id).first()

    if stats:
        track.start_time = stats[0]
        track.end_time = stats[1]
        track.max_speed_kmh = stats[2]
        track.avg_speed_kmh = stats[3]
        track.max_elevation_m = stats[4]
        track.min_elevation_m = stats[5]

    dist_result = db.execute(
        text("SELECT ST_Length(geom_track) FROM opentracks_tracks WHERE id = :tid"),
        {'tid': track.id}
    ).scalar()

    if dist_result:
        track.total_distance_m = dist_result

    if track.start_time and track.end_time:
        delta = track.end_time - track.start_time
        track.total_time_s = int(delta.total_seconds())

    db.commit()