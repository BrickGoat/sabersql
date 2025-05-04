#!/usr/bin/env python3

from .base_command import BaseCommand
from ..PitchEnrichment.PitchTimestampEnricher import PitchTimestampEnricher
from ..PitchEnrichment.PitchVenueEnricher import PitchVenueEnricher
from .utils import progress

class PitchEnrichmentCommand(BaseCommand):
    """Command handler for pitch enrichment operations."""
    
    def __init__(self):
        super().__init__("pitch-enrichment")
    
    def register_commands(self, parser):
        """
        Register commands specific to pitch enrichment.
        
        :param parser: The argparse parser to add subcommands to
        :return: The parser object
        """
        self._add_common_args(parser)
        parser.add_argument(
            "--timestamps", 
            action="store_true", 
            help="Process timestamp enrichment for pitches"
        )
        parser.add_argument(
            "--venues", 
            action="store_true", 
            help="Process venue enrichment for pitches"
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of pitches to process in each batch"
        )
        
        return parser
    
    def execute_command(self, args):
        """
        Execute the enrichment operation.
        
        :param args: The parsed command-line arguments
        :return: True if successful, False otherwise
        """
        try:
            if not hasattr(args, 'path') or args.path is None:
                print("Error: No data path specified. Please provide a path in the config file or command line.")
                return False
                
            self._handle_date_range_args(args)
            
            run_timestamps = args.timestamps
            run_venues = args.venues
            
            if not run_timestamps and not run_venues:
                run_timestamps = True
                run_venues = True
                print("Running both timestamp and venue enrichment for pitches")
            
            batch_size = getattr(args, 'batch_size', 1000)
            
            start_date = getattr(args, 'start_date', None)
            end_date = getattr(args, 'end_date', None)
            
            if start_date or end_date:
                date_range_text = f" for period {start_date or 'earliest'} to {end_date or 'latest'}"
            else:
                date_range_text = " for all dates"
                
            if run_timestamps:
                print(f"Enriching pitch data with timestamps{date_range_text}...")
                timestamp_enricher = PitchTimestampEnricher(args.path, self.create_connection(args))
                try:
                    timestamp_enricher.enrich_pitches(
                        start_date=start_date,
                        end_date=end_date,
                        batch_size=batch_size,
                        handler=progress
                    )
                finally:
                    timestamp_enricher.close()
            
            if run_venues:
                print(f"Enriching pitch data with venue information{date_range_text}...")
                venue_enricher = PitchVenueEnricher(args.path, self.create_connection(args))
                try:
                    venue_enricher.enrich_pitches(
                        start_date=start_date,
                        end_date=end_date,
                        batch_size=batch_size,
                        handler=progress
                    )
                finally:
                    venue_enricher.close()
            
            return True
            
        except Exception as e:
            print(f"Error processing pitch enrichment: {str(e)}")
            if hasattr(args, 'debug') and args.debug:
                import traceback
                print(traceback.format_exc())
            return False
        
    def create_downloader(self, args):
        """
        Required abstract method implementation. Not used for enrichment.
        
        :param args: The parsed command-line arguments
        :return: None
        """
        return None

    def create_importer(self, args, connection):
        """
        Required abstract method implementation. Not used for enrichment.
        
        :param args: The parsed command-line arguments
        :param connection: A database connection
        :return: None
        """
        return None