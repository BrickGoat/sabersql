#!/usr/bin/env python3

from .PitchEnricher import PitchEnricher
import time

class PitchVenueEnricher(PitchEnricher):
    """
    Enriches pitch data with venue information from the MLB Stats API.
    """

    def __init__(self, path, connection):
        """Initialize the venue enricher."""
        super().__init__(path, connection, "venue_id")

    def _get_operation_name(self):
        """Get the operation name for tracking."""
        return "venue_enrichment"
    
    def _get_enrichment_type(self):
        """Get the type of enrichment."""
        return "venue"
    
    def _ensure_database_structure(self):
        """Ensure venue table and column exist."""
        try:
            query = "SHOW TABLES LIKE 'venue';"
            df = self._connection.read_sql(query)
            
            if df.empty:
                from ..Schemas import _venue
                self._connection.execute(_venue)
                print("Created venue table")
            
            query = "SHOW COLUMNS FROM pitch LIKE 'venue_id';"
            df = self._connection.read_sql(query)
            
            if df.empty:
                query = """
                ALTER TABLE pitch ADD COLUMN venue_id INT COMMENT 'ID of the venue where the pitch was thrown';
                """
                self._connection.execute(query)
                print("Added venue_id column to pitch table")
                
                query = """
                ALTER TABLE pitch ADD CONSTRAINT fk_pitch_venue
                FOREIGN KEY (venue_id) REFERENCES venue(venue_id);
                """
                self._connection.execute(query)
                print("Added foreign key constraint to pitch.venue_id")
            
        except Exception as e:
            print(f"Error ensuring venue tables exist: {e}")
    
    def _get_appropriate_batch_size(self, max_batch_size):
        """Get appropriate batch size for venue enrichment."""
        return min(max_batch_size, 50)  # Venue updates are lightweight
    
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
        """Update the database with venue information."""
        try:
            if not batch_data:
                return 0
                
            game_pks = ", ".join(str(pk) for pk in batch_data.keys())
            
            # Get count before update
            before_query = f"""
                SELECT COUNT(*) as before_count
                FROM pitch
                WHERE game_pk IN ({game_pks}) AND venue_id IS NULL;
            """
            before_df = self._connection.read_sql(before_query)
            before_count = int(before_df.iloc[0]['before_count']) if not before_df.empty else 0
            
            if before_count == 0:
                return 0
                
            # Create temporary table
            self._connection.execute("""
                CREATE TEMPORARY TABLE IF NOT EXISTS temp_venue_updates (
                    game_pk INT,
                    venue_id INT
                );
            """)
            
            # Clear any existing data
            self._connection.execute("TRUNCATE TABLE temp_venue_updates;")
            
            # Insert all our game_pk/venue_id pairs
            values = ", ".join([f"({game_pk}, {venue_id})" for game_pk, venue_id in batch_data.items()])
            self._connection.execute(f"""
                INSERT INTO temp_venue_updates (game_pk, venue_id)
                VALUES {values};
            """)
            
            # Execute a single batch update via JOIN
            self._connection.execute("""
                UPDATE pitch p
                JOIN temp_venue_updates t ON p.game_pk = t.game_pk
                SET p.venue_id = t.venue_id
                WHERE p.venue_id IS NULL;
            """)
            
            # Count how many remain without venue_id
            after_query = f"""
                SELECT COUNT(*) as after_count
                FROM pitch
                WHERE game_pk IN ({game_pks}) AND venue_id IS NULL;
            """
            after_df = self._connection.read_sql(after_query)
            after_count = int(after_df.iloc[0]['after_count']) if not after_df.empty else 0
            
            # Clean up
            self._connection.execute("DROP TEMPORARY TABLE IF EXISTS temp_venue_updates;")
            
            # Calculate actual updated count
            updated_count = before_count - after_count
            return updated_count
                    
        except Exception as e:
            print(f"Error batch updating pitch venues: {e}")
            try:
                self._connection.execute("DROP TEMPORARY TABLE IF EXISTS temp_venue_updates;")
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
            self._connection.execute(query)
            
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
                self._connection.execute(query)
                
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
        df = self._connection.read_sql(query)
        
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
        df = self._connection.read_sql(query)
        
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