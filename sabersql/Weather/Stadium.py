import pandas as pd
import numpy as np

def match_stadiums_to_weather_stations(stations_csv_path, stadiums_csv_path, 
                                       start_date=None, end_date=None, 
                                       max_distance_km=None):
    """
    Match each MLB stadium to the closest weather station that was active during
    the specified date range and within the maximum acceptable distance.
    
    :param stations_csv_path: Path to ISD history CSV file containing weather stations
    :param stadiums_csv_path: Path to CSV file containing stadium information
    :param start_date: Start date in 'YYYY-MM-DD' format to filter stations (inclusive)
    :param end_date: End date in 'YYYY-MM-DD' format to filter stations (inclusive)
    :param max_distance_km: Maximum acceptable distance between stadium and station in kilometers
    :return: DataFrame with stadium-to-station matches and distances. 
             If no station meets the criteria for a stadium, the station_icao, 
             station_usaf, and distance_km fields will be None for that stadium.
    """
    stadia = pd.read_csv(stadiums_csv_path)  # team, stadium, lat, lon
    
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
    
    # Check if we have any stations left after filtering
    if len(stations) == 0:
        print("Warning: No stations meet the date criteria")
        return pd.DataFrame([{
            'team': park.team,
            'stadium': park.stadium,
            'station_icao': None,
            'station_usaf': None,
            'distance_km': None
        } for _, park in stadia.iterrows()])
    
    # Match each stadium to the closest weather station within max_distance_km
    matches = []
    for _, park in stadia.iterrows():
        dists = haversine(
            park.lat, park.lon,
            stations.LAT.values, stations.LON.values
        )
        
        if max_distance_km:
            valid_indices = np.where(dists <= max_distance_km)[0]
            if len(valid_indices) == 0:
                # No stations within acceptable distance
                matches.append({
                    'team': park.team,
                    'stadium': park.stadium,
                    'station_icao': None,
                    'station_usaf': None,
                    'distance_km': None
                })
                continue
            
            # Find the closest station among valid ones
            idx = valid_indices[np.argmin(dists[valid_indices])]
        else:
            # No distance constraint, just find the closest
            idx = np.argmin(dists)
        
        closest = stations.iloc[idx]
        matches.append({
            'team': park.team,
            'stadium': park.stadium,
            'station_icao': closest.ICAO[1:] if closest.ICAO[0] == 'K' else closest.ICAO,
            'station_usaf': closest.USAF,
            'distance_km': dists[idx]
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