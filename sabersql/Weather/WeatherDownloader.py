#!/usr/bin/env python3

import os
import pandas as pd
from datetime import datetime
import time
import urllib.request
from ..Utilities import _shell
from ..OperationTracker import OperationTracker

class WeatherDownloader:
    """
    Manages weather data downloads for MLB stadiums.
    """

    def __init__(self, path):
        """        
        :param path: the path to the folder for all SaberSQL data
        """
        self._path = path
    
    def download(self, matches_df, start_date, end_date, weather_types=None, 
                delay_seconds=5, handler=lambda *args: None, force=False):
        """
        Downloads weather data for stadiums based on matched weather stations.
        
        :param matches_df: DataFrame with stadium-to-station matches from Stadium.py
        :param start_date: Start date in 'YYYY-MM-DD' format
        :param end_date: End date in 'YYYY-MM-DD' format
        :param weather_types: List of weather data types to fetch (default: tmpf, dwpf, sknt)
        :param delay_seconds: Delay between requests
        :param handler: a function that takes in a double, representing the completion percentage of the download
        :param force: If True, force download even if it was previously completed
        """
        weather_dir = os.path.join(self._path, "Weather")
        _shell(f"mkdir -p \"{weather_dir}\"")
        
        if weather_types is None:
            weather_types = ["tmpf", "dwpf", "relh", "drct", "sknt", "gust", "alti", "vsby", "wxcodes"]
        
        start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
        
        # Format the data parameters
        data_params = "&".join([f"data={wt}" for wt in weather_types])
        
        tracker = OperationTracker(weather_dir)
        
        if tracker.is_operation_complete('download') and not force:
            print("Weather data already downloaded. Use force=True to redownload.")
            handler(1, status="Weather data already downloaded")
            return
        
        tracker.start_operation('download', 
                              start_date=start_date,
                              end_date=end_date,
                              weather_types=weather_types,
                              total_stations=len(matches_df))
        
        handler(0, status="Downloading weather data")
        
        # Process each stadium-station pair
        total_stations = len(matches_df)
        processed_stations = 0
        downloaded_files = 0
        
        for _, row in matches_df.iterrows():
            if pd.isna(row.station_icao):
                print(f"No weather station matched for {row.stadium}")
                processed_stations += 1
                continue
                
            filename = f"{row.team}_{row.stadium.replace(' ', '_')}_{start_date}_{end_date}.csv"
            filepath = os.path.join(weather_dir, filename)
            
            # Skip if file already exists and is not empty and we're not forcing redownload
            if not force and os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                print(f"Weather data for {row.stadium} already exists, skipping. ")
                processed_stations += 1
                handler(processed_stations / total_stations, 
                      status=f"Skipped {row.stadium} (already downloaded)")
                continue
            
            year1, month1, day1 = start_date_obj.year, start_date_obj.month, start_date_obj.day
            year2, month2, day2 = end_date_obj.year, end_date_obj.month, end_date_obj.day
            
            url = (
                f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?"
                f"station={row.station_icao}&{data_params}"
                f"&year1={year1}&month1={month1}&day1={day1}"
                f"&year2={year2}&month2={month2}&day2={day2}"
                f"&tz=Etc/UTC&format=comma&latlon=yes"
            )
            
            try:
                # Download the data
                print(f"Downloading weather data for {row.stadium} (Station: {row.station_icao})")
                urllib.request.urlretrieve(url, filepath)
                
                # Check if the file is not empty and contains data (not just headers)
                with open(filepath, 'r') as f:
                    content = f.read()
                
                if '#' in content and not any(line.strip() and not line.strip().startswith('#') for line in content.split('\n')):
                    print(f"  No data retrieved for {row.stadium}")
                    os.remove(filepath)
                    # Record the error but continue
                    tracker.record_error('download',
                                       ValueError(f"No data available for station {row.station_icao}"),
                                       stadium=row.stadium,
                                       station=row.station_icao)
                else:
                    print(f"  Weather data downloaded for {row.stadium}")
                    downloaded_files += 1
            except Exception as e:
                print(f"Error downloading data for {row.stadium}: {str(e)}")
                # If there was an error, remove the potentially partially downloaded file
                if os.path.exists(filepath):
                    os.remove(filepath)
                tracker.record_error('download', e, 
                                   stadium=row.stadium, 
                                   station=row.station_icao,
                                   url=url)
            
            processed_stations += 1
            handler(processed_stations / total_stations, 
                  status=f"Downloading weather data ({processed_stations}/{total_stations})")
            
            # Rate limiting
            if processed_stations < total_stations:
                print(f"  Waiting {delay_seconds} seconds before next request...")
                time.sleep(delay_seconds)
        
        success = downloaded_files > 0
        tracker.complete_operation('download', 
                                 success=success,
                                 downloaded_files=downloaded_files,
                                 processed_stations=processed_stations,
                                 total_stations=total_stations)
        
        if success:
            print(f"Successfully downloaded weather data for {downloaded_files} stations")
            handler(1, status="Weather data download complete")
        else:
            error_message = "Failed to download any weather data"
            print(error_message)
            handler(1, status=error_message)
    
    def undownload(self, handler=lambda *args: None):
        """
        Undoes download of weather data.
        
        :param handler: a function that takes in a double, representing the completion percentage of the undownload
        """
        weather_dir = os.path.join(self._path, "Weather")
        
        handler(0, status="Removing downloaded weather data")
        
        tracker = OperationTracker(weather_dir)
        
        tracker.start_operation('undownload')
        
        try:
            if os.path.exists(weather_dir):
                _shell(f"rm -rf \"{weather_dir}\"")
                print(f"Removed weather data directory: {weather_dir}")
                
                _shell(f"mkdir -p \"{weather_dir}\"")
                
                tracker = OperationTracker(weather_dir)
                tracker.complete_operation('undownload', success=True)
            else:
                print(f"Weather data directory not found: {weather_dir}")
                
                _shell(f"mkdir -p \"{weather_dir}\"")
                
                # Nothing to undownload, but still complete the operation
                tracker = OperationTracker(weather_dir)
                tracker.complete_operation('undownload', success=True, note="Directory did not exist")
            
            handler(1, status="Weather data removal complete")
            return True
            
        except Exception as e:
            print(f"Error removing weather data: {str(e)}")
            
            # Make sure the directory exists for the tracker
            if not os.path.exists(weather_dir):
                _shell(f"mkdir -p \"{weather_dir}\"")
                
            tracker = OperationTracker(weather_dir)
            tracker.complete_operation('undownload', success=False, error=e)
            
            handler(1, status=f"Error removing weather data: {str(e)}")
            return False