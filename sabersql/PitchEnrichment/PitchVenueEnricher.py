#!/usr/bin/env python3

from .PitchEnricher import PitchEnricher
import time
import pandas as pd
class PitchVenueEnricher(PitchEnricher):
    """
    Enriches pitch data with venue information from the MLB Stats API.
    Now uses a normalized approach with a game_venue mapping table.
    """

    def __init__(self, path, connection):
        """Initialize the venue enricher."""
        super().__init__(path, connection, "game_pk")  # We don't need a specific column name now

    def _get_operation_name(self):
        """Get the operation name for tracking."""
        return "venue_enrichment"
    
    def _get_enrichment_type(self):
        """Get the type of enrichment."""
        return "venue"
    
    def _ensure_database_structure(self):
        """Ensure venue table and game_venue mapping table exist."""
        try:
            # Ensure venue table exists
            query = "SHOW TABLES LIKE 'venue';"
            df = self._sqlalchemy.read_sql(query)
            
            if df.empty:
                from ..Schemas import _venue
                self._sqlalchemy.execute(_venue)
                print("Created venue table")
            
            # Create game_venue mapping table if it doesn't exist
            query = "SHOW TABLES LIKE 'game_venue';"
            df = self._sqlalchemy.read_sql(query)
            
            if df.empty:
                query = """
                CREATE TABLE game_venue (
                  game_pk INT PRIMARY KEY,
                  venue_id INT,
                  FOREIGN KEY (venue_id) REFERENCES venue(venue_id)
                ) COMMENT 'Mapping table between games and venues';
                """
                self._sqlalchemy.execute(query)
                print("Created game_venue mapping table")
            
        except Exception as e:
            print(f"Error ensuring database structure: {e}")
    
    def _get_appropriate_batch_size(self, max_batch_size):
        """Get appropriate batch size for venue enrichment."""
        return min(max_batch_size, 200)  # Can use larger batches now with simplified approach
    
    def _collect_batch_data(self, batch, tracker):
        """Collect venue data for a batch of games."""
        batch_venue_data = {}
        
        for i, game_data in enumerate(batch):
            try:
                game_pk, game_date = game_data
                venue_info = self._get_enrichment_data(game_pk)
                
                if venue_info and 'venue_id' in venue_info:
                    batch_venue_data[game_pk] = venue_info['venue_id']
                    
            except Exception as e:
                print(f"Error processing game: {str(e)}")
                if tracker:
                    tracker.record_error(self._get_operation_name(), e, game_data=game_data)
        
        return batch_venue_data
    
    def _update_batch_data(self, batch_data):
        """Update the game_venue table with venue information."""
        try:
            if not batch_data:
                return 0
            
            # First check which mappings already exist
            game_pks = list(batch_data.keys())
            # Convert list of game_pks to a comma-separated string for direct inclusion in query
            game_pks_str = ", ".join(str(pk) for pk in game_pks)
            
            query = f"""
                SELECT game_pk 
                FROM game_venue 
                WHERE game_pk IN ({game_pks_str})
            """
            
            existing_df = self._sqlalchemy.read_sql(query)
            existing_games = set(existing_df['game_pk'].tolist() if not existing_df.empty else [])
            
            # Filter out games that already have venue mappings
            new_mappings = {
                game_pk: venue_id 
                for game_pk, venue_id in batch_data.items() 
                if game_pk not in existing_games
            }
            
            if not new_mappings:
                return 0
            
            # Create temporary table for efficient insert
            self._sqlalchemy.execute("""
                CREATE TEMPORARY TABLE IF NOT EXISTS temp_game_venue (
                    game_pk INT,
                    venue_id INT
                );
            """)
            
            # Clear any existing data
            self._sqlalchemy.execute("TRUNCATE TABLE temp_game_venue;")
            
            # Insert all our game_pk/venue_id pairs
            values = ", ".join([f"({game_pk}, {venue_id})" for game_pk, venue_id in new_mappings.items()])
            self._sqlalchemy.execute(f"""
                INSERT INTO temp_game_venue (game_pk, venue_id)
                VALUES {values};
            """)
            
            # Insert into game_venue table, ignoring duplicates
            self._sqlalchemy.execute("""
                INSERT IGNORE INTO game_venue (game_pk, venue_id)
                SELECT game_pk, venue_id FROM temp_game_venue;
            """)
            
            # Clean up
            self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_game_venue;")
            
            # Return count of new mappings added
            return len(new_mappings)
                    
        except Exception as e:
            print(f"Error batch updating game venues: {e}")
            try:
                self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_game_venue;")
            except:
                pass
            return 0

    def _get_enrichment_data(self, game_pk):
        """
        Get venue information for a specific game using the MLB Stats API
        
        :param game_pk: the MLB game ID
        :return: dictionary with venue information
        """
        try:
            game_data = self._get_game_data(game_pk)
            
            if not game_data or 'gameData' not in game_data or 'venue' not in game_data['gameData']:
                return {}
                
            venue_data = game_data['gameData']['venue']
            
            venue_info = {
                'venue_id': venue_data.get('id'),
                'name': venue_data.get('name'),
                'location_city': None,
                'location_state': None,
                'location_address': None,
                'location_latitude': None,
                'location_longitude': None,
                'timezone': None,
                'field_type': None,
                'roof_type': None,
                'elevation': None,
                'azimuthAngle': None,
            }
            
            if 'location' in venue_data:
                location = venue_data['location']
                venue_info.update({
                    'location_city': location.get('city'),
                    'location_state': location.get('state'),
                    'location_address': location.get('address'),
                    'azimuthAngle': location.get('azimuthAngle'),
                    'elevation': location.get('elevation')
                })
                
                if 'defaultCoordinates' in location:
                    coords = location['defaultCoordinates']
                    venue_info.update({
                        'location_latitude': coords.get('latitude'),
                        'location_longitude': coords.get('longitude'),
                        
                    })
                
            if 'timeZone' in venue_data:
                venue_info['timezone'] = venue_data['timeZone'].get('id')
            
            if 'fieldInfo' in venue_data:
                field_info = venue_data['fieldInfo']
                venue_info.update({
                    'field_type': field_info.get('turfType'),
                    'roof_type': field_info.get('roofType'),
                })
            
            return venue_info
            
        except Exception as e:
            print(f"Error getting venue info for game {game_pk}: {e}")
            return {}
       
    def _insert_venue(self, venue_info):
        """
        Insert a new venue into the venue table
        
        :param venue_info: dictionary with venue information
        """
        try:
            columns = []
            values = []
            
            for key, value in venue_info.items():
                if value is not None:
                    columns.append(key)
                    if isinstance(value, str):
                        values.append(f"'{value}'")
                    else:
                        values.append(str(value))
            
            query = f"INSERT INTO venue ({', '.join(columns)}) VALUES ({', '.join(values)});"
            self._sqlalchemy.execute(query)
            
            print(f"Inserted venue ID {venue_info['venue_id']} ({venue_info.get('name')}) into venue table")
            
        except Exception as e:
            print(f"Error inserting venue: {e}")
    
    def _update_venue(self, venue_info):
        """
        Update an existing venue in the venue table
        
        :param venue_info: dictionary with venue information
        """
        try:
            venue_id = venue_info['venue_id']
            
            updates = []
            for key, value in venue_info.items():
                if key != 'venue_id' and value is not None:
                    if isinstance(value, str):
                        updates.append(f"{key} = '{value}'")
                    else:
                        updates.append(f"{key} = {value}")
            
            if updates:
                query = f"UPDATE venue SET {', '.join(updates)} WHERE venue_id = {venue_id};"
                self._sqlalchemy.execute(query)
                
                print(f"Updated venue ID {venue_id} ({venue_info.get('name')}) in venue table")
            
        except Exception as e:
            print(f"Error updating venue: {e}")
     
    def _ensure_venue_exists(self, venue_info):
        """
        Ensure the venue exists in the venue table
        
        :param venue_info: dictionary with venue information
        """
        if not venue_info or 'venue_id' not in venue_info:
            return
            
        venue_id = venue_info['venue_id']
        
        query = f"SELECT venue_id FROM venue WHERE venue_id = {venue_id};"
        df = self._sqlalchemy.read_sql(query)
        
        if df.empty:
            self._insert_venue(venue_info)

    def _ensure_prerequisites(self, batch_data):
        """
        Ensure all venues in the batch exist in the venue table.
        This is a batch operation to reduce database queries.
        
        :param batch_data: Dictionary mapping game_pk to venue_id
        """
        if not batch_data:
            return
        
        # Get all unique venue IDs from the batch
        venue_ids = set(batch_data.values())
        
        if not venue_ids:
            return
        
        # Check which venues already exist in the database
        venue_list = ", ".join(str(venue_id) for venue_id in venue_ids)
        query = f"SELECT venue_id FROM venue WHERE venue_id IN ({venue_list});"
        df = self._sqlalchemy.read_sql(query)
        
        existing_venues = set(df['venue_id'].tolist()) if not df.empty else set()
        
        # Get list of venue IDs that need to be created
        missing_venues = venue_ids - existing_venues
        
        if not missing_venues:
            return
        
        print(f"Need to create {len(missing_venues)} new venues")
        
        # Create missing venues
        for venue_id in missing_venues:
            # Find a game that uses this venue
            for game_pk, v_id in batch_data.items():
                if v_id == venue_id:
                    # Get venue info for this game
                    venue_info = self._get_enrichment_data(game_pk)
                    if venue_info and 'venue_id' in venue_info:
                        self._insert_venue(venue_info)
                    break
    
    def _get_games_needing_enrichment(self, start_date=None, end_date=None):
        """
        Get all games that don't have venue mappings, filtered by date range if provided
        
        :param start_date: Optional start date in YYYY-MM-DD format
        :param end_date: Optional end date in YYYY-MM-DD format
        :return: List of tuples (game_pk, game_date)
        """
        query = """
            SELECT DISTINCT p.game_pk, p.game_date 
            FROM pitch p
            LEFT JOIN game_venue gv ON p.game_pk = gv.game_pk
            WHERE gv.game_pk IS NULL 
        """
        
        # Add date range filter if provided
        if start_date:
            query += f" AND p.game_date >= '{start_date}'"
        if end_date:
            query += f" AND p.game_date <= '{end_date}'"
            
        query += " ORDER BY p.game_date;"
        
        df = self._sqlalchemy.read_sql(query)
        
        if df.empty:
            return []
        
        return list(zip(df['game_pk'].tolist(), df['game_date'].tolist()))
  
    def _get_date_range_info(self, start_date=None, end_date=None):
        """
        Get information about the date range and count of games in the database
        
        :param start_date: Optional start date in YYYY-MM-DD format
        :param end_date: Optional end date in YYYY-MM-DD format
        :return: Dictionary with date range information
        """
        query = """
            SELECT 
                MIN(p.game_date) as min_date,
                MAX(p.game_date) as max_date,
                COUNT(DISTINCT p.game_pk) as total_count,
                SUM(CASE WHEN gv.game_pk IS NULL THEN 1 ELSE 0 END) as missing_count
            FROM (
                SELECT DISTINCT game_pk, game_date 
                FROM pitch
            ) p
            LEFT JOIN game_venue gv ON p.game_pk = gv.game_pk
        """
        
        # Add date range filter if provided
        where_clauses = []
        if start_date:
            where_clauses.append(f"p.game_date >= '{start_date}'")
        if end_date:
            where_clauses.append(f"p.game_date <= '{end_date}'")
            
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