#!/usr/bin/env python3

import pandas as pd
import numpy as np
import sqlalchemy

def get_venues_from_database(connection):
    """
    Retrieve venue information from the database 'venue' table.
    
    :param connection: A database connection or SQLAlchemy engine
    :return: DataFrame with venue information (venue_id, name, lat, lon)
    """
    try:            
        query = """
        SELECT 
            venue_id,
            name,
            location_latitude AS lat,
            location_longitude AS lon,
            location_city AS city,
            location_state AS state
        FROM venue
        WHERE location_latitude IS NOT NULL AND location_longitude IS NOT NULL
        """
        
        venues_df = pd.read_sql(query, connection)
        
        required_columns = ['venue_id', 'name', 'lat', 'lon']
        for col in required_columns:
            if col not in venues_df.columns:
                raise ValueError(f"Required column '{col}' not found in venue data")
        
        print(f"Retrieved {len(venues_df)} venues from database")
        return venues_df
        
    except Exception as e:
        print(f"Error getting venues from database: {str(e)}")
        raise

def match_venues_to_weather_stations(stations_csv_path, connection, 
                                    start_date=None, end_date=None, 
                                    max_distance_km=None):
    """
    Match each MLB venue to the closest weather station that was active during
    the specified date range and within the maximum acceptable distance.
    
    :param stations_csv_path: Path to ISD history CSV file containing weather stations
    :param connection: A database connection to retrieve venue information
    :param venues_df: DataFrame with venue information (venue_id, name, lat, lon)
                      If not provided, will use the venue table from the database
    :param start_date: Start date in 'YYYY-MM-DD' format to filter stations (inclusive)
    :param end_date: End date in 'YYYY-MM-DD' format to filter stations (inclusive)
    :param max_distance_km: Maximum acceptable distance between venue and station in kilometers
    :return: DataFrame with venue-to-station matches and distances.
    """
    venues = get_venues_from_database(connection)
    
    if venues.empty:
        raise ValueError("No venue data found")
    
    stations = pd.read_csv(stations_csv_path)
    stations = stations.dropna(subset=['ICAO'])
    
    begin_col = next((col for col in stations.columns if col.lower() == 'begin'), None)
    end_col = next((col for col in stations.columns if col.lower() == 'end'), None)
    
    if start_date and begin_col:
        start_date_dt = pd.to_datetime(start_date)
        stations[begin_col] = stations[begin_col].astype(str)
        stations_begin_dt = pd.to_datetime(stations[begin_col])
        stations = stations[stations_begin_dt <= start_date_dt]
    elif start_date:
        print("Warning: 'begin' column not found in stations data, skipping start date filtering")
    
    if end_date and end_col:
        end_date_dt = pd.to_datetime(end_date)
        stations[end_col] = stations[end_col].astype(str)
        stations_end_dt = pd.to_datetime(stations[end_col])
        stations = stations[stations_end_dt >= end_date_dt]
    elif end_date:
        print("Warning: 'end' column not found in stations data, skipping end date filtering")
    
    if len(stations) == 0:
        print("Warning: No stations meet the date criteria")
        return pd.DataFrame([{
            'venue_id': venue['venue_id'],
            'venue_name': venue['name'],
            'station_icao': None,
            'station_usaf': None,
            'distance_km': None
        } for _, venue in venues.iterrows()])
    
    matches = []
    for _, venue in venues.iterrows():
        try:
            dists = haversine(
                venue.lat, venue.lon,
                stations.LAT.values, stations.LON.values
            )
            
            if max_distance_km:
                valid_indices = np.where(dists <= max_distance_km)[0]
                if len(valid_indices) == 0:
                    matches.append({
                        'venue_id': venue.venue_id,
                        'venue_name': venue.name,
                        'station_icao': None,
                        'station_usaf': None,
                        'distance_km': None
                    })
                    continue
                
                # Find the closest station among valid ones
                idx = valid_indices[np.argmin(dists[valid_indices])]
            else:
                idx = np.argmin(dists)
            
            closest = stations.iloc[idx]
            
            # Process ICAO code - some US stations start with K, which needs to be removed
            icao_code = closest.ICAO
            if isinstance(icao_code, str) and icao_code.startswith('K'):
                icao_code = icao_code[1:]
            
            matches.append({
                'venue_id': venue['venue_id'],
                'venue_name': venue['name'],
                'station_icao': icao_code,
                'station_usaf': closest.USAF,
                'distance_km': dists[idx],
                'station_name': closest.get('STATION NAME', '')
            })
        except Exception as e:
            print(f"Error matching venue {venue.name}: {str(e)}")
            matches.append({
                'venue_id': venue.venue_id,
                'venue_name': venue.name,
                'station_icao': None,
                'station_usaf': None,
                'distance_km': None
            })
    
    return pd.DataFrame(matches)

def haversine(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    
    :param lat1: Latitude of point 1
    :param lon1: Longitude of point 1
    :param lat2: Latitude of point 2 (or array of latitudes)
    :param lon2: Longitude of point 2 (or array of longitudes)
    :return: Distance in kilometers
    """
    # Approximate radius of earth in km
    R = 6371.0
    
    # Convert to radians
    φ1, φ2 = np.radians(lat1), np.radians(lat2)
    Δφ = φ2 - φ1
    Δλ = np.radians(lon2) - np.radians(lon1)
    
    # Haversine formula
    a = np.sin(Δφ/2)**2 + np.cos(φ1)*np.cos(φ2)*np.sin(Δλ/2)**2
    
    return R * 2 * np.arcsin(np.sqrt(a))