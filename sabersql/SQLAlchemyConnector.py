#!/usr/bin/env python3

from sqlalchemy import create_engine, text
import pandas as pd
from .Schemas import schemas
from sqlalchemy import inspect

class SQLAlchemyConnector:
    """
    Provides a SQLAlchemy connection to the database for efficient operations.
    """

    def __init__(self, username, password, database, address):
        """
        Initialize a SQLAlchemy connection with the given information

        :param username: the database user
        :param password: the password for the user
        :param database: the name of the database to store the data in
        :param address: the address of the database server
        :param port: the port of the database server
        """
        self._username = username
        self._password = password
        self._database = database
        self._address = address
        
        self._engine = self._create_engine()

    def create_database(self):
        """
        Creates database and tables

        :raises ConnectionError: if the connection fails
        """
        try:
            temp_conn_string = f"mysql+pymysql://{self._username}:{self._password}@{self._address}"
            temp_engine = create_engine(temp_conn_string)
            
            with temp_engine.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {self._database}"))
                conn.commit()
            
            with self._engine.connect() as conn:
                for schema in schemas:
                    conn.execute(text(schema))
                    conn.commit()
                
            print(f"Database {self._database} and required tables created successfully")
            
        except Exception as e:
            if_port = f":{self._port}" if self._port else ""
            raise ConnectionError(f"Failed to create database {self._database} at {self._username}@{self._address}{if_port} : {str(e)}")
            
    def _create_engine(self):
        """
        Creates a SQLAlchemy engine
        
        :return: SQLAlchemy engine
        :raises ConnectionError: if the connection fails
        """
        try:
            conn_string = f"mysql+pymysql://{self._username}:{self._password}@{self._address}/{self._database}"
            return create_engine(conn_string)
        except Exception as e:
            raise ConnectionError(f"Failed to create SQLAlchemy engine for {self._database} at {self._username}@{self._address} : {str(e)}")

    def get_table_columns(self, table_name):
        """
        Get the columns for a specific table in the database
        
        :param table_name: Name of the table to get columns for
        :return: Set of column names in the table
        """
        try:
            with self._engine.connect() as conn:
                insp = inspect(self._engine)
                return set(col['name'] for col in insp.get_columns(table_name))
        except Exception as e:
            print(f"Warning: Could not get columns for table {table_name}: {str(e)}")
            # Fall back to direct SQL query
            try:
                with self._engine.connect() as conn:
                    result = conn.execute(text(f"DESCRIBE {table_name};"))
                    columns = set(row[0] for row in result)
                    return columns
            except Exception as e2:
                print(f"Error getting table schema: {str(e2)}")
                return None
    
    def filter_dataframe_columns(self, df, table_name):
        """
        Filter a DataFrame to only include columns that exist in the target table
        
        :param df: Pandas DataFrame to filter
        :param table_name: Table to check columns against
        :return: Tuple of (filtered_dataframe, set_of_removed_columns)
        """
        valid_columns = self.get_table_columns(table_name)
        if not valid_columns:
            return df, set()
            
        original_columns = set(df.columns)
        valid_df_columns = [col for col in df.columns if col in valid_columns]
        filtered_columns = original_columns - set(valid_df_columns)
        
        return df[valid_df_columns], filtered_columns
     
    def read_sql(self, query, params=None):
        """
        Execute a SQL query and return the results as a pandas DataFrame
        
        :param query: SQL query string
        :param params: Parameters for the query (optional)
        :return: pandas DataFrame with query results
        :raises ConnectionError: if the query fails
        """
        try:
            return pd.read_sql(query, self._engine, params=params)
        except Exception as e:
            raise ConnectionError(f"Failed to execute read_sql query: {str(e)}")
            
    def execute(self, query, params=None):
        """
        Execute a SQL command (INSERT, UPDATE, DELETE, etc.)
        
        :param query: SQL command string
        :param params: Parameters for the command (optional)
        :raises ConnectionError: if the command fails
        """
        try:
            with self._engine.connect() as connection:
                connection.execute(text(query), params)
                connection.commit()
        except Exception as e:
            raise ConnectionError(f"Failed to execute SQL command: {str(e)}")
            
    def execute_many(self, query, params_list):
        """
        Execute a SQL command multiple times with different parameters
        
        :param query: SQL command string with parameter placeholders
        :param params_list: List of parameter dictionaries
        :raises ConnectionError: if the command fails
        """
        try:
            with self._engine.connect() as connection:
                for params in params_list:
                    connection.execute(text(query), params)
                connection.commit()
        except Exception as e:
            raise ConnectionError(f"Failed to execute_many SQL command: {str(e)}")
            
    def batch_update(self, table, update_data, id_column='pitch_id'):
        """
        Generates a single UPDATE statement like:
        UPDATE pitch SET
            velocity = CASE pitch_id
                WHEN 1 THEN 92.3
                WHEN 2 THEN 94.1
                WHEN 3 THEN 93.0
                ELSE velocity END,
            spin_rate = CASE pitch_id
                WHEN 1 THEN 2200
                WHEN 2 THEN 2250
                ELSE spin_rate END
        WHERE pitch_id IN (1, 2, 3)

        :param table: Table name to update
        :param update_data: List of dictionaries with column data to update
        :param id_column: Name of the ID column to use in the WHERE clause
        :raises ConnectionError: if the update fails
        """
        if not update_data:
            return
            
        try:
            # Collects all unique column names from the update data
            columns = set()
            for item in update_data:
                columns.update(set(item.keys()) - {id_column})
                
            # Create the batch update query
            case_statements = []
            for column in columns:
                case_when = f"{column} = CASE {id_column} "
                for item in update_data:
                    if column in item and item[column] is not None:
                        value = item[column]
                        if isinstance(value, str):
                            value = f"'{value}'"
                        case_when += f"WHEN {item[id_column]} THEN {value} "
                case_when += f"ELSE {column} END"
                case_statements.append(case_when)
                
            # Create IDs list for WHERE clause
            ids = [item[id_column] for item in update_data]
            id_list = ", ".join(str(id) for id in ids)
            
            # Build the final query
            query = f"UPDATE {table} SET {', '.join(case_statements)} WHERE {id_column} IN ({id_list})"
            
            with self._engine.connect() as connection:
                connection.execute(text(query))
                connection.commit()
                
        except Exception as e:
            raise ConnectionError(f"Failed to perform batch update: {str(e)}")
            
    def close(self):
        """
        Close the database connection
        """
        if hasattr(self, '_engine'):
            self._engine.dispose()