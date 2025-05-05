#!/usr/bin/env python3

import os
import pandas as pd
from datetime import datetime
import time
import urllib.request
from ..Utilities import _shell
from ..BaseDownloader import BaseDownloader
from ..Weather.WeatherUtils import (
    get_existing_date_coverage, 
    get_missing_date_ranges,
    build_download_url,
    validate_downloaded_file,
    generate_filename
)

class WeatherDownloader(BaseDownloader):
    """
    Manages weather data downloads for MLB venues.
    """

    def __init__(self, path):
        """        
        :param path: the path to the folder for all SaberSQL data
        """
        super().__init__(path)
    
    def download(self, matches_df, start_date, end_date, weather_types=None, 
            delay_seconds=2.5, handler=lambda *args: None):
        """
        Downloads weather data for venues based on matched weather stations.
        Only downloads date ranges that aren't already covered by existing files.
        
        :param matches_df: DataFrame with venue-to-station matches
        :param start_date: Start date in 'YYYY-MM-DD' format
        :param end_date: End date in 'YYYY-MM-DD' format
        :param weather_types: List of weather data types to fetch
        :param delay_seconds: Delay between requests to avoid overwhelming the server
        :param handler: Progress reporting function
        :return: True if any data was downloaded, False otherwise
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
    
    def _prepare_download(self, weather_types=None):
        """Prepare for download by creating directory and setting defaults."""
        weather_dir = os.path.join(self._path, "Weather")
        self._ensure_dir_exists(weather_dir)
        
        if not weather_types:
            weather_types = ["tmpf", "dwpf", "relh", "drct", "sknt", "gust", "alti", "vsby", "wxcodes"]
            
        return weather_dir

    def _initialize_tracking(self, weather_dir, start_date, end_date, weather_types, matches_df):
        """Initialize the operation tracker."""
        tracker = self._init_tracker(weather_dir)
        
        self._start_tracking(tracker, 'download',
                          start_date=start_date,
                          end_date=end_date,
                          weather_types=weather_types,
                          total_stations=len(matches_df))
        return tracker

    def _process_all_stations(self, matches_df, requested_start, requested_end, 
                            existing_coverage, weather_types, weather_dir, 
                            tracker, delay_seconds, handler):
        """Process all stations and download necessary data."""
        total_stations = len(matches_df)
        processed_stations = 0
        downloaded_files = 0
        
        for _, row in matches_df.iterrows():
            if pd.isna(row['station_icao']):
                print(f"No weather station matched for venue {row['venue_name']} (ID: {row['venue_id']})")
                processed_stations += 1
                continue
            
            date_ranges = self._determine_date_ranges(
                row.station_icao, existing_coverage, requested_start, requested_end)
            
            if not date_ranges:
                print(f"Weather data for venue {row['venue_name']} already complete, skipping")
                processed_stations += 1
                handler(processed_stations / total_stations, 
                    status=f"Skipped venue {row['venue_id']} (already complete)")
                continue
            
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
            
            try:
                filename = generate_filename(row, range_start, range_end)
                filepath = os.path.join(weather_dir, filename)
            except Exception as e:
                print(f"Error generating filename: {str(e)}")
                continue
            
            print(f"Downloading weather data for venue {row['venue_name']} (ID: {row['venue_id']}) from {range_start_str} to {range_end_str}")
            
            url = build_download_url(row.station_icao, range_start, range_end, weather_types)
            
            # Use retry logic from parent class for downloading
            try:
                def download_weather_file():
                    urllib.request.urlretrieve(url, filepath)
                    return True
                
                def error_handler(error, attempt, max_attempts):
                    print(f"  Retry {attempt}/{max_attempts} for {row['venue_name']}: {str(error)[:100]}")
                
                self._retry_operation(
                    download_weather_file,
                    max_retries=3,
                    error_handler=error_handler
                )
                
                if validate_downloaded_file(filepath, row['station_icao'], row['venue_name'], tracker, range_start_str, range_end_str):
                    self._add_venue_id_to_file(filepath, row['venue_id'])
                    downloaded_count += 1
                else:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    print(f"  Validation failed for {filename}")
            except Exception as e:
                self._handle_download_error(e, filepath, row, tracker, range_start_str, range_end_str, url)
        
        return downloaded_count
        
    def _add_venue_id_to_file(self, filepath, venue_id):
        """Add venue_id to the CSV file as a comment in the header."""
        try:
            with open(filepath, 'r') as file:
                content = file.read()
                
            # Add venue_id comment at the beginning
            venue_comment = f"# venue_id: {venue_id}\n"
            
            comment_end = 0
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('#'):
                    comment_end = i + 1
                else:
                    break
            
            lines.insert(comment_end, venue_comment)
            
            with open(filepath, 'w') as file:
                file.write('\n'.join(lines))
                
        except Exception as e:
            print(f"  Warning: Could not add venue_id to file: {str(e)}")

    def _handle_download_error(self, error, filepath, row, tracker, start_date, end_date, url):
        """Handle errors during download."""
        print(f"Error downloading data for venue {row['venue_name']} (ID: {row['venue_id']}): {str(error)}")
        if os.path.exists(filepath):
            os.remove(filepath)
        
        self._record_error(tracker, 'download', error, 
                       venue_name=row['venue_name'],
                       venue_id=row['venue_id'],
                       station=row['station_icao'],
                       date_range=f"{start_date} to {end_date}",
                       url=url)

    def _complete_operation(self, tracker, results, handler):
        """Complete the download operation and update status."""
        success = results['downloaded_files'] > 0
        
        self._complete_tracking(tracker, 'download', 
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
            
    def undownload(self, handler=lambda *args: None, start_date=None, end_date=None):
        """
        Undoes download of weather data.
        
        :param handler: a function that takes in a double, representing the completion percentage of the undownload
        :param start_date: Optional start date (ignored for undownload)
        :param end_date: Optional end date (ignored for undownload)
        """
        weather_dir = os.path.join(self._path, "Weather")
        
        handler(0, status="Removing downloaded weather data")
        
        tracker = self._init_tracker(weather_dir, 'undownload')
        self._start_tracking(tracker, 'undownload')
        
        try:
            if os.path.exists(weather_dir):
                _shell(f"rm -rf \"{weather_dir}\"")
                print(f"Removed weather data directory: {weather_dir}")
                
                self._ensure_dir_exists(weather_dir)
                
                self._complete_tracking(tracker, 'undownload', success=True)
            else:
                print(f"Weather data directory not found: {weather_dir}")
                
                self._ensure_dir_exists(weather_dir)
                
                self._complete_tracking(tracker, 'undownload', success=True, note="Directory did not exist")
            
            handler(1, status="Weather data removal complete")
            return True
            
        except Exception as e:
            print(f"Error removing weather data: {str(e)}")
            
            self._ensure_dir_exists(weather_dir)
                
            self._complete_tracking(tracker, 'undownload', success=False, error=e)
            
            handler(1, status=f"Error removing weather data: {str(e)}")
            return False