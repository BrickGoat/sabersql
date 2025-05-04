#!/usr/bin/env python3

from .year_based_command import YearBasedCommand
from ..SDownloader import StatcastDownloader
from ..SImporter import SImporter

class StatcastCommand(YearBasedCommand):
    """Command handler for BaseballSavant (Statcast) data."""
    
    def __init__(self):
        super().__init__("statcast")
    
    def create_downloader(self, args):
        """Create a Statcast downloader."""
        return StatcastDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a Statcast importer."""
        return SImporter(args.path, connection)
    
    def get_import_method_name(self):
        """Get the custom import method name for Statcast data."""
        return "import_statcast_data"
    
    def get_unimport_method_name(self):
        """Get the custom unimport method name for Statcast data."""
        return "unimport_statcast_data"