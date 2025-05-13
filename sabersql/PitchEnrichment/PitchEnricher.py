#!/usr/bin/env python3

import os
import json
import statsapi
import time
import pandas as pd
from datetime import datetime
from ..Utilities import _shell
from ..OperationTracker import OperationTracker

class PitchEnricher:
    """
    Base class for enriching pitch data with additional information from the MLB Stats API.
    """

    def __init__(self, path, connection, column_name):
        """
        Initializes a PitchEnricher based on the path to the SaberSQL data and a MySQLConnection

        :param path: the path to the folder for all SaberSQL data
        :param connection: a MySQLConnection to the database to import data to
        """
        self._path = path
        self._connection = connection
        self.column_name = column_name
        self._enrichment_dir = os.path.join(self._path, "Enrichment")
        self._game_data_dir = os.path.join(self._enrichment_dir, "game_data")
        from ..SQLAlchemyConnector import SQLAlchemyConnector
        self._sqlalchemy = SQLAlchemyConnector(
            username=connection._username,
            password=connection._password,
            database=connection._database,
            address=connection._address,
        )

        _shell(f"mkdir -p {self._enrichment_dir}")
        _shell(f"mkdir -p {self._game_data_dir}")
    
    def _get_game_data(self, game_pk):
        """
        Get game data for a specific game using the MLB Stats API or from saved data
            
        :param game_pk: the MLB game ID
        :return: game data dictionary
        """
        try:
            file_path = os.path.join(self._game_data_dir, f"game_{game_pk}.json")
            
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    return json.load(f)
            
            game_data = statsapi.get('game', {'gamePk': game_pk})
            
            with open(file_path, 'w') as f:
                json.dump(game_data, f)
            time.sleep(0.25)
            return game_data
            
        except Exception as e:
            print(f"Error getting game data for game {game_pk}: {e}")
            return None


    def enrich_pitches(self, start_date=None, end_date=None, batch_size=1000, handler=lambda *args: None):
        """Main public method that orchestrates the enrichment process."""
        try:
            tracker = OperationTracker(self._enrichment_dir)
            
            # Ensure required database structures exist
            self._ensure_database_structure()
            
            # Get date range text for logging
            date_range_text = self._get_date_range_text(start_date, end_date)
            
            # Start operation tracking
            tracker.start_operation(self._get_operation_name(), 
                                   start_date=start_date, 
                                   end_date=end_date,
                                   batch_size=batch_size)
            
            # Get info about data that needs processing
            info = self._get_date_range_info(start_date, end_date)
            if not info or not info.get('missing_count'):
                message = f"No pitches need {self._get_enrichment_type()} enrichment{date_range_text}"
                tracker.complete_operation(self._get_operation_name(), success=True, message=message)
                handler(1, status=message)
                return
            
            # Log current status
            print(f"Date range: {info.get('min_date')} to {info.get('max_date')}")
            print(f"Total pitches: {info.get('total_count')}")
            print(f"Pitches missing {self._get_enrichment_type()}: {info.get('missing_count')}")
            
            # Process data in batches
            processed_count = self._process_games_template(start_date, end_date, batch_size, handler, tracker)
            
            # Get final status for reporting
            remaining_info = self._get_date_range_info(start_date, end_date)
            
            # Complete operation tracking
            tracker.complete_operation(self._get_operation_name(), success=True,
                                     start_date=info.get('min_date'),
                                     end_date=info.get('max_date'),
                                     total_pitches=info.get('total_count'),
                                     initial_missing=info.get('missing_count'),
                                     remaining_missing=remaining_info.get('missing_count', 0),
                                     processed_count=processed_count)
            
            handler(1, status=f"{self._get_enrichment_type().capitalize()} enrichment complete{date_range_text}")
            
        except Exception as e:
            print(f"Error during {self._get_enrichment_type()} enrichment: {e}")
            if 'tracker' in locals():
                tracker.complete_operation(self._get_operation_name(), success=False, error=e)
            handler(1, status=f"{self._get_enrichment_type().capitalize()} enrichment failed: {str(e)}")
            raise
        finally:
            self.close()
  
    def _process_games_template(self, start_date=None, end_date=None, batch_size=1000, handler=lambda *args: None, tracker=None):
        """Template method that defines the skeleton of the batch processing algorithm."""
        games_data = self._get_games_needing_enrichment(start_date, end_date)
        
        if not games_data:
            print(f"No games found that need {self._get_enrichment_type()} enrichment")
            return 0
                
        print(f"Found {len(games_data)} games that need {self._get_enrichment_type()} enrichment")
        
        # Get appropriate batch size for this enricher type
        batch_size = self._get_appropriate_batch_size(batch_size)
        processed_count = 0
        
        for batch_index in range(0, len(games_data), batch_size):
            batch = games_data[batch_index:batch_index + batch_size]
            batch_progress = batch_index / len(games_data)
            
            handler(batch_progress * 0.9, 
                  status=f"Processing games {batch_index+1}-{batch_index+len(batch)}/{len(games_data)}")
            
            # Collect data for this batch - delegated to child classes
            batch_data = self._collect_batch_data(batch, tracker)
            
            if batch_data:
                self._ensure_prerequisites(batch_data)

            # Update database with collected data - delegated to child classes
            if batch_data:
                updated = self._update_batch_data(batch_data)
                processed_count += updated
                print(f"Updated {updated} pitches in batch")
            
            batch_complete = (batch_index + len(batch)) / len(games_data)
            handler(batch_complete * 0.9, 
                  status=f"Completed games {batch_index+1}-{batch_index+len(batch)}/{len(games_data)}")
        
        return processed_count   
    
    def _get_enrichment_data(self, game_pk):
        """
        Abstract method
        
        :return: game_pk enrichment data
        """
        raise NotImplementedError("Subclasses must implement this method")

    def _get_operation_name(self):
        """Get the name of this operation for tracking."""
        raise NotImplementedError("Child classes must implement this method")
    
    def _get_enrichment_type(self):
        """Get a descriptive name for this type of enrichment (e.g., 'venue', 'timestamp')."""
        raise NotImplementedError("Child classes must implement this method")
    
    def _ensure_database_structure(self):
        """Ensure any required database structures (tables, columns) exist."""
        raise NotImplementedError("Child classes must implement this method")
    
    def _ensure_prerequisites(self, batch_data):
        """
        Ensure any prerequisites are met before updating the database.
        This is a batch operation to reduce database queries.
        
        :param batch_data: Dictionary of data collected for this batch
        """
        raise NotImplementedError("Child classes must implement this method")
    
    def _get_appropriate_batch_size(self, max_batch_size):
        """Get the appropriate batch size for this enricher type."""
        raise NotImplementedError("Child classes must implement this method")
    
    def _collect_batch_data(self, batch, tracker):
        """
        Collect data for a batch of games.
        
        :param batch: List of (game_pk, game_date) tuples
        :param tracker: Operation tracker for error reporting
        :return: Dictionary of data to update (format depends on enricher type)
        """
        raise NotImplementedError("Child classes must implement this method")
    
    def _update_batch_data(self, batch_data):
        """
        Update the database with batch data.
        
        :param batch_data: Dictionary of data collected for this batch
        :return: Number of records updated
        """
        raise NotImplementedError("Child classes must implement this method")
    
    def _get_games_needing_enrichment(self, start_date=None, end_date=None):
        """
        Get all games that have pitches missing enrichment column, filtered by date range if provided
        
        :param start_date: Optional start date in YYYY-MM-DD format
        :param end_date: Optional end date in YYYY-MM-DD format
        :return: List of tuples (game_pk, game_date)
        """
        query = f"""
            SELECT DISTINCT game_pk, game_date 
            FROM pitch 
            WHERE {self.column_name} IS NULL 
        """
        
        # Add date range filter if provided
        if start_date:
            query += f" AND game_date >= '{start_date}'"
        if end_date:
            query += f" AND game_date <= '{end_date}'"
            
        query += " ORDER BY game_date;"
        
        df = self._sqlalchemy.read_sql(query)
        
        if df.empty:
            return []
        
        return list(zip(df['game_pk'].tolist(), df['game_date'].tolist()))
  
    def _get_date_range_info(self, start_date=None, end_date=None):
        """
        Get information about the date range and count of pitches in the database
        
        :param start_date: Optional start date in YYYY-MM-DD format
        :param end_date: Optional end date in YYYY-MM-DD format
        :return: Dictionary with date range information
        """
        query = f"""
            SELECT 
                MIN(game_date) as min_date,
                MAX(game_date) as max_date,
                COUNT(*) as total_count,
                SUM(CASE WHEN {self.column_name} IS NULL THEN 1 ELSE 0 END) as missing_count
            FROM pitch
        """
        
        # Add date range filter if provided
        where_clauses = []
        if start_date:
            where_clauses.append(f"game_date >= '{start_date}'")
        if end_date:
            where_clauses.append(f"game_date <= '{end_date}'")
            
        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"
        
        df = self._sqlalchemy.read_sql(query)
        
        if df.empty:
            return None
            
        return {
            'min_date': df.iloc[0]['min_date'].strftime('%Y-%m-%d') if not pd.isna(df.iloc[0]['min_date']) else None,
            'max_date': df.iloc[0]['max_date'].strftime('%Y-%m-%d') if not pd.isna(df.iloc[0]['max_date']) else None,
            'total_count': int(df.iloc[0]['total_count']) if not pd.isna(df.iloc[0]['total_count']) else 0,
            'missing_count': int(df.iloc[0]['missing_count']) if not pd.isna(df.iloc[0]['missing_count']) else 0
        }
   
    def _get_date_range_text(self, start_date, end_date):
        """Get a descriptive text for the date range."""
        if start_date and end_date:
            return f" for period {start_date} to {end_date}"
        elif start_date:
            return f" from {start_date} onwards"
        elif end_date:
            return f" up to {end_date}"
        return ""
    
    def close(self):
        """
        Close any open connections
        """
        if hasattr(self, '_sqlalchemy'):
            self._sqlalchemy.close()
