#!/usr/bin/env python3

import os
import pandas as pd
from datetime import datetime, timedelta

def get_existing_date_coverage(weather_dir):
    """Scan existing CSV files to determine date coverage for each station."""
    coverage = {}  # station_id -> list of (start_date, end_date) tuples
    
    for csv_file in os.listdir(weather_dir):
        if not csv_file.endswith('.csv'):
            continue
        #TODO - add station name to filename?
        file_info = parse_filename_info(csv_file)
        if not file_info:
            continue
        
        file_path = os.path.join(weather_dir, csv_file)
        try:
            df = pd.read_csv(file_path, comment='#', nrows=1)  
            if df.empty or 'station' not in df.columns:
                continue
                
            station = df['station'].iloc[0]
            
            if station not in coverage:
                coverage[station] = []
            coverage[station].append((file_info['start_date'], file_info['end_date']))
            
        except Exception:
            continue
    
    # Merge overlapping date ranges
    for station in coverage:
        coverage[station] = merge_date_ranges(coverage[station])
    
    return coverage

def merge_date_ranges(ranges):
    """Merge overlapping date ranges."""
    if not ranges:
        return []
        
    # Sort by start date
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    
    merged = [sorted_ranges[0]]
    for current_start, current_end in sorted_ranges[1:]:
        prev_start, prev_end = merged[-1]
        
        # If current range overlaps with previous range, merge them
        if current_start <= prev_end + timedelta(days=1):
            merged[-1] = (prev_start, max(prev_end, current_end))
        else:
            # No overlap, add as a new range
            merged.append((current_start, current_end))
            
    return merged

def get_missing_date_ranges(coverage, requested_start, requested_end):
    """Find date ranges that aren't covered by existing data."""
    if not coverage:
        return [(requested_start, requested_end)]
    
    missing = []
    
    # Check if we need data before the first existing range
    if requested_start < coverage[0][0]:
        missing.append((requested_start, min(coverage[0][0] - timedelta(days=1), requested_end)))
    
    # Check for gaps between existing ranges
    for i in range(len(coverage) - 1):
        gap_start = coverage[i][1] + timedelta(days=1)
        gap_end = coverage[i+1][0] - timedelta(days=1)
        
        if gap_start <= gap_end and gap_start <= requested_end and gap_end >= requested_start:
            adjusted_start = max(gap_start, requested_start)
            adjusted_end = min(gap_end, requested_end)
            missing.append((adjusted_start, adjusted_end))
    
    # Check if we need data after the last existing range
    if requested_end > coverage[-1][1]:
        missing.append((max(coverage[-1][1] + timedelta(days=1), requested_start), requested_end))
    
    return missing

def build_download_url(station_icao, start_date, end_date, weather_types):
    """Build the URL for downloading weather data."""
    data_params = "&".join([f"data={wt}" for wt in weather_types])
        
    return (
            f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
            f"station={station_icao}&{data_params}"
            f"&year1={start_date.year}&month1={start_date.month}&day1={start_date.day}"
            f"&year2={end_date.year}&month2={end_date.month}&day2={end_date.day}"
            f"&tz=Etc/UTC&format=comma&latlon=yes"
    )

def validate_downloaded_file(filepath, station_icao, stadium, tracker, start_date, end_date):
        """Validate that the downloaded file contains data."""
        with open(filepath, 'r') as f:
            content = f.read()
        
        if '#' in content and not any(line.strip() and not line.strip().startswith('#') for line in content.split('\n')):
            print(f"  No data retrieved for {stadium} in this date range")
            os.remove(filepath)
            tracker.record_error('download',
                            ValueError(f"No data available for station {station_icao} in this date range"),
                            stadium=stadium,
                            station=station_icao,
                            date_range=f"{start_date} to {end_date}")
            return False
        
        print(f" Weather data downloaded for {stadium}")
        return True

def parse_filename_info(filename):
    """
        Extract stadium, team, and date information from a weather filename.
        
        Expected format: "TEAM__STADIUM__START-DATE__END-DATE.csv"
     """
    try:
        parts = os.path.splitext(filename)[0].split('__')
        if len(parts) != 4:
            return None
            
        return {
            'team': parts[0],
            'stadium': parts[1],
            'start_date': datetime.strptime(parts[2], '%Y-%m-%d'),
            'end_date': datetime.strptime(parts[3], '%Y-%m-%d')
        }
    except Exception:
        return None
    
def clean_weather_dataframe(df):
    """Clean and prepare a weather DataFrame for import."""
    if df.empty:
        return df
    
    df = df.copy()
    
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].replace('M', pd.NA)
    
    numeric_cols = ['tmpf', 'dwpf', 'relh', 'drct', 'sknt', 'gust', 'alti', 'vsby', 'lat', 'lon']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    if 'valid' in df.columns:
        df['valid'] = pd.to_datetime(df['valid'], errors='coerce')
    
    if 'station' in df.columns and 'valid' in df.columns:
        df['non_null_count'] = df.notna().sum(axis=1)
        df = (
            df.sort_values('non_null_count', ascending=False)
            .drop_duplicates(subset=['station', 'valid'], keep='first')
        )
        df = df.drop(columns=['non_null_count'])
    
    return df

def read_weather_csv(filepath):
    """Read a weather CSV file and clean the data."""
    try:
        df = pd.read_csv(filepath, comment='#')
        
        if df.empty:
            return True, df, "File contains no data rows"
        
        df = clean_weather_dataframe(df)
        
        if 'valid' not in df.columns or 'station' not in df.columns:
            return False, None, "Missing required columns (station or valid)"
        
        return True, df, None
    except Exception as e:
        return False, None, str(e)