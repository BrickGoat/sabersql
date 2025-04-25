#!/usr/bin/env python3

from .retrosheet_command import RetrosheetCommand
from .statcast_command import StatcastCommand
from .people_command import PeopleCommand
from .weather_command import WeatherCommand

# Create command instances
_retrosheet_command = RetrosheetCommand()
_statcast_command = StatcastCommand()
_people_command = PeopleCommand()
_weather_command = WeatherCommand()

def register_commands(subparsers):
    """Register all commands with the argument parser."""
    # Create subparsers for each data source
    retrosheet_parser = subparsers.add_parser('retrosheet', help='Manage Retrosheet data')
    statcast_parser = subparsers.add_parser('statcast', help='Manage BaseballSavant data')
    people_parser = subparsers.add_parser('people', help='Manage player data')
    weather_parser = subparsers.add_parser('weather', help='Manage weather data')
    
    # Register specific commands for each data source
    _retrosheet_command.register_commands(retrosheet_parser)
    _statcast_command.register_commands(statcast_parser)
    _people_command.register_commands(people_parser)
    _weather_command.register_commands(weather_parser)
    
    # Add 'all' command to process all data sources
    register_all_command(subparsers)

def register_all_command(subparsers):
    """Register the 'all' command for processing all data sources."""
    all_parser = subparsers.add_parser('all', help='Process all data sources')
    all_subparsers = all_parser.add_subparsers(dest="subcommand", help="Operation to perform")
    
    # Add download and import subcommands for 'all'
    all_download = all_subparsers.add_parser('download', help='Download all data')
    all_download.add_argument("path", nargs="?", help="The folder to store files downloaded and processed by sabersql")
    all_download.add_argument("-y", "--year", type=int, help="Process only the given year")
    all_download.add_argument("--undo", action="store_true", help="Undo the download")
    
    all_import = all_subparsers.add_parser('import', help='Import all data')
    all_import.add_argument("path", nargs="?", help="The folder to store files downloaded and processed by sabersql")
    all_import.add_argument("-y", "--year", type=int, help="Process only the given year")
    all_import.add_argument("--undo", action="store_true", help="Undo the import")

def execute_command(args):
    """Execute the requested command based on args."""
    command = args.command
    
    if command == 'all':
        return execute_all_command(args)
    elif command == 'retrosheet':
        return _retrosheet_command.execute_command(args)
    elif command == 'statcast':
        return _statcast_command.execute_command(args)
    elif command == 'people':
        return _people_command.execute_command(args)
    elif command == 'weather':
        return _weather_command.execute_command(args)
    else:
        print(f"Unknown command: {command}")
        return 1

def execute_all_command(args):
    """Execute operations on all basic data sources."""
    if args.subcommand == 'download':
        # Download all basic data sources
        success = True
        success &= _retrosheet_command.process(args, download_only=True)
        success &= _statcast_command.process(args, download_only=True)
        success &= _people_command.process(args, download_only=True)
        # Weather download requires additional arguments, so we skip it in the "all" command
        print("Note: Weather data was not processed as it requires additional parameters.")
        print("      Use 'sabersql weather download' with appropriate options instead.")
        return 0 if success else 1
        
    elif args.subcommand == 'import':
        # Import all basic data sources
        success = True
        success &= _retrosheet_command.process(args, import_only=True)
        success &= _statcast_command.process(args, import_only=True)
        success &= _people_command.process(args, import_only=True)
        # Weather import requires additional context, so we skip it in the "all" command
        print("Note: Weather data was not processed as it requires additional parameters.")
        print("      Use 'sabersql weather import' with appropriate options instead.")
        return 0 if success else 1
    
    return 1