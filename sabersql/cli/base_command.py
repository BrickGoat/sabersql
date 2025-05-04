#!/usr/bin/env python3

import abc
from ..SQLAlchemyConnector import SQLAlchemyConnector
from .utils import progress
import traceback
from datetime import datetime

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
        
        download_parser = subparsers.add_parser('download', help=f'Download {self.name} data')
        self._add_download_args(download_parser)
        
        import_parser = subparsers.add_parser('import', help=f'Import {self.name} data to database')
        self._add_import_args(import_parser)
        
        process_parser = subparsers.add_parser('process', help=f'Download and import {self.name} data', conflict_handler='resolve')
        self._add_common_args(process_parser)
        self._add_download_specific_args(process_parser)
        self._add_import_specific_args(process_parser)
        
        return subparsers
    
    def _add_common_args(self, parser):
        """
        Add arguments common to all operations.
        
        :param parser: The argparse parser to add arguments to
        """
        parser.add_argument("path", nargs="?", help="The folder to store files downloaded and processed by sabersql")
        if self.supports_date_range():
            parser.add_argument("--start-date", help="Start date in YYYY-MM-DD format")
            parser.add_argument("--end-date", help="End date in YYYY-MM-DD format")
        parser.add_argument("--undo", action="store_true", help="Undo the operation")
        parser.add_argument("--debug", action="store_true", help="Show detailed error messages")
 
    def _add_download_args(self, parser):
        """Add download arguments to a parser."""
        self._add_common_args(parser)
        self._add_download_specific_args(parser)
    
    def _add_import_args(self, parser):
        """Add import arguments to a parser."""
        self._add_common_args(parser)
        self._add_import_specific_args(parser)
    
    def _add_download_specific_args(self, parser):
        """
        Add arguments specific to download operations.
        Override in subclasses if needed.
        """
        pass
    
    def _add_import_specific_args(self, parser):
        """
        Add arguments specific to import operations.
        Override in subclasses if needed.
        """
        pass
    
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
            if self.supports_date_range():
                self._handle_date_range_args(args)
                
            if not import_only:
                downloader = self.create_downloader(args)
                
                if args.undo:
                    print(f"Undoing {self.name} data download...")
                    self.handle_undownload(downloader, args)
                else:
                    print(f"Downloading {self.name} data...")
                    self.handle_download(downloader, args)
            
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
            print(f"Error processing {self.name} data: {str(e)}")
            if hasattr(args, 'debug') and args.debug:
                print(traceback.format_exc())
            return False
    
    def _handle_date_range_args(self, args):
        """
        Process date range arguments, setting defaults if needed.
        
        :param args: The parsed command-line arguments
        """
        if not hasattr(args, 'start_date') or not args.start_date:
            current_year = datetime.now().year
            args.start_date = f"{current_year}-01-01"
            print(f"Using default start date: {args.start_date}")
        
        if not hasattr(args, 'end_date') or not args.end_date:
            try:
                start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
                end_date = datetime(start_date.year, 12, 31)
                args.end_date = end_date.strftime('%Y-%m-%d')
                print(f"Using default end date: {args.end_date}")
            except ValueError:
                args.end_date = datetime.now().strftime('%Y-%m-%d')
                print(f"Invalid start date format. Using today as end date: {args.end_date}")
    
    def create_connection(self, args):
        """
        Create a database connection.
        
        :param args: The parsed command-line arguments
        :return: A MySQLConnection object
        """
        connection = SQLAlchemyConnector(args.user, args.password, args.schema, args.address)
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
        if self.supports_date_range():
            start_date = args.start_date
            end_date = args.end_date
            downloader.download(handler=progress, start_date=start_date, end_date=end_date)
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
        if self.supports_date_range():
            start_date = args.start_date
            end_date = args.end_date
            downloader.undownload(handler=progress, start_date=start_date, end_date=end_date)
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
        method = getattr(importer, self.get_import_method_name())
        if self.supports_date_range():
            method(handler=progress, start_date=args.start_date, end_date=args.end_date)
        else:
            method(handler=progress)
    
    def handle_unimport(self, importer, args):
        """
        Execute the unimport operation.
        
        This is the standard implementation that works for most data sources.
        Override this method to customize the unimport process.
        
        :param importer: The importer object
        :param args: The parsed command-line arguments
        """
        method = getattr(importer, self.get_unimport_method_name())
        if self.supports_date_range():
            method(handler=progress, start_date=args.start_date, end_date=args.end_date)
        else:
            method(handler=progress)
    
    def supports_date_range(self):
        """
        Whether this data source supports date range filtering.
        
        :return: True if this data source supports date range filtering, False otherwise
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
        
    def _create_progress_handler(self, prefix=''):
        """
        Create a progress handler that can be used by operations.
        
        :param prefix: Text to prepend to status messages
        :return: A progress handler function
        """
        def handler(fraction, status=''):
            if prefix and status:
                status = f"{prefix}: {status}"
            elif prefix:
                status = prefix
            progress(fraction, status)
        
        return handler