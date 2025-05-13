#!/usr/bin/env python3

from .base_command import BaseCommand
from . import commands
import configparser
import shlex
import re

class RunCommand(BaseCommand):
    """Command handler for running operations defined in the config file."""
    
    def __init__(self):
        super().__init__("run")
    
    def register_commands(self, parser):
        """Register command without subcommands."""
        self._add_common_args(parser)
        return parser
    
    def execute_command(self, args):
        """Execute operations defined in the config file."""
        try:
            config_path = args.config
            
            if not config_path:
                print("Error: Config file path is required for the run command.")
                print("Usage: sabersql run --config <config_path>")
                return False
                
            operations = self._get_operations(config_path)
            
            if not operations:
                print(f"Error: No valid operations found in the config file '{config_path}'.")
                return False
                
            return self._execute_operations(operations, args, config_path)
            
        except Exception as e:
            print(f"Error running operations from config: {str(e)}")
            if hasattr(args, 'debug') and args.debug:
                import traceback
                print(traceback.format_exc())
            return False
    
    def _parse_param_value(self, value_str):
        """Parse parameter value with proper type conversion."""
        value_str = value_str.strip()
        
        # Check for quoted string (keep as string)
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]
        
        # Try to convert to boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False
            
        # Try to convert to int
        try:
            return int(value_str)
        except ValueError:
            pass
            
        # Try to convert to float
        try:
            return float(value_str)
        except ValueError:
            pass
            
        # Return as string if no other conversion works
        return value_str
    
    def _parse_operation_params(self, param_string):
        """Parse the parameter string into a dictionary of parameters."""
        params = {}
        
        # Default values for required parameters
        params['undo'] = False
        
        # For empty strings, return just the defaults
        if not param_string.strip():
            return params
            
        # Split the string by commas, but respect quoted values
        try:
            # First, try to use shlex which handles quotes properly
            parts = []
            for part in shlex.split(param_string, posix=True):
                # shlex removes the quotes, but we need to resplit by commas
                parts.extend(part.split(','))
        except ValueError:
            # Fall back to a simpler approach if shlex fails
            parts = re.split(r',\s*', param_string)
            
        for part in parts:
            if not part.strip():
                continue
                
            # Look for key=value pattern
            if '=' in part:
                key, value = part.split('=', 1)
                key = key.strip()
                params[key] = self._parse_param_value(value)
            else:
                # Handle flag parameters (no value)
                param_name = part.strip()
                if param_name.lower() == 'undo':
                    params['undo'] = True
                elif param_name:
                    # Boolean flags without values default to True
                    params[param_name] = True
        
        return params
        
    def _get_operations(self, config_path):
        """Parse operations from the configuration file."""
        try:
            parser = configparser.ConfigParser()
            parser.read(config_path)
            
            if not parser.has_section('operations'):
                return []
                
            operations = []
            
            for operation_id, param_string in parser['operations'].items():
                # Parse the parameters for this operation
                params = self._parse_operation_params(param_string)
                
                # Create the operation dictionary with the command
                operation = {
                    'command': operation_id.strip(),
                    'undo': params.pop('undo', False)  # Extract undo flag
                }
                
                # Add subcommand from params or use default
                operation['subcommand'] = params.pop('subcommand', 'process')
                
                # Handle special cases for backwards compatibility
                if operation['command'] == 'enrich':
                    # Convert boolean flags to the right parameter names
                    if 'timestamp' in params or 'timestamps' in params:
                        operation['timestamps'] = True
                    if 'venue' in params or 'venues' in params:
                        operation['venues'] = True
                
                # Add all remaining parameters
                operation.update(params)
                
                operations.append(operation)
            
            return operations
        except Exception as e:
            print(f"Error parsing operations from config: {str(e)}")
            return []
    
    def _execute_operations(self, operations, args, config_path):
        """Execute all operations in sequence."""
        from argparse import Namespace
        from ..config import load_config
        
        # Load base config for global settings
        base_config = load_config(config_path)
        
        success = True
        
        for i, operation in enumerate(operations):
            print(f"\nExecuting operation {i+1}/{len(operations)}: {operation['command']} {operation.get('subcommand', '')}")
            
            # Create a new args namespace for this operation
            op_args = Namespace()
            
            # Set default values for required attributes
            setattr(op_args, 'undo', False)
            setattr(op_args, 'debug', False)
            
            # Copy global args from config
            for key, value in base_config.items():
                setattr(op_args, key, value)
            
            # Copy command-line args that would override config
            for param in ['user', 'password', 'address', 'schema', 'path', 'debug']:
                if hasattr(args, param) and getattr(args, param) is not None:
                    setattr(op_args, param, getattr(args, param))
            
            # Set operation-specific args
            op_args.command = operation['command']
            op_args.subcommand = operation.get('subcommand')
            
            # Set all other parameters from the operation
            for key, value in operation.items():
                if key not in ['command', 'subcommand']:
                    setattr(op_args, key, value)
            
            # Execute the operation
            try:
                result = commands.execute_command(op_args)
                
                if not result:
                    print(f"Operation {i+1} failed: {operation['command']} {operation.get('subcommand', '')}")
                    success = False
                    # Continue with other operations
            except Exception as e:
                print(f"Error executing operation {i+1}: {str(e)}")
                if hasattr(args, 'debug') and args.debug:
                    import traceback
                    print(traceback.format_exc())
                success = False
            
        return success
    
    def create_downloader(self, args):
        """Required abstract method implementation. Not used for run command."""
        return None

    def create_importer(self, args, connection):
        """Required abstract method implementation. Not used for run command."""
        return None
        
    def supports_date_range(self):
        """Run command doesn't directly support date ranges."""
        return False