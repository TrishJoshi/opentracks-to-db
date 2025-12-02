from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from geoalchemy2 import Geography
from database import Base

class Track(Base):
    __tablename__ = "opentracks_tracks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(Text)
    description = Column(Text)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    total_distance_m = Column(Numeric(10, 2))
    total_time_s = Column(Integer)
    moving_time_s = Column(Integer)
    avg_speed_kmh = Column(Numeric(5, 2))
    max_speed_kmh = Column(Numeric(5, 2))
    avg_moving_speed_kmh = Column(Numeric(5, 2))
    max_elevation_m = Column(Numeric(7, 2))
    min_elevation_m = Column(Numeric(7, 2))
    elevation_gain_m = Column(Numeric(7, 2))
    
    # FIXED: spatial_index=False is now inside Geography()
    geom_track = Column(Geography(geometry_type='LINESTRING', srid=4326, spatial_index=False))
    
    created_at = Column(DateTime(timezone=True), server_default='NOW()')

    # Relationship to link to track points
    points = relationship("TrackPoint", back_populates="track", cascade="all, delete-orphan")


class TrackPoint(Base):
    __tablename__ = "opentracks_track_points"

    id = Column(Integer, primary_key=True, index=True)
    track_id = Column(Integer, ForeignKey("opentracks_tracks.id"))
    time = Column(DateTime(timezone=True), index=True)
    latitude = Column(Numeric(10, 7))
    longitude = Column(Numeric(10, 7))
    elevation_m = Column(Numeric(7, 2))
    speed_kmh = Column(Numeric(5, 2))
    heart_rate = Column(Integer)
    cadence = Column(Integer)

    # FIXED: spatial_index=False is now inside Geography()
    geom_point = Column(Geography(geometry_type='POINT', srid=4326, spatial_index=False))

    # Relationship back to the parent track
    track = relationship("Track", back_populates="points")
