#!/usr/bin/env python3

import os
import pandas as pd
from datetime import datetime
import time
import urllib.request
from ..Utilities import _shell
from ..OperationTracker import OperationTracker
from ..Weather.WeatherUtils import get_existing_date_coverage, get_missing_date_ranges

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
            delay_seconds=5, handler=lambda *args: None):
        """
        Downloads weather data for stadiums based on matched weather stations.
        Only downloads date ranges that aren't already covered by existing files.
        """
        weather_dir = self._prepare_download(weather_types)
        
        requested_start = datetime.strptime(start_date, '%Y-%m-%d')
        requested_end = datetime.strptime(end_date, '%Y-%m-%d')
        existing_coverage = get_existing_date_coverage(weather_dir)
        
        tracker = self._initialize_tracking(weather_dir, start_date, end_date, weather_types, matches_df)
        handler(0, status="Analyzing existing data and determining download needs")
        
        results = self._process_all_stations(
            matches_df, requested_start, requested_end, existing_coverage, 
            weather_types, weather_dir, tracker, delay_seconds, handler
        )
        
        self._complete_operation(tracker, results, handler)
        return results['downloaded_files'] > 0
    
    def _parse_filename_info(self, filename):
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
    
    def _prepare_download(self, weather_types=None):
        """Prepare for download by creating directory and setting defaults."""
        weather_dir = os.path.join(self._path, "Weather")
        _shell(f"mkdir -p \"{weather_dir}\"")
        
        return weather_dir

    def _initialize_tracking(self, weather_dir, start_date, end_date, weather_types, matches_df):
        """Initialize the operation tracker."""
        tracker = OperationTracker(weather_dir)
        tracker.start_operation('download', 
                            start_date=start_date,
                            end_date=end_date,
                            weather_types=weather_types,
                            total_stations=len(matches_df))
        return tracker

    def _process_all_stations(self, matches_df, requested_start, requested_end, 
                            existing_coverage, weather_types, weather_dir, 
                            tracker, delay_seconds, handler, force):
        """Process all stations and download necessary data."""
        total_stations = len(matches_df)
        processed_stations = 0
        downloaded_files = 0
        
        for _, row in matches_df.iterrows():
            if pd.isna(row.station_icao):
                print(f"No weather station matched for {row.stadium}")
                processed_stations += 1
                continue
            
            # Determine what needs to be downloaded
            date_ranges = self._determine_date_ranges(
                row.station_icao, existing_coverage, requested_start, requested_end, force)
            
            if not date_ranges:
                print(f"Weather data for {row.stadium} already complete, skipping")
                processed_stations += 1
                handler(processed_stations / total_stations, 
                    status=f"Skipped {row.stadium} (already complete)")
                continue
            
            # Download the data for this station
            station_files = self._download_station_data(
                row, date_ranges, weather_types, weather_dir, tracker)
            downloaded_files += station_files
            
            processed_stations += 1
            handler(processed_stations / total_stations, 
                status=f"Downloading weather data ({processed_stations}/{total_stations})")
            
            # Rate limiting
            if processed_stations < total_stations:
                print(f"  Waiting {delay_seconds} seconds before next request...")
                time.sleep(delay_seconds)
        
        return {
            'processed_stations': processed_stations,
            'downloaded_files': downloaded_files,
            'total_stations': total_stations
        }

    def _determine_date_ranges(self, station_icao, existing_coverage, 
                            requested_start, requested_end):
        """Determine what date ranges need to be downloaded."""
        station_coverage = existing_coverage.get(station_icao, [])
        return get_missing_date_ranges(station_coverage, requested_start, requested_end)

    def _download_station_data(self, row, date_ranges, weather_types, weather_dir, tracker):
        """Download data for all required date ranges for a station."""
        downloaded_count = 0
        
        for range_start, range_end in date_ranges:
            range_start_str = range_start.strftime('%Y-%m-%d')
            range_end_str = range_end.strftime('%Y-%m-%d')
            
            filename = f"{row.team}__{row.stadium}__{range_start_str}__{range_end_str}.csv"
            filepath = os.path.join(weather_dir, filename)
            
            print(f"Downloading weather data for {row.stadium} from {range_start_str} to {range_end_str}")
            
            url = self._build_download_url(row.station_icao, range_start, range_end, weather_types)
            
            try:
                # Download the data
                urllib.request.urlretrieve(url, filepath)
                
                # Validate the file
                if self._validate_downloaded_file(filepath, row.station_icao, row.stadium, tracker, range_start_str, range_end_str):
                    downloaded_count += 1
            except Exception as e:
                self._handle_download_error(e, filepath, row, tracker, range_start_str, range_end_str, url)
        
        return downloaded_count

    def _handle_download_error(self, error, filepath, row, tracker, start_date, end_date, url):
        """Handle errors during download."""
        print(f"Error downloading data for {row.stadium}: {str(error)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        
        tracker.record_error('download', error, 
                        stadium=row.stadium, 
                        station=row.station_icao,
                        date_range=f"{start_date} to {end_date}",
                        url=url)

    def _complete_operation(self, tracker, results, handler):
        """Complete the download operation and update status."""
        success = results['downloaded_files'] > 0
        tracker.complete_operation('download', 
                                success=success,
                                downloaded_files=results['downloaded_files'],
                                processed_stations=results['processed_stations'],
                                total_stations=results['total_stations'])
        
        if success:
            print(f"Successfully downloaded weather data for {results['downloaded_files']} date ranges")
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