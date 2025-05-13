#!/usr/bin/env python3

from .PitchEnricher import PitchEnricher
import pandas as pd
import time
from datetime import datetime, timedelta

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
        # Add this to PitchTimestampEnricher._collect_batch_data before the return statement
        print(f"Games processed: {len(batch)}, Timestamps matched: {len(batch_pitch_data)}")

        return batch_pitch_data

    def _get_enrichment_data(self, game_pk):
        """
        Get pitch timestamps for a specific game using the MLB Stats API with fallback estimation
        
        :param game_pk: the MLB game ID
        :return: dictionary mapping pitch events to timestamps
        """
        try:
            game_data = self._get_game_data(game_pk)
            
            if not game_data or 'liveData' not in game_data or 'plays' not in game_data['liveData']:
                return {}
                
            all_plays = game_data['liveData']['plays'].get('allPlays', [])
            
            pitch_events = {}
            at_bats_needing_estimates = []
            
            # First pass: Process pitches with actual timestamps and identify at-bats needing estimates
            for play_idx, play in enumerate(all_plays):
                if 'playEvents' not in play or 'about' not in play:
                    continue
                    
                at_bat_index = play.get('atBatIndex') + 1  # 0 index in API
                
                # Get all pitch events for this at-bat
                pitch_events_in_at_bat = [
                    event for event in play['playEvents'] 
                    if event.get('type') == 'pitch'
                ]
                
                # Count pitches with and without timestamps
                pitches_with_timestamp = sum(1 for event in pitch_events_in_at_bat if 'startTime' in event)
                total_pitches = len(pitch_events_in_at_bat)
                
                # If all pitches have timestamps, process normally
                if pitches_with_timestamp == total_pitches and total_pitches > 0:
                    for event in pitch_events_in_at_bat:
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
                
                # If some or all pitches are missing timestamps, queue for estimation
                elif total_pitches > 0:
                    # Try to get start and end times
                    start_time = None
                    end_time = None
                    
                    # Get start time from play's about section
                    if 'startTime' in play['about']:
                        start_time = play['about']['startTime']
                    
                    # Get end time from play's about section or next play's start time
                    if 'endTime' in play['about']:
                        end_time = play['about']['endTime']
                    elif play_idx < len(all_plays) - 1 and 'about' in all_plays[play_idx + 1]:
                        end_time = all_plays[play_idx + 1]['about'].get('startTime')
                    
                    if start_time and end_time:
                        at_bats_needing_estimates.append({
                            'at_bat_index': at_bat_index,
                            'start_time': start_time,
                            'end_time': end_time,
                            'pitches': pitch_events_in_at_bat,
                            'total_pitches': total_pitches
                        })
            
            # Second pass: Generate estimated timestamps for at-bats that need them
            for at_bat_data in at_bats_needing_estimates:
                estimated_timestamps = self._estimate_pitch_timestamps(
                    at_bat_data['start_time'],
                    at_bat_data['end_time'],
                    at_bat_data['pitches']
                )
                
                # Apply estimated timestamps
                if estimated_timestamps:
                    at_bat_index = at_bat_data['at_bat_index']
                    for idx, event in enumerate(at_bat_data['pitches']):
                        if idx < len(estimated_timestamps):
                            pitch_number = event.get('pitchNumber')
                            if pitch_number is None:
                                continue
                            
                            # Only use estimate if there's no actual timestamp
                            pitch_time = event.get('startTime') or estimated_timestamps[idx]
                            
                            pitch_data = {
                                'atBatIndex': at_bat_index,
                                'pitchNumber': pitch_number,
                                'timestamp': pitch_time,
                                'estimated': 'startTime' not in event
                            }
                            
                            if 'details' in event and 'type' in event['details']:
                                pitch_data['type'] = event['details']['type'].get('code')
                            
                            key = f"{at_bat_index}_{pitch_number}"
                            pitch_events[key] = pitch_data
            
            return pitch_events
            
        except Exception as e:
            print(f"Error getting timestamps for game {game_pk}: {e}")
            return {}

    def _estimate_pitch_timestamps(self, start_time_str, end_time_str, pitches):
        """
        Estimate timestamps for pitches based on at-bat start and end times
        
        :param start_time_str: ISO timestamp string for at-bat start
        :param end_time_str: ISO timestamp string for at-bat end
        :param pitches: List of pitch events in the at-bat
        :return: List of estimated timestamp strings for each pitch
        """
        try:
            # Parse start and end times
            start_time = self._parse_iso_timestamp(start_time_str)
            end_time = self._parse_iso_timestamp(end_time_str)
            
            if not start_time or not end_time:
                return []
                
            # Calculate timespan
            timespan = end_time - start_time
            
            # If timespan is unreasonably long (> 1 hour), use a reasonable default
            if timespan > timedelta(hours=1):
                # Use 20 seconds per pitch as a reasonable average
                timespan = timedelta(seconds=20 * len(pitches))
            
            # If we still have a valid timespan and pitches, distribute timestamps
            if timespan.total_seconds() > 0 and len(pitches) > 0:
                # Calculate interval between pitches
                interval = timespan / len(pitches)
                
                # Generate timestamps
                timestamps = []
                for i in range(len(pitches)):
                    estimated_time = start_time + (interval * i)
                    timestamps.append(estimated_time.strftime('%Y-%m-%dT%H:%M:%S.000Z'))
                
                return timestamps
            
            return []
        
        except Exception as e:
            print(f"Error estimating pitch timestamps: {e}")
            return []

    def _parse_iso_timestamp(self, timestamp_str):
        """
        Parse ISO 8601 timestamp string to datetime object
        
        :param timestamp_str: ISO 8601 timestamp string
        :return: datetime object or None if parsing fails
        """
        if not timestamp_str:
            return None
            
        try:
            # Handle timestamps with or without milliseconds and Z timezone
            if '.' in timestamp_str:
                if timestamp_str.endswith('Z'):
                    dt = datetime.strptime(timestamp_str[:-1], '%Y-%m-%dT%H:%M:%S.%f')
                else:
                    dt = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S.%f')
            else:
                if timestamp_str.endswith('Z'):
                    dt = datetime.strptime(timestamp_str[:-1], '%Y-%m-%dT%H:%M:%S')
                else:
                    dt = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')
                    
            return dt
        except Exception:
            return None

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
        Uses a more flexible matching approach to handle discrepancies
        
        :param pitch_data: dictionary of pitch data from database
        :param timestamps: dictionary of pitch events with timestamps
        :return: matched timestamp or None
        """
        at_bat = pitch_data['at_bat_number']
        pitch_number = pitch_data['pitch_number']
        
        if at_bat is None or pitch_number is None:
            return None
            
        # First try exact match
        key = f"{at_bat}_{pitch_number}"
        if key in timestamps:
            return timestamps[key]['timestamp']

        # If exact match fails, try to find the closest pitch in the same at-bat
        at_bat_pitches = []
        for match_key, match_data in timestamps.items():
            if match_data['atBatIndex'] == at_bat:
                at_bat_pitches.append((match_data['pitchNumber'], match_key))
        
        # No pitches found for this at-bat
        if not at_bat_pitches:
            return None
        
        # Sort by pitch number
        at_bat_pitches.sort()
        
        # Find the closest pitch number
        closest_diff = float('inf')
        closest_key = None
        
        for p_num, p_key in at_bat_pitches:
            diff = abs(p_num - pitch_number)
            if diff < closest_diff:
                closest_diff = diff
                closest_key = p_key
        
        # If we found a pitch within reasonable distance (max 2 pitches away)
        if closest_diff <= 2 and closest_key in timestamps:
            print(f"Using close match: at-bat {at_bat}, DB pitch {pitch_number} -> API pitch {timestamps[closest_key]['pitchNumber']} (diff: {closest_diff})")
            return timestamps[closest_key]['timestamp']
            
        return None

    def _update_batch_data(self, batch_data):
        """Update the database with timestamp information with improved error reporting."""
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
                print("No pitches to update - all already have timestamps")
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
            
            # Track invalid timestamps
            invalid_timestamps = 0
            valid_updates = []
            
            # Validate timestamp format before building SQL
            for pitch_id, timestamp in batch_data.items():
                if timestamp != 'NULL' and timestamp.startswith("'") and timestamp.endswith("'"):
                    valid_updates.append(f"({pitch_id}, {timestamp})")
                else:
                    invalid_timestamps += 1
            
            if invalid_timestamps > 0:
                print(f"Warning: {invalid_timestamps} invalid timestamp values skipped")
            
            if not valid_updates:
                print("No valid timestamps to update")
                self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_timestamp_updates;")
                return 0
                
            # Insert all our pitch_id/timestamp pairs
            values = ", ".join(valid_updates)
            insert_query = f"""
                INSERT INTO temp_timestamp_updates (pitch_id, pitch_timestamp)
                VALUES {values};
            """
            
            try:
                self._sqlalchemy.execute(insert_query)
            except Exception as e:
                print(f"Error inserting timestamp data: {e}")
                print(f"Sample values: {valid_updates[:2]}")
                self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_timestamp_updates;")
                return 0
            
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
            print(f"Successfully updated {updated_count} of {before_count} pitches with timestamps")
            
            return updated_count
                
        except Exception as e:
            print(f"Error batch updating pitch timestamps: {e}")
            try:
                self._sqlalchemy.execute("DROP TEMPORARY TABLE IF EXISTS temp_timestamp_updates;")
            except:
                pass
            return 0
        
    def _ensure_prerequisites(self, batch_data):
        """
        No prerequisites needed for timestamp enrichment.
        
        :param batch_data: Dictionary mapping pitch_id to timestamp
        """
        pass