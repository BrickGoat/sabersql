#!/usr/bin/env python3

from .Utilities import _shell
from . import Schemas
import tempfile

class MySQLConnection:
    """
    Manages a MySQL connection and sends commands.
    """

    def __init__(self, username, password, database, address, port=None):
        """
        Initialize a MySQLConnection with the given connection information

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
        self._port = port

    def _run(self, command, use_database=True):
        """
        Runs the given command within the MySQL connection

        :param command: the command to be run
        :return: the stdout of running the command
        :raises ConnectionError: if the connection fails
        """
        with tempfile.NamedTemporaryFile(delete=False, mode='w') as temp_query_file:
            temp_query_file.write(command)
            temp_query_file.flush()

            if use_database:
                mysql_command = f"export MYSQL_PWD={self._password}; mysql -u{self._username} {self._database} -B < {temp_query_file.name}"
            else:
                mysql_command = f"export MYSQL_PWD={self._password}; mysql -u{self._username} -B < {temp_query_file.name}"

            stdout, stderr = _shell(mysql_command)

        if stderr:
            if_port = f":{self._port}" if self._port else ""
            raise ConnectionError(f"Failed to connect to MySQL database {self._database} at {self._username}@{self._address}{if_port} : {stderr}")
        else:
            return stdout

    def create_database(self):
        """
        Creates database and tables as documented on `GitHub <https://github.com/liam923/sabersql>`_.

        :raises ConnectionError: if the connection fails
        """

        self._run("create database if not exists %s;" % self._database, use_database=False)
        for schema in Schemas.schemas:
            self._run(schema)

    def import_data(self, table, headers, data, batch_size=100):
        """
        Imports data into a given table.

        :param table: the name of the table to add data to
        :param headers: the column names of the values to add, as an array of strings
        :param data: the values to add to the table, as a generator of generators of strings that are the value literal
        :param batch_size: how many values to send at once
        :raises ConnectionError: if the connection fails
        """

        def send_batch(batch):
            command = "INSERT INTO %s (" % table
            command += ','.join(headers)
            command += ") VALUES"
            command += ','.join(
                ["(" + ','.join(row) + ")" for row in batch])
            command += ";"
            self._run(command)

        batch = []
        for row in data:
            batch.append(row)

            if len(batch) == batch_size:
                send_batch(batch)
                batch = []
        if len(batch) != 0:
            send_batch(batch)
