#!/usr/bin/env python3

import os
import configparser

def load_config(config_file=None):
    """
    Load configuration from an INI file.
    
    :param config_file: Path to the config file (default: look for sabersql.ini in current directory)
    :return: Dictionary with configuration values
    """
    config = {}
    
    # Default config file locations to try
    config_locations = [
        config_file, 
        os.path.join(os.getcwd(), 'sabersql.ini'), 
        os.path.expanduser('~/.sabersql.ini'),   
    ]
    
    # Try to find and load a config file
    parser = configparser.ConfigParser()
    for location in config_locations:
        if location and os.path.exists(location):
            try:
                parser.read(location)
                break
            except Exception:
                continue
    
    # Database settings
    if 'database' in parser:
        config['user'] = parser.get('database', 'user', fallback='root')
        config['password'] = parser.get('database', 'password', fallback='password')
        config['address'] = parser.get('database', 'address', fallback='localhost')
        config['schema'] = parser.get('database', 'schema', fallback='sabersql')
    
    # Path settings
    if 'paths' in parser:
        config['path'] = parser.get('paths', 'data_dir', fallback=None)
        config['stadiums'] = parser.get('paths', 'stadiums_file', fallback=None)
        config['stations'] = parser.get('paths', 'stations_file', fallback=None)
    
    # Weather settings
    if 'weather' in parser:
        config['start_date'] = parser.get('weather', 'start_date', fallback=None)
        config['end_date'] = parser.get('weather', 'end_date', fallback=None)
        
        # Handle numeric values
        try:
            config['max_distance'] = parser.getfloat('weather', 'max_distance', fallback=None)
        except (ValueError, configparser.NoOptionError):
            config['max_distance'] = None
            
        try:
            config['delay'] = parser.getint('weather', 'delay', fallback=None)
        except (ValueError, configparser.NoOptionError):
            config['delay'] = None
    
    return config