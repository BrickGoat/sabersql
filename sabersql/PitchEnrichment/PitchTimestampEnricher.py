#!/usr/bin/env python3

from .PitchEnricher import PitchEnricher
import pandas as pd
from datetime import datetime
import time

class PitchTimestampEnricher(PitchEnricher):
    """Enriches pitch data with timestamps from the MLB Stats API."""

    def __init__(self, path, connection):
        """Initialize the timestamp enricher."""
        super().__init__(path, connection, "pitch_timestamp")
    
    def _get_operation_name(self):
        """Get the operation name for tracking."""
        return "timestamp_enrichment"
    
    def _get_enrichment_type(self):
        """Get the type of enrichment."""
        return "timestamp"
    
    def _ensure_database_structure(self):
        """Ensure the pitch_timestamp column exists."""
        try:            
            query = "SHOW COLUMNS FROM pitch LIKE 'pitch_timestamp';"
            df = self._sqlalchemy.read_sql(query)
            
            if df.empty:
                self._sqlalchemy.execute(
                    "ALTER TABLE pitch ADD COLUMN pitch_timestamp DATETIME COMMENT 'Timestamp of the pitch from MLB Stats API';"
                )
                print("Added pitch_timestamp column to pitch table")
            else:
                print("pitch_timestamp column already exists")
        except Exception as e:
            print(f"Error ensuring timestamp column exists: {e}")
    
    def _get_appropriate_batch_size(self, max_batch_size):
        """Get appropriate batch size for timestamp enrichment."""
        return min(max_batch_size, 25)  # Smaller batches due to more data per game
    
    def _collect_batch_data(self, batch, tracker):
        """Collect timestamp data for a batch of games."""
        batch_pitch_data = {}
        
        for i, game_data in enumerate(batch):
            try:
                game_pk, game_date = game_data
                
                # Get timestamps for this game
                timestamps = self._get_enrichment_data(game_pk)
                
                if timestamps:
                    # Get pitches that need timestamps
                    pitches = self._get_pitches_for_game(game_pk)
                    
                    # Match pitches to timestamps
                    for pitch_id, pitch_data in pitches.items():
                        matched_timestamp = self._match_pitch_to_timestamp(pitch_data, timestamps)
                        
                        if matched_timestamp:
                            mysql_timestamp = self._convert_timestamp_to_mysql_format(matched_timestamp)
                            if mysql_timestamp != 'NULL':
                                # Add to batch update data - note the quotes around the timestamp value
                                batch_pitch_data[pitch_id] = f"'{mysql_timestamp}'"
                
                # Add small delay between API calls
                if i < len(batch) - 1:
                    time.sleep(0.5)
                    
            except Exception as e:
                print(f"Error processing game: {str(e)}")
                if tracker:
                    tracker.record_error(self._get_operation_name(), e, game_data=game_data)
        
        return batch_pitch_data
    
    def _update_batch_data(self, batch_data):
        """Update the database with timestamp information."""
        try:
            if not batch_data:
                return 0
                
            pitch_ids = ", ".join(str(pk) for pk in batch_data.keys())
            
            # Get count before update
            before_query = f"""
                SELECT COUNT(*) as before_count
                FROM pitch
                WHERE pitch_id IN ({pitch_ids}) AND pitch_timestamp IS NULL;
            """
            before_df = self._sqlalchemy.read_sql(before_query)
            before_count = int(before_df.iloc[0]['before_count']) if not before_df.empty else 0
            
            if before_count == 0:
                return 0
                
            # Create temporary table
            self._sqlalchemy.execute("""
                CREATE TEMPORARY TABLE IF NOT EXISTS temp_timestamp_updates (
                    pitch_id INT,
                    pitch_timestamp DATETIME
                );
            """)
            
            # Clear any existing data
            self._sqlalchemy.execute("TRUNCATE TABLE temp_timestamp_updates;")
            
            # Insert all our pitch_id/timestamp pairs
            values = ", ".join([f"({pitch_id}, {timestamp})" for pitch_id, timestamp in batch_data.items()])
            self._sqlalchemy.execute(f"""
                INSERT INTO temp_timestamp_updates (pitch_id, pitch_timestamp)
                VALUES {values};
            """)
            
            # Execute a single batch update via JOIN
            self._sqlalchemy.execute("""
                UPDATE pitch p
                JOIN temp_timestamp_updates t ON p.pitch_id = t.pitch_id
                SET p.pitch_timestamp = t.pitch_timestamp
                WHERE p.pitch_timestamp IS NULL;
            """)
            
            # Count how many remain without timestamp
            after_query = f"""
                SELECT COUNT(*) as after_count
                FROM pitch
                WHERE pitch_id IN ({pitch_ids}) AND pitch_timestamp IS NULL;
            """
            after_df = self._sqlalchemy.read_sql(after_query)
            after_count = int(after_df.iloc[0]['after_count']) if not after_df.empty else 0
            
            # Clean up
            self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_timestamp_updates;")
            
            # Calculate actual updated count
            updated_count = before_count - after_count
            return updated_count
            
        except Exception as e:
            print(f"Error batch updating pitch timestamps: {e}")
            try:
                self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_timestamp_updates;")
            except:
                pass
            return 0
    
    def _get_enrichment_data(self, game_pk):
        """
        Get pitch timestamps for a specific game using the MLB Stats API
        
        :param game_pk: the MLB game ID
        :return: dictionary mapping pitch events to timestamps
        """
        try:
            game_data = self._get_game_data(game_pk)
            
            if not game_data or 'liveData' not in game_data or 'plays' not in game_data['liveData']:
                return {}
                
            all_plays = game_data['liveData']['plays'].get('allPlays', [])
            
            pitch_events = {}
            
            for play in all_plays:
                if 'playEvents' not in play:
                    continue
                    
                at_bat_index = play.get('atBatIndex') + 1 # 0 index
                
                for event in play['playEvents']:
                    if event.get('type') == 'pitch' and 'startTime' in event:
                        pitch_number = event.get('pitchNumber')

                        if pitch_number is None:
                            continue

                        pitch_time = event.get('startTime')
                        pitch_data = {
                            'atBatIndex': at_bat_index,
                            'pitchNumber': pitch_number,
                            'timestamp': pitch_time,
                        }

                        if 'details' in event and 'type' in event['details']:
                            pitch_data['type'] = event['details']['type'].get('code')

                        key = f"{at_bat_index}_{pitch_number}"
                        pitch_events[key] = pitch_data
            
            return pitch_events
            
        except Exception as e:
            print(f"Error getting timestamps for game {game_pk}: {e}")
            return {}
      
    def _convert_timestamp_to_mysql_format(self, iso_timestamp):
        """
        Convert ISO 8601 timestamp to MySQL DATETIME format
        
        :param iso_timestamp: ISO 8601 timestamp from MLB Stats API (e.g. '2024-03-20T10:10:01.913Z')
        :return: Timestamp in MySQL DATETIME format (YYYY-MM-DD HH:MM:SS)
        """
        try:
            if '.' in iso_timestamp:
                # Handle timestamps with milliseconds and 'Z' timezone
                if iso_timestamp.endswith('Z'):
                    dt = datetime.strptime(iso_timestamp[:-1], '%Y-%m-%dT%H:%M:%S.%f')
                else:
                    dt = datetime.strptime(iso_timestamp, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                # Handle timestamps without milliseconds
                if iso_timestamp.endswith('Z'):
                    dt = datetime.strptime(iso_timestamp[:-1], '%Y-%m-%dT%H:%M:%S')
                else:
                    dt = datetime.strptime(iso_timestamp, '%Y-%m-%dT%H:%M:%S')
                    
            # Format to MySQL DATETIME format
            return dt.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            print(f"Error converting timestamp {iso_timestamp}: {e}")
            return 'NULL'

    def _get_pitches_for_game(self, game_pk):
        """
        Get all pitches for a specific game from the database that need timestamps
        
        :param game_pk: the MLB game ID
        :return: dictionary of pitch data keyed by pitch_id
        """
        query = f"""
            SELECT pitch_id, at_bat_number
            FROM pitch
            WHERE game_pk = {game_pk} AND {self.column_name} IS NULL
            ORDER BY at_bat_number, pitch_number;
        """     
        df = self._sqlalchemy.read_sql(query)
        
        if df.empty:
            return {}
        
        df['pitch_number'] = df.groupby('at_bat_number').cumcount() + 1 # statsapi pitch counting method differs from statcasts
        pitches = {}
        for _, row in df.iterrows():
            pitch_id = int(row['pitch_id'])
            pitches[pitch_id] = {
                'at_bat_number': int(row['at_bat_number']) if pd.notna(row['at_bat_number']) else None,
                'pitch_number': int(row['pitch_number']) if pd.notna(row['pitch_number']) else None,
            }
        
        return pitches
    
    def _match_pitch_to_timestamp(self, pitch_data, timestamps):
        """
        Match a pitch from our database to a timestamp from the API
        
        :param pitch_data: dictionary of pitch data from database
        :param timestamps: dictionary of pitch events with timestamps
        :return: matched timestamp or None
        """
        at_bat = pitch_data['at_bat_number']
        pitch_number = pitch_data['pitch_number']
        
        if at_bat is None or pitch_number is None:
            return None
            
        key = f"{at_bat}_{pitch_number}"
        if key in timestamps:
            return timestamps[key]['timestamp']

        return None
    
    def _ensure_prerequisites(self, batch_data):
        """
        No prerequisites needed for timestamp enrichment.
        
        :param batch_data: Dictionary mapping pitch_id to timestamp
        """
        pass