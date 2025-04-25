#!/usr/bin/env python3

import abc
from ..MySQLConnection import MySQLConnection
from .utils import progress
import traceback
class BaseCommand(abc.ABC):
    """
    Base class for all command handlers.
    
    This class defines the interface and common functionality for all command handlers.
    Subclasses should implement the abstract methods to provide data source-specific behavior.
    """
    
    def __init__(self, name):
        """Initialize with the data source name."""
        self.name = name
    
    def register_commands(self, parser):
        """
        Register standard subcommands with the argument parser.
        
        :param parser: The argparse parser to add subcommands to
        :return: The subparsers object for further customization
        """
        subparsers = parser.add_subparsers(dest="subcommand", help="Operation to perform")
        
        # Add download command
        download_parser = subparsers.add_parser('download', help=f'Download {self.name} data')
        self._add_download_args(download_parser)
        
        # Add import command
        import_parser = subparsers.add_parser('import', help=f'Import {self.name} data to database')
        self._add_import_args(import_parser)
        
        # Add process command (download + import)
        process_parser = subparsers.add_parser('process', help=f'Download and import {self.name} data', conflict_handler='resolve')
        self._add_download_args(process_parser)
        self._add_import_args(process_parser)
        
        return subparsers
    
    def _add_download_args(self, parser):
        """
        Add download arguments to a parser.
        
        :param parser: The argparse parser to add arguments to
        """
        parser.add_argument("path", nargs="?", help="The folder to store files downloaded and processed by sabersql")
        if self.supports_year():
            parser.add_argument("-y", "--year", type=int, help="Process only the given year")
        parser.add_argument("--undo", action="store_true", help="Undo the download")
    
    def _add_import_args(self, parser):
        """
        Add import arguments to a parser.
        
        :param parser: The argparse parser to add arguments to
        """
        parser.add_argument("path", nargs="?", help="The folder to store files downloaded and processed by sabersql")
        if self.supports_year():
            parser.add_argument("-y", "--year", type=int, help="Process only the given year")
        parser.add_argument("--undo", action="store_true", help="Undo the import")
    
    def execute_command(self, args):
        """
        Execute the requested command.
        
        :param args: The parsed command-line arguments
        :return: True if successful, False otherwise
        """
        if args.subcommand == 'download':
            return self.process(args, download_only=True)
        elif args.subcommand == 'import':
            return self.process(args, import_only=True)
        elif args.subcommand == 'process':
            return self.process(args)
        else:
            print(f"Please specify a subcommand for {self.name}: download, import, or process")
            return False
    
    def process(self, args, download_only=False, import_only=False):
        """
        Process data according to the specified arguments.
        
        This method orchestrates the download and import operations.
        
        :param args: The parsed command-line arguments
        :param download_only: If True, only download data without importing
        :param import_only: If True, only import data without downloading
        :return: True if successful, False otherwise
        """
        try:
            # Download data if requested
            if not import_only:
                downloader = self.create_downloader(args)
                
                if args.undo:
                    print(f"Undoing {self.name} data download...")
                    self.handle_undownload(downloader, args)
                else:
                    print(f"Downloading {self.name} data...")
                    self.handle_download(downloader, args)
            
            # Import data if requested
            if not download_only:
                connection = self.create_connection(args)
                importer = self.create_importer(args, connection)
                
                if args.undo:
                    print(f"Undoing {self.name} data import...")
                    self.handle_unimport(importer, args)
                else:
                    print(f"Importing {self.name} data...")
                    self.handle_import(importer, args)
            
            return True
        except Exception as e:
            print(f"Error processing {self.name} data: {str(e)}\n{traceback.format_exc()}")
            return False
    
    def create_connection(self, args):
        """
        Create a database connection.
        
        :param args: The parsed command-line arguments
        :return: A MySQLConnection object
        """
        connection = MySQLConnection(args.user, args.password, args.schema, args.address)
        connection.create_database()
        return connection
    
    @abc.abstractmethod
    def create_downloader(self, args):
        """
        Create a downloader instance.
        
        :param args: The parsed command-line arguments
        :return: A downloader object for this data source
        """
        pass
    
    @abc.abstractmethod
    def create_importer(self, args, connection):
        """
        Create an importer instance.
        
        :param args: The parsed command-line arguments
        :param connection: A database connection
        :return: An importer object for this data source
        """
        pass
    
    def handle_download(self, downloader, args):
        """
        Execute the download operation.
        
        This is the standard implementation that works for most data sources.
        Override this method to customize the download process.
        
        :param downloader: The downloader object
        :param args: The parsed command-line arguments
        """
        if self.supports_year():
            downloader.download(handler=progress, year=args.year)
        else:
            downloader.download(handler=progress)
    
    def handle_undownload(self, downloader, args):
        """
        Execute the undownload operation.
        
        This is the standard implementation that works for most data sources.
        Override this method to customize the undownload process.
        
        :param downloader: The downloader object
        :param args: The parsed command-line arguments
        """
        if self.supports_year():
            downloader.undownload(handler=progress, year=args.year)
        else:
            downloader.undownload(handler=progress)
    
    def handle_import(self, importer, args):
        """
        Execute the import operation.
        
        This is the standard implementation that works for most data sources.
        Override this method to customize the import process.
        
        :param importer: The importer object
        :param args: The parsed command-line arguments
        """
        if self.supports_year():
            method = getattr(importer, self.get_import_method_name())
            method(handler=progress, year=args.year)
        else:
            method = getattr(importer, self.get_import_method_name())
            method(handler=progress)
    
    def handle_unimport(self, importer, args):
        """
        Execute the unimport operation.
        
        This is the standard implementation that works for most data sources.
        Override this method to customize the unimport process.
        
        :param importer: The importer object
        :param args: The parsed command-line arguments
        """
        if self.supports_year():
            method = getattr(importer, self.get_unimport_method_name())
            method(handler=progress, year=args.year)
        else:
            method = getattr(importer, self.get_unimport_method_name())
            method(handler=progress)
    
    def supports_year(self):
        """
        Whether this data source supports year-specific operations.
        
        :return: True if this data source supports year filtering, False otherwise
        """
        return True
    
    def get_import_method_name(self):
        """
        Get the name of the import method.
        
        :return: The name of the method to call on the importer
        """
        return f"import_{self.name}_data"
    
    def get_unimport_method_name(self):
        """
        Get the name of the unimport method.
        
        :return: The name of the method to call on the importer
        """
        return f"unimport_{self.name}_data"