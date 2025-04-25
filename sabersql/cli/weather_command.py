#!/usr/bin/env python3

from .base_command import BaseCommand
from ..Weather.WeatherDownloader import WeatherDownloader
from ..Weather.WeatherImporter import WeatherImporter
from ..Weather.Stadium import match_stadiums_to_weather_stations
from .utils import progress
from datetime import datetime

class WeatherCommand(BaseCommand):
    """Command handler for weather data."""
    
    def __init__(self):
        super().__init__("weather")
        self.matches_df = None
    
    def _add_download_args(self, parser):
        """Add weather-specific download arguments."""
        super()._add_download_args(parser)
        parser.add_argument("--stadiums", 
                          help="Path to CSV file with stadium information (team, stadium, lat, lon)")
        parser.add_argument("--stations", 
                          help="Path to CSV file with weather station information")
        parser.add_argument("--start-date", 
                          help="Start date for weather data (YYYY-MM-DD)")
        parser.add_argument("--end-date", 
                          help="End date for weather data (YYYY-MM-DD)")
        parser.add_argument("--max-distance", type=float, default=50.0, 
                          help="Maximum distance (km) between stadium and weather station")
        parser.add_argument("--delay", type=int, default=5, 
                          help="Delay between requests in seconds")
    
    def _add_import_args(self, parser):
        """Add weather-specific import arguments."""
        super()._add_import_args(parser)
        # Optional arguments for import when used without download
        parser.add_argument("--stadiums", 
                          help="Path to CSV file with stadium information (optional for import)")
        parser.add_argument("--stations", 
                          help="Path to CSV file with weather station information (optional for import)")
        parser.add_argument("--start-date", 
                          help="Start date for weather data (optional for import)")
        parser.add_argument("--end-date", 
                          help="End date for weather data (optional for import)")
        parser.add_argument("--max-distance", type=float, 
                          help="Maximum distance between stadium and station (optional for import)")
    
    def create_downloader(self, args):
        """Create a weather data downloader."""
        return WeatherDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a weather data importer."""
        return WeatherImporter(args.path, connection)
    
    def supports_year(self):
        """Weather data doesn't support year filtering."""
        return False
    
    def handle_download(self, downloader, args):
        """Custom download handling for weather data."""
        # Set default dates if not provided
        if not args.start_date:
            current_year = datetime.now().year
            args.start_date = f"{current_year}-04-01"  # Start of baseball season
            print(f"Using default start date: {args.start_date}")
            
        if not args.end_date:
            start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
            end_date = start_date.replace(month=10, day=31)  # End of regular season
            args.end_date = end_date.strftime('%Y-%m-%d')
            print(f"Using default end date: {args.end_date}")
        
        # Ensure required parameters are provided
        if not args.stadiums or not args.stations:
            raise ValueError("Both --stadiums and --stations must be specified for weather data download")
        
        # Match stadiums to weather stations
        print("Matching stadiums to weather stations...")
        self.matches_df = match_stadiums_to_weather_stations(
            args.stations,
            args.stadiums,
            start_date=args.start_date,
            end_date=args.end_date,
            max_distance_km=args.max_distance
        )
        
        # Print matches summary
        print(f"Found {len(self.matches_df)} stadium-station matches.")
        matches_with_station = self.matches_df[self.matches_df.station_icao.notna()]
        print(f" - {len(matches_with_station)} stadiums matched to weather stations")
        print(f" - {len(self.matches_df) - len(matches_with_station)} stadiums without a matching station")
        
        # Download weather data
        print(f"Downloading weather data from {args.start_date} to {args.end_date}...")
        downloader.download(
            self.matches_df,
            args.start_date,
            args.end_date,
            weather_types=["tmpf", "dwpf", "relh", "drct", "sknt", "gust", "alti", "vsby", "wxcodes"],
            delay_seconds=args.delay,
            handler=progress
        )
    
    def handle_import(self, importer, args):
        """Custom import handling for weather data."""
        # Use stadium matches from download step if available
        matches_df = getattr(self, 'matches_df', None)
        
        # Try to recreate matches if not available and we have the required info
        if matches_df is None and args.stadiums and args.stations:
            try:
                matches_df = match_stadiums_to_weather_stations(
                    args.stations,
                    args.stadiums,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    max_distance_km=args.max_distance
                )
            except Exception as e:
                print(f"Warning: Could not recreate stadium-station matches: {str(e)}")
                print("Continuing with import without stadium matching information.")
        force = getattr(args, 'force', False)
        # Import the data
        importer.import_weather_data(matches_df, handler=progress)