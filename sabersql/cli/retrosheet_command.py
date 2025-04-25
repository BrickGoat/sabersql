#!/usr/bin/env python3

from .base_command import BaseCommand
from ..RDownloader import RDownloader
from ..RImporter import RImporter

class RetrosheetCommand(BaseCommand):
    """Command handler for Retrosheet data."""
    
    def __init__(self):
        super().__init__("retrosheet")
    
    def create_downloader(self, args):
        """Create a Retrosheet downloader."""
        return RDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a Retrosheet importer."""
        return RImporter(args.path, connection)