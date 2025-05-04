#!/usr/bin/env python3

import os
import glob
from . import Utilities
import pandas as pd
from sqlalchemy import text
from .ProgressHandler import ProgressHandler


class PImporter:

    def __init__(self, path, connection):
        """
        Initializes a PImporter based on the path to the SaberSQL data and a MySQLConnection

        :param path: the path to the folder for all SaberSQL data
        :param connection: a MySQLConnection to the database to import data to
        """

        self._path = path
        self._connection = connection

        self.__key_pair = [
            ("key_person", "person_id"),
            ("key_mlbam", "mlbam"),
            ("key_retro", "retro"),
            ("key_bbref", "bbref"),
            ("key_fangraphs", "fangraphs"),
            ("name_last", "lastname"),
            ("name_first", "firstname"),
            ("name_given", "givenname"),
            ("name_suffix", "name_suffix"),
            ("name_matrilineal", "matrilinealname"),
            ("name_nick", "nickname"),
            ("birth_year", "birth_year"),
            ("birth_month", "birth_month"),
            ("birth_day", "birth_day"),
            ("death_year", "death_year"),
            ("death_month", "death_month"),
            ("death_day", "death_day"),
            ("pro_played_first", "pro_played_first"),
            ("pro_played_last", "pro_played_last"),
            ("mlb_played_first", "mlb_played_first"),
            ("mlb_played_last", "mlb_played_last"),
            ("col_played_first", "col_played_first"),
            ("col_played_last", "col_played_last"),
            ("pro_managed_first", "pro_managed_first"),
            ("pro_managed_last", "pro_managed_last"),
            ("mlb_managed_first", "mlb_managed_first"),
            ("mlb_managed_last", "mlb_managed_last"),
            ("col_managed_first", "col_managed_first"),
            ("col_managed_last", "col_managed_last"),
            ("pro_umpired_first", "pro_umpired_first"),
            ("pro_umpired_last", "pro_umpired_last"),
            ("mlb_umpired_first", "mlb_umpired_first"),
            ("mlb_umpired_last", "mlb_umpired_last")
        ]

    def import_people_data(self, handler=lambda *args: None):
        """
        Imports all downloaded people data to MySQL database

        :param handler: a function that takes in a double, representing the completion percentage of the import
        :raises ConnectionError: if the connection fails
        """

        status = "Importing people data"
        handler(0, status=status)
        progress_handler = ProgressHandler(os.path.join(self._path, "Person"))
        progress = progress_handler.get_progress()
        
        if progress != ProgressHandler.FINISHED:
            if progress == ProgressHandler.STARTED:
                self.__undo_sql_import()
            progress_handler.start_progress()

            # Get all people CSV files
            person_dir = os.path.join(self._path, "Person")
            csv_files = glob.glob(os.path.join(person_dir, "people-*.csv"))
            
            if not csv_files:
                print("No people CSV files found to import.")
                handler(1, status="No people data to import")
                return
            
            total_files = len(csv_files)
            files_processed = 0
            
            # Import each CSV file
            for csv_file in csv_files:
                try:
                    print(f"Importing {os.path.basename(csv_file)}...")
                    self.__import_people_from_file(csv_file, lambda progress: handler(
                        (files_processed + progress) / total_files, 
                        status=f"Importing people data ({files_processed+1}/{total_files})"
                    ))
                    files_processed += 1
                    handler(files_processed / total_files, 
                            status=f"Importing people data ({files_processed}/{total_files})")
                except Exception as e:
                    print(f"Error importing {csv_file}: {str(e)}")
            
            progress_handler.end_progress()
        
        handler(1, status=status)

    def unimport_people_data(self, handler=lambda *args: None):
        """
        Undoes import of all people data from MySQL database

        :param handler: a function that takes in a double, representing the completion percentage of the import undoing
        :raises ConnectionError: if the connection fails
        """

        status = "Undoing people import"
        handler(0, status=status)
        progress_handler = ProgressHandler(os.path.join(self._path, "Person"))
        progress = progress_handler.get_progress()
        if progress != ProgressHandler.NONE:
            progress_handler.start_progress()
            self.__undo_sql_import()
        handler(1, status=status)

    def __import_people_from_file(self, filepath, handler):
        """
        Import people data from a specific CSV file

        :param filepath: Path to the CSV file
        :param handler: Progress handler function
        """
        batch_size = 1000

        try:
            dataframe = Utilities._import_csv(filepath)
            
            # Skip if empty
            length = len(dataframe)
            if length == 0:
                print(f"  {os.path.basename(filepath)} is empty, skipping.")
                return
                
            # Get database column names from key_pair mapping
            column_names = [x[1] for x in self.__key_pair]
            
            # Map column indices to use from the dataframe
            indices = []
            column_map = {}
            for i, col_name in enumerate(dataframe.columns):
                for csv_col, db_col in self.__key_pair:
                    if csv_col == col_name:
                        indices.append(i)
                        column_map[i] = db_col
                        break
            
            # Prepare the SQL insert statement
            columns_str = ", ".join(column_names)
            placeholders = ", ".join([":"+col for col in column_names])
            insert_query = f"INSERT INTO person ({columns_str}) VALUES ({placeholders})"
            
            # Process in batches
            rows_processed = 0
            batch_data = []
            
            for row in dataframe.values:
                # Create a dictionary for this row
                row_dict = {}
                for i, db_col in column_map.items():
                    cell = row[i]
                    # Convert to proper SQL format
                    if pd.isna(cell):
                        row_dict[db_col] = None
                    elif isinstance(cell, str) and cell.lower() == "null":
                        row_dict[db_col] = None
                    else:
                        row_dict[db_col] = cell
                
                # Make sure all expected columns are in the dictionary
                for col in column_names:
                    if col not in row_dict:
                        row_dict[col] = None
                
                batch_data.append(row_dict)
                rows_processed += 1
                
                # Execute batch when it reaches the batch size
                if len(batch_data) >= batch_size:
                    with self._connection._engine.connect() as conn:
                        conn.execute(text(insert_query), batch_data)
                        conn.commit()
                    batch_data = []
                    handler(rows_processed/length)
            
            # Insert any remaining records
            if batch_data:
                with self._connection._engine.connect() as conn:
                    conn.execute(text(insert_query), batch_data)
                    conn.commit()
            
            print(f"  Successfully imported {length} records from {os.path.basename(filepath)}")
            
        except Exception as e:
            print(f"  Error processing {filepath}: {str(e)}")
            raise

    def __undo_sql_import(self):
        """
        Undoes all import progress to the database so far on a year

        :raises ConnectionError: if the connection fails
        """
        self._connection.execute("DELETE FROM person;")

        progress_file_path = os.path.join(self._path, "Person", "progress.dat")
        if os.path.exists(progress_file_path):
            os.remove(progress_file_path)