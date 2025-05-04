#!/usr/bin/env python3

from .base_command import BaseCommand
from ..Weather.WeatherDownloader import WeatherDownloader
from ..Weather.WeatherImporter import WeatherImporter
from ..Weather.Stadium import match_venues_to_weather_stations
from .utils import progress

class WeatherCommand(BaseCommand):
    """Command handler for weather data."""
    
    def __init__(self):
        super().__init__("weather")
        self.matches_df = None
    
    def _add_download_specific_args(self, parser):
        """Add weather-specific download arguments."""
        parser.add_argument("--stations", 
                          help="Path to CSV file with weather station information")
        parser.add_argument("--max-distance", type=float, default=50.0, 
                          help="Maximum distance (km) between venue and weather station")
        parser.add_argument("--delay", type=int, default=5, 
                          help="Delay between requests in seconds")
        parser.add_argument("--types", 
                          help="Comma-separated list of weather data types to download (e.g., tmpf,dwpf,sknt)")
    
    def _add_import_specific_args(self, parser):
        """Add weather-specific import arguments."""
        parser.add_argument("--stations", 
                          help="Path to CSV file with weather station information (optional for import)")
        parser.add_argument("--max-distance", type=float, 
                          help="Maximum distance between venue and station (optional for import)")
    
    def create_downloader(self, args):
        """Create a weather data downloader."""
        return WeatherDownloader(args.path)
    
    def create_importer(self, args, connection):
        """Create a weather data importer."""
        return WeatherImporter(args.path, connection)
    
    def supports_date_range(self):
        """Weather data supports date range filtering."""
        return True
    
    def handle_download(self, downloader, args):
        """Custom download handling for weather data."""
        if not args.stations:
            raise ValueError("--stations parameter must be specified for weather data download")
        
        weather_types = ["tmpf", "dwpf", "relh", "drct", "sknt", "gust", "alti", "vsby", "wxcodes"]
        if hasattr(args, 'types') and args.types:
            weather_types = args.types.split(',')
            print(f"Using custom weather types: {', '.join(weather_types)}")
        
        connection = self.create_connection(args)
        
        print("Matching MLB venues to weather stations...")
        
        self.matches_df = match_venues_to_weather_stations(
            args.stations,
            connection=connection,
            start_date=args.start_date,
            end_date=args.end_date,
            max_distance_km=args.max_distance
        )

        print(f"Found {len(self.matches_df)} venue-station matches.")
        matches_with_station = self.matches_df[self.matches_df.station_icao.notna()]
        print(f" - {len(matches_with_station)} venues matched to weather stations")
        print(f" - {len(self.matches_df) - len(matches_with_station)} venues without a matching station")
        
        print(f"Downloading weather data from {args.start_date} to {args.end_date}...")
        downloader.download(
            self.matches_df,
            args.start_date,
            args.end_date,
            weather_types=weather_types,
            delay_seconds=args.delay,
            handler=progress,
        )
    
    def handle_import(self, importer, args):
        """Custom import handling for weather data."""
        matches_df = getattr(self, 'matches_df', None)
        
        if matches_df is None and args.stations:
            try:
                connection = self.create_connection(args)
                
                matches_df = match_venues_to_weather_stations(
                    args.stations,
                    connection=connection,
                    start_date=args.start_date,
                    end_date=args.end_date,
                    max_distance_km=args.max_distance
                )
            except Exception as e:
                print(f"Warning: Could not recreate venue-station matches: {str(e)}")
                print("Continuing with import without venue matching information.")
        
        importer.import_weather_data(matches_df, handler=progress)