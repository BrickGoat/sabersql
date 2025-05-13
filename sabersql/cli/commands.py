#!/usr/bin/env python3

from .retrosheet_command import RetrosheetCommand
from .statcast_command import StatcastCommand
from .people_command import PeopleCommand
from .weather_command import WeatherCommand
from .pitch_enrichment_command import PitchEnrichmentCommand
from .run_command import RunCommand

_retrosheet_command = RetrosheetCommand()
_statcast_command = StatcastCommand()
_people_command = PeopleCommand()
_weather_command = WeatherCommand()
_pitch_enrichment_command = PitchEnrichmentCommand()
_run_command = RunCommand()

def register_commands(subparsers):
    """Register all commands with the argument parser."""
    retrosheet_parser = subparsers.add_parser('retrosheet', help='Manage Retrosheet data')
    statcast_parser = subparsers.add_parser('statcast', help='Manage BaseballSavant data')
    people_parser = subparsers.add_parser('people', help='Manage player data')
    weather_parser = subparsers.add_parser('weather', help='Manage weather data')
    pitch_enrichment_parser = subparsers.add_parser('enrich', help='Enrich pitch data with additional information')
    run_parser = subparsers.add_parser('run', help='Run operations defined in the config file')
    _run_command.register_commands(run_parser)
    _retrosheet_command.register_commands(retrosheet_parser)
    _statcast_command.register_commands(statcast_parser)
    _people_command.register_commands(people_parser)
    _weather_command.register_commands(weather_parser)
    _pitch_enrichment_command.register_commands(pitch_enrichment_parser)

def execute_command(args):
    """Execute the requested command based on args."""
    command = args.command
    
    if command == 'retrosheet':
        return _retrosheet_command.execute_command(args)
    elif command == 'statcast':
        return _statcast_command.execute_command(args)
    elif command == 'people':
        return _people_command.execute_command(args)
    elif command == 'weather':
        return _weather_command.execute_command(args)
    elif command == 'enrich':
        return _pitch_enrichment_command.execute_command(args)
    elif command == 'run':
        return _run_command.execute_command(args)
    else:
        print(f"Unknown command: {command}")
        return 1