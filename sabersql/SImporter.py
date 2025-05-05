#!/usr/bin/env python3

from datetime import datetime
import os
import pandas as pd
from .ProgressHandler import ProgressHandler

class SImporter:

    def __init__(self, path, connection):
        """
        Initializes a SImporter based on the path to the SaberSQL data and a MySQLConnection

        :param path: the path to the folder for all SaberSQL data
        :param connection: a MySQLConnection to the database to import data to
        """

        self._path = path
        self._connection = connection

    def import_statcast_data(self, year=None, handler=lambda *args: None):
        """
        Imports all downloaded BaseballSavant data to MySQL database

        :param year: the year to be imported; defaults to all years 1999 to present
        :param handler: a function that takes in a double, representing the completion percentage of the import
        :raises ConnectionError: if the connection fails
        """

        if year:
            years = [year]
        else:
            years = [y for y in range(1999, datetime.now().year + 1)]

        year_prog = 0
        handler(0, status="Importing Statcast data")
        for year in years:
            savant_path = os.path.join(self._path, "BaseballSavant", str(year))
            
            # Skip if directory doesn't exist
            if not os.path.exists(savant_path):
                year_prog += 1
                handler(year_prog / len(years), status=f"No data for {year}, skipping")
                continue
                
            progress_handler = ProgressHandler(savant_path)
            progress = progress_handler.get_progress()
            if progress != ProgressHandler.FINISHED:
                if progress == ProgressHandler.STARTED:
                    self.__undo_sql_import(year)
                progress_handler.start_progress()

                files = self.__get_valid_data_files(year)
                if not files:
                    # No valid files found
                    handler(year_prog / len(years), status=f"No valid data files for {year}")
                    continue
                    
                file_prog = 0
                for csv in files:
                    try:
                        # Check if file is empty or just a placeholder
                        print(f"Importing {os.path.basename(csv)}")
                        dataframe = self.__read_csv(csv)
                        if dataframe is not None and not dataframe.empty:
                            self.__import_dataframe(dataframe)
                            print(f"  Imported {len(dataframe)} records")

                    except Exception as e:
                        print(f"Error processing {csv}: {str(e)}")
                        
                    file_prog += 1
                    handler(((file_prog / len(files)) * (1 / len(years))) + (year_prog / len(years)),
                            status=f"Importing Statcast data for {year}")

                progress_handler.end_progress()
            year_prog += 1
            handler(year_prog / len(years), status="Importing Statcast data")

    def __get_valid_data_files(self, year):
        """
        Gets all valid Statcast data files for a given year with comprehensive validation.

        :param year: the year to find valid data files for
        :return: list of paths to valid CSV files
        """
        savant_path = os.path.join(self._path, "BaseballSavant", str(year))
        if not os.path.exists(savant_path):
            print(f"Directory for year {year} does not exist: {savant_path}")
            return []

        valid_files = []
        all_files = [f for f in os.listdir(savant_path) if f.endswith('.csv') and not f.endswith('.error')]
        
        for filename in all_files:
            file_path = os.path.join(savant_path, filename)
            if os.path.getsize(file_path) < 10:
                print(f"Skipping file due to small size: {filename}")
                continue
            
            try:
                with open(file_path, 'r') as f:
                    # Read a few lines to check content
                    data_lines = 0
                    header_found = False
                    
                    for i, line in enumerate(f):
                        if i >= 10:
                            break
                            
                        line = line.strip()
                        if line.startswith('#'):
                            continue
                        
                        if not header_found:
                            header_found = True
                            continue
                        
                        if line and ',' in line:
                            data_lines += 1
                    
                    if header_found and data_lines > 0:
                        valid_files.append(file_path)
                        print(f"Found valid data file: {filename}")
                    else:
                        print(f"Skipping file with no data: {filename}")
                        
            except Exception as e:
                print(f"Error validating file {filename}: {str(e)}")
                continue

        print(f"Found {len(valid_files)} valid data files for year {year}")
        return valid_files

    def __read_csv(self, path, header=None):
        """
        Reads a csv file into memory, handling potential errors
        
        :param path: the path to the csv
        :param header: the header for the file (as array of strings); if None (default), 
                     the headers will come from the first line of the file
        :return: a pandas DataFrame of the csv or None if empty/invalid
        """
        try:
            if header:
                return pd.read_csv(path, header=None, names=header)
            else:
                try:
                    dataframe = pd.read_csv(path, low_memory=False)
                    # Handle duplicate columns
                    names_so_far = set()
                    drop_cols = []
                    for col in dataframe.columns:
                        if col in names_so_far:
                            drop_cols.append(col)
                        else:
                            names_so_far.add(col + ".1")
                    
                    if drop_cols:
                        dataframe = dataframe.drop(columns=drop_cols)
                        
                    return dataframe
                except pd.errors.EmptyDataError:
                    print(f"  Warning: {os.path.basename(path)} is empty")
                    return None
                except Exception as e:
                    print(f"  Error reading {os.path.basename(path)}: {str(e)}")
                    return None
        except Exception as e:
            print(f"  Fatal error reading {os.path.basename(path)}: {str(e)}")
            return None

    def unimport_statcast_data(self, year=None, handler=lambda *args: None):
        """
        Undoes import of BaseballSavant data to MySQL database

        :param year: the year to be ub-imported; defaults to all years 1999 to present
        :param handler: a function that takes in a double, representing the completion percentage of the import undoing
        :raises ConnectionError: if the connection fails
        """

        if year:
            years = [year]
        else:
            years = [y for y in range(1999, datetime.now().year + 1)]

        year_prog = 0
        handler(0, status="Undoing Statcast import")
        for year in years:
            savant_path = os.path.join(self._path, "BaseballSavant", str(year))
            if not os.path.exists(savant_path):
                year_prog += 1
                handler(year_prog / len(years), status=f"No data directory for {year}")
                continue
                
            progress_handler = ProgressHandler(savant_path)
            progress = progress_handler.get_progress()
            if progress != ProgressHandler.NONE:
                progress_handler.start_progress()
                self.__undo_sql_import(year)
            year_prog += 1
            handler(year_prog / len(years), status="Undoing Statcast import")

    def __import_dataframe(self, dataframe):
        """
        Imports data from dataframe to MySQL

        :param dataframe: the dataframe to import
        :raises ConnectionError: if the connection fails
        """
        # Remove columns not in schema
        clean_df, filtered_columns = self._connection.filter_dataframe_columns(dataframe, 'pitch')
            
        if filtered_columns:
            print(f"  Filtered out {len(filtered_columns)} column(s) not in schema:")
            for col in sorted(filtered_columns):
                print(f"    - {col}")
                
            print(f"  Continuing with {len(clean_df.columns)} valid column(s)")
            
        for column in clean_df.columns:
            clean_df[column] = clean_df[column].apply(
                lambda x: None if pd.isna(x) or (isinstance(x, str) and x.lower() == "null") else x
            )
        
        clean_df.to_sql(
            "pitch", 
            self._connection._engine, 
            if_exists='append',
            index=False,
            chunksize=500,
            method='multi'
        )

    def __undo_sql_import(self, year):
        """
        Undoes all import progress to the database so far on a year

        :param year: the year to undo progress on
        :raises ConnectionError: if the connection fails
        """
        print(f"Removing existing Statcast data for {year}...")
        self._connection.execute(f"DELETE FROM pitch WHERE game_year={year};")

        # Remove progress file
        progress_file = os.path.join(self._path, "BaseballSavant", str(year), "progress.dat")
        if os.path.exists(progress_file):
            os.remove(progress_file)