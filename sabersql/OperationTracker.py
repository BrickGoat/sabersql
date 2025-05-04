#!/usr/bin/env python3

import os
import json
from datetime import datetime
import traceback

class OperationTracker:
    """
    Tracks the status of different operations on data.
    
    This is a more flexible replacement for the original ProgressHandler,
    allowing tracking of multiple operations independently.
    """
    
    def __init__(self, data_path):
        """
        Initialize the tracker with the path to the data directory.
        
        :param data_path: Path to the data directory
        """
        self.data_path = data_path
        self.tracker_file = os.path.join(data_path, "operations.json")
        self._ensure_tracker_exists()
    
    def _ensure_tracker_exists(self):
        """Ensure the tracker file exists."""
        os.makedirs(self.data_path, exist_ok=True)
        if not os.path.exists(self.tracker_file):
            # Create an empty tracker file
            self._save_data({})
    
    def _load_data(self):
        """Load tracker data from the JSON file."""
        try:
            with open(self.tracker_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_data(self, data):
        """Save tracker data to the JSON file."""
        with open(self.tracker_file, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def get_operation_status(self, operation_name):
        """
        Get the status of a specific operation.
        
        :param operation_name: Name of the operation (e.g., 'download', 'import')
        :return: Dictionary with operation status or None if not found
        """
        data = self._load_data()
        return data.get(operation_name)
    
    def start_operation(self, operation_name, **metadata):
        """
        Mark an operation as started.
        
        :param operation_name: Name of the operation
        :param metadata: Additional metadata to store with the operation
        """
        data = self._load_data()
        
        data[operation_name] = {
            'status': 'started',
            'start_time': datetime.now().isoformat(),
            'metadata': metadata
        }
        
        self._save_data(data)
    
    def complete_operation(self, operation_name, success=True, error=None, **metadata):
        """
        Mark an operation as completed.
        
        :param operation_name: Name of the operation
        :param success: Whether the operation completed successfully
        :param error: Exception object or error information
        :param metadata: Additional metadata to store with the operation
        """
        data = self._load_data()
        
        op_data = data.get(operation_name, {})
        
        op_data.update({
            'status': 'success' if success else 'failed',
            'end_time': datetime.now().isoformat()
        })
        
        if error is not None:
            error_info = {
                'error_type': error.__class__.__name__ if hasattr(error, '__class__') else 'Unknown',
                'error_message': str(error),
                'traceback': traceback.format_exc()
            }
            op_data['error'] = error_info
        
        op_metadata = op_data.get('metadata', {})
        op_metadata.update(metadata)
        op_data['metadata'] = op_metadata
        
        data[operation_name] = op_data
        self._save_data(data)
    
    def record_error(self, operation_name, error, **metadata):
        """
        Record an error for an operation without changing its status.
        
        :param operation_name: Name of the operation
        :param error: Exception object or error description
        :param metadata: Additional metadata to store with the error
        """
        data = self._load_data()
        
        op_data = data.get(operation_name, {})
        
        error_info = {
            'error_type': error.__class__.__name__ if hasattr(error, '__class__') else 'Unknown',
            'error_message': str(error),
            'error_time': datetime.now().isoformat(),
            'traceback': traceback.format_exc()
        }
        
        if 'errors' not in op_data:
            op_data['errors'] = []
        op_data['errors'].append(error_info)
        
        op_metadata = op_data.get('metadata', {})
        op_metadata.update(metadata)
        op_data['metadata'] = op_metadata
        
        data[operation_name] = op_data
        self._save_data(data)
    
    def reset_operation(self, operation_name):
        """
        Reset an operation's status.
        
        :param operation_name: Name of the operation
        """
        data = self._load_data()
        
        if operation_name in data:
            del data[operation_name]
            self._save_data(data)
    
    def is_operation_complete(self, operation_name):
        """
        Check if an operation is complete.
        
        :param operation_name: Name of the operation
        :return: True if the operation is complete and successful, False otherwise
        """
        status = self.get_operation_status(operation_name)
        return status is not None and status.get('status') == 'success'