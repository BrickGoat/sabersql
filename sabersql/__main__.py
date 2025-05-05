#!/usr/bin/env python3

import sys
import argparse
from .cli import commands
from .config import load_config

def main():
    """Entry point for the sabersql command line interface."""
    parser = argparse.ArgumentParser(
        description="SaberSQL: Download and import baseball data into a MySQL database.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # Global configuration options
    config_group = parser.add_argument_group('configuration options')
    config_group.add_argument("--config", help="Path to configuration file")
    
    # Database connection options
    db_group = parser.add_argument_group('database options')
    db_group.add_argument("-u", "--user", help="MySQL username")
    db_group.add_argument("-p", "--password", help="MySQL password")
    db_group.add_argument("-a", "--address", help="MySQL server address")
    db_group.add_argument("-s", "--schema", help="MySQL schema name")
    
    subparsers = parser.add_subparsers(dest="command", help="Data source to process")
    
    commands.register_commands(subparsers)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
        
    config = {}
    if hasattr(args, 'config') and args.config:
        config = load_config(args.config)
    else:
        config = load_config()
    
    for key, value in config.items():
        if hasattr(args, key) and getattr(args, key) is None and value is not None:
            setattr(args, key, value)
    
    if not hasattr(args, 'path') or args.path is None:
        if 'path' in config:
            args.path = config['path']
        else:
            print("Error: No data path specified. Please provide a path in the config file or command line.")
            return 1
    
    for param in ['user', 'password', 'address', 'schema']:
        if not hasattr(args, param) or getattr(args, param) is None:
            print(f"Error: {param} not specified. Please provide in config file or command line.")
            return 1
    
    return commands.execute_command(args)

if __name__ == "__main__":
    sys.exit(main() or 0)