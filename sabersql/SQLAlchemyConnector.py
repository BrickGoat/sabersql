#!/usr/bin/env python3

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import pandas as pd

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
        
        # Create SQLAlchemy engine
        self._engine = self._create_engine()
        
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
            raise ConnectionError(f"Failed to create SQLAlchemy engine for {self._database} at {self._username}@{self._address}:{self._port} : {str(e)}")
            
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
        Perform a batch update operation
        
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
            
            # Execute the query
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