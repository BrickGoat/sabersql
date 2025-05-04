#!/usr/bin/env python3

from .base_command import BaseCommand
from .utils import progress

class YearBasedCommand(BaseCommand):
    """
    Base class for commands that process data by year.
    
    This intermediate class provides common functionality for commands that 
    need to process data year by year (like Retrosheet and Statcast).
    
    TODO - Remove?
    """
    
    def __init__(self, name):
        """Initialize with the data source name."""
        super().__init__(name)
    
    def handle_download(self, downloader, args):
        """Execute the download operation year by year."""
        self._process_by_year(
            args=args,
            operation_type="download",
            handler_object=downloader,
            method_name="download"
        )
    
    def handle_undownload(self, downloader, args):
        """Execute the undownload operation year by year."""
        self._process_by_year(
            args=args,
            operation_type="undownload",
            handler_object=downloader,
            method_name="undownload"
        )
    
    def handle_import(self, importer, args):
        """Execute the import operation year by year."""
        self._process_by_year(
            args=args,
            operation_type="import",
            handler_object=importer,
            method_name=self.get_import_method_name()
        )
    
    def handle_unimport(self, importer, args):
        """Execute the unimport operation year by year."""
        self._process_by_year(
            args=args,
            operation_type="unimport",
            handler_object=importer,
            method_name=self.get_unimport_method_name()
        )
    
    def _process_by_year(self, args, operation_type, handler_object, method_name):
        """
        Process data year by year for the specified operation.
        
        :param args: Command-line arguments
        :param operation_type: Type of operation (download, import, etc.)
        :param handler_object: Object that will perform the operation
        :param method_name: Method name to call on the handler object
        """
        start_year = int(args.start_date.split('-')[0])
        end_year = int(args.end_date.split('-')[0])
        
        years = list(range(start_year, end_year + 1))
        
        operation_verbs = {
            "download": "Downloading",
            "undownload": "Removing downloads for",
            "import": "Importing",
            "unimport": "Removing imports for"
        }
        verb = operation_verbs.get(operation_type, "Processing")
        
        print(f"{verb} {self.name} data for years {start_year} to {end_year}")
        
        for i, year in enumerate(years):
            print(f"Year {year} ({i+1}/{len(years)})")
            
            method = getattr(handler_object, method_name)
            
            method(
                year=year,
                handler=self._create_subprogress_handler(i, len(years))
            )
    
    def _create_subprogress_handler(self, current_index, total_items):
        """
        Create a progress handler for a subset of the overall work.
        
        :param current_index: Current item index
        :param total_items: Total number of items
        :return: Progress handler function
        """
        def handler(fraction, status=''):
            overall_fraction = (current_index + fraction) / total_items
            progress(overall_fraction, status)
        
        return handler