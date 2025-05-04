#!/usr/bin/env python3

from .year_based_command import YearBasedCommand
from ..RDownloader import RetrosheetDownloader
from ..RImporter import RImporter

class RetrosheetCommand(YearBasedCommand):
    """Command handler for Retrosheet data."""
    
    def __init__(self):
        super().__init__("retrosheet")
    
    def create_downloader(self, args):
        """Create a Retrosheet downloader."""
        return RetrosheetDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a Retrosheet importer."""
        return RImporter(args.path, connection)