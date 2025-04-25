#!/usr/bin/env python3

from .base_command import BaseCommand
from ..PDownloader import PDownloader
from ..PImporter import PImporter

class PeopleCommand(BaseCommand):
    """Command handler for player data."""
    
    def __init__(self):
        super().__init__("people")
    
    def create_downloader(self, args):
        """Create a people data downloader."""
        return PDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a people data importer."""
        return PImporter(args.path, connection)
    
    def supports_year(self):
        """People data doesn't support year filtering."""
        return False