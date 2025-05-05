#!/usr/bin/env python3

import os
import pandas as pd
from ..OperationTracker import OperationTracker
import sqlalchemy
from sqlalchemy import create_engine, text
from .WeatherUtils import parse_filename_info, read_weather_csv, clean_weather_dataframe

class WeatherImporter:
    """
    Manages weather data imports to the database.
    """
    
    def __init__(self, path, connection):
        """        
        :param path: the path to the folder for all SaberSQL data
        :param connection: a MySQLConnection to the database to import data to
        """
        self._path = path
        self._connection = connection

    def _process_weather_file(self, file_path, filename):
        """Process a single weather file and import new records."""
        file_info = parse_filename_info(filename)
        print(f"Reading weather data from {filename}...")
        
        # Read and clean data
        success, df, error_message = read_weather_csv(file_path)
        if not success or df.empty:
            return {'processed': False, 'error': error_message}
        
        # Extract venue_id from filename or file content
        venue_id = self._extract_venue_id(df, file_info, file_path)
        if venue_id is None:
            print(f"  Error: Could not determine venue_id for file {filename}")
            return {'processed': False, 'error': "No venue_id available"}
        
        df['venue_id'] = venue_id
        
        # Find new records to import
        new_records_df, file_stats = self._filter_existing_records(df)
        
        # Import new records if any
        if new_records_df is not None and not new_records_df.empty:
            self._import_records(new_records_df, filename)
            file_stats['imported'] = True
        
        return file_stats
    
    def _extract_venue_id(self, df, file_info, file_path):
        """
        Extract venue_id from various sources.
        
        1. Check file_info from filename
        2. Check for venue_id comment in file
        3. Use station/date to look up existing records
        """
        # Try to get from filename
        if file_info and 'venue_id' in file_info and file_info['venue_id'] is not None:
            return file_info['venue_id']
            
        # Try to get from file comment
        try:
            with open(file_path, 'r') as file:
                for line in file:
                    if line.startswith('# venue_id:'):
                        try:
                            return int(line.split(':')[1].strip())
                        except (ValueError, IndexError):
                            pass
                    if not line.startswith('#'):
                        break
        except Exception:
            pass
            
        # If we have the station, try to look up existing records with the same station
        if 'station' in df.columns and len(df) > 0:
            station = df['station'].iloc[0]
            
            try:
                query = f"""
                SELECT DISTINCT venue_id 
                FROM weather 
                WHERE station = '{station}'
                AND venue_id IS NOT NULL
                LIMIT 1
                """
                
                with self._engine.connect() as conn:
                    result = conn.execute(text(query))
                    row = result.fetchone()
                    if row:
                        return row[0]
            except Exception as e:
                print(f"  Warning: Error looking up venue_id: {str(e)}")
                
        return None
            
    def _filter_existing_records(self, df):
        """
        Filter out records that already exist in the database.
        Returns the filtered DataFrame and statistics.
        """
        stats = {
            'total': len(df),
            'new': 0,
            'skipped': 0
        }
        
        if df.empty:
            return None, stats
        
        # Get database lookup data
        stations = df['station'].unique()
        if len(stations) == 0:
            return None, stats
            
        date_range = None    
        if 'valid' in df.columns:
            valid_dates = df['valid'].dropna()
            if not valid_dates.empty:
                min_date = valid_dates.min()
                max_date = valid_dates.max()
                date_range = (min_date, max_date)
        
        if date_range is None:
            print("  No valid date range found in file")
            stats['skipped'] = len(df)
            return None, stats
            
        existing_keys = self._get_existing_record_keys(stations, *date_range)
        
        # Filter records
        new_records = []
        for _, row in df.iterrows():
            if pd.isna(row.get('valid')):
                stats['skipped'] += 1
                continue
                
            key = f"{row['station']}_{row['valid'].strftime('%Y-%m-%d %H:%M:%S')}"
            if key in existing_keys:
                stats['skipped'] += 1
            else:
                new_records.append(row)
        
        stats['new'] = len(new_records)
        new_df = pd.DataFrame(new_records) if new_records else None
        
        # Report results
        if new_df is not None and not new_df.empty:
            print(f"  Found {stats['new']} new records to import")
            print(f"  Skipping {stats['skipped']} already existing records")
        else:
            print(f"  All {stats['total']} records already exist in the database")
        
        return new_df, stats

    def _get_existing_record_keys(self, stations, min_date, max_date):
        """Get keys for all existing records in the given range."""
        existing_data = self._get_existing_records(stations, min_date, max_date)
        return {f"{row['station']}_{row['valid'].strftime('%Y-%m-%d %H:%M:%S')}" 
                for row in existing_data}

    def _import_records(self, df, filename):
        """Import records to database."""
        print(f"  Importing {len(df)} new weather records...")
        
        # Make sure we have only the columns that are in the weather table
        try:
            df_to_import, filtered_columns = self._connection.filter_dataframe_columns(df, 'pitch')
            if filtered_columns:
                print(f"  Filtered out {len(filtered_columns)} column(s) not in schema:")
                for col in sorted(filtered_columns):
                    print(f"    - {col}")
            # Ensure required columns are present
            required_cols = ['station', 'valid']
            missing_cols = [col for col in required_cols if col not in df_to_import.columns]
            if missing_cols:
                raise ValueError(f"Missing required columns: {missing_cols}")
            
            if 'venue_id' not in df_to_import.columns:
                raise ValueError("venue_id column is required for import")
                
            df_to_import.to_sql(
                'weather',
                self._engine,
                if_exists='append',
                index=False,
                chunksize=100,
                method='multi'
            )
            print(f"  Successfully imported {len(df_to_import)} records")
            
        except Exception as e:
            print(f"  Error importing data: {str(e)}")

    def _update_stats(self, overall_stats, file_stats):
        """Update overall statistics with file statistics."""
        if not file_stats.get('processed', False):
            return
            
        overall_stats['total_records'] += file_stats.get('total', 0)
        overall_stats['new_records'] += file_stats.get('new', 0)
        overall_stats['skipped_records'] += file_stats.get('skipped', 0)
        
        if file_stats.get('imported', False):
            overall_stats['imported_files'] += 1

    def import_weather_data(self, matches_df=None, handler=lambda *args: None, force=False):
        """
        Imports weather data to MySQL database, skipping already existing records.
        
        :param matches_df: DataFrame with venue-to-station matches (optional)
        :param handler: Progress reporting function
        :param force: If True, import even if operation was previously completed
        """
        weather_dir = os.path.join(self._path, "Weather")
        
        tracker = OperationTracker(weather_dir)
        
        if tracker.is_operation_complete('import') and not force:
            print("Weather data import already marked as complete.")
            handler(1, status="Weather data already imported")
            return True
        
        if not self._prepare_import(weather_dir, tracker, handler):
            return False
        
        csv_files = [f for f in os.listdir(weather_dir) if f.endswith('.csv')]
        if not csv_files:
            self._handle_no_files(tracker, handler)
            return False
        
        stats = {
            'total_records': 0,
            'new_records': 0, 
            'skipped_records': 0,
            'imported_files': 0
        }
        
        handler(0, status="Importing weather data")
        for i, csv_file in enumerate(csv_files):
            file_path = os.path.join(weather_dir, csv_file)
            
            try:
                file_stats = self._process_weather_file(file_path, csv_file)
                self._update_stats(stats, file_stats)
                
                handler((i + 1) / len(csv_files), 
                    status=f"Importing weather data ({i+1}/{len(csv_files)})")
                    
            except Exception as e:
                print(f"  Error importing {csv_file}: {str(e)}")
                tracker.record_error('import', e, file=csv_file)
        
        self._finalize_import(tracker, stats, handler)
        return stats['imported_files'] > 0 or stats['skipped_records'] > 0
    
    def _prepare_import(self, weather_dir, tracker, handler):
        """Setup and validate import prerequisites."""
        if not os.path.exists(weather_dir):
            print(f"Weather data directory not found: {weather_dir}")
            handler(1, status="No weather data to import")
            return False
        
        tracker.start_operation('import', source_files_count=0)
        return True

    def _handle_no_files(self, tracker, handler):
        """Handle case when no files are found."""
        print("No weather data files found to import.")
        tracker.complete_operation('import', success=False, 
                                error=ValueError("No weather data files found"))
        handler(1, status="No weather data to import")

    def _finalize_import(self, tracker, stats, handler):
        """Complete the import operation with statistics."""
        if stats['imported_files'] > 0 or stats['new_records'] > 0:
            print(f"Successfully imported {stats['new_records']} new records from {stats['imported_files']} files")
            print(f"Skipped {stats['skipped_records']} already existing records")
            
            tracker.complete_operation('import', success=True, 
                                    imported_files=stats['imported_files'],
                                    total_records=stats['total_records'],
                                    new_records=stats['new_records'],
                                    skipped_records=stats['skipped_records'])
        else:
            if stats['skipped_records'] > 0:
                print(f"All {stats['skipped_records']} records already exist in the database")
                tracker.complete_operation('import', success=True,
                                        skipped_records=stats['skipped_records'],
                                        new_records=0)
            else:
                print("Failed to import any weather data files")
                tracker.complete_operation('import', success=False,
                                        error=ValueError("No files were successfully imported"))
        
        handler(1, status="Weather data import complete")

    def _get_existing_records(self, stations, min_date, max_date):
        """
        Query the database for existing records for the given stations and date range.
        
        :param stations: List of station codes
        :param min_date: Minimum date to check
        :param max_date: Maximum date to check
        :return: List of dictionaries containing station and valid fields
        """
        try:
            # Format the stations list for SQL IN clause
            stations_str = "', '".join(stations)
            
            # Format dates for SQL query
            min_date_str = min_date.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(min_date) else '1900-01-01'
            max_date_str = max_date.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(max_date) else '2100-01-01'
            
            # Query for existing records
            query = f"""
                SELECT station, valid 
                FROM weather 
                WHERE station IN ('{stations_str}')
                  AND valid BETWEEN '{min_date_str}' AND '{max_date_str}'
            """
            
            with self._engine.connect() as conn:
                result = conn.execute(text(query))
                existing_records = [{'station': row[0], 'valid': row[1]} for row in result]
                
            return existing_records
        except Exception as e:
            print(f"Error checking existing records: {str(e)}")
            return []
    
    def unimport_weather_data(self, handler=lambda *args: None):
        """
        Undoes import of weather data from MySQL database.
        
        :param handler: a function that takes in a double, representing the completion percentage of the unimport
        :raises ConnectionError: if the connection fails
        """
        handler(0, status="Undoing weather data import")
        self.__undo_sql_import()
        handler(1, status="Weather data import undone")
    
    def __undo_sql_import(self):
        """
        Undoes all import progress to the database for weather data.
        
        :raises ConnectionError: if the connection fails
        """
        try:
            self._connection._run("DELETE FROM weather;")
            print("Deleted all weather data from database")
        except Exception as e:
            print(f"Error deleting weather data: {str(e)}")
            raise

        # Reset the operation tracker
        weather_dir = os.path.join(self._path, "Weather")
        if os.path.exists(weather_dir):
            tracker = OperationTracker(weather_dir)
            tracker.reset_operation('import')