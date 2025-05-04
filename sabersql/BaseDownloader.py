#!/usr/bin/env python3

import time
from datetime import datetime
from .Utilities import _shell
from .OperationTracker import OperationTracker

class BaseDownloader:
    """
    Base class for all downloaders.
    Provides common functionality for SDownloader, RDownloader, PDownloader, etc.
    """
    
    def __init__(self, path):
        """
        Initialize a downloader with the path to store data.
        
        :param path: Base path for storing downloaded data
        """
        self._path = path
    
    def download(self, year=None, handler=lambda *args: None):
        """
        Download data for the specified year(s).
        
        :param year: Year(s) to download, or None for all years
        :param handler: Progress handler function
        """
        raise NotImplementedError("Subclasses must implement download method")
    
    def undownload(self, year=None, handler=lambda *args: None):
        """
        Undo download for the specified year(s).
        
        :param year: Year(s) to undownload, or None for all years
        :param handler: Progress handler function
        """
        raise NotImplementedError("Subclasses must implement undownload method")
    
    def _get_years_range(self, year=None, start_year=1903, end_year=None):
        """
        Get the range of years to process.
        
        :param year: Specific year to process, or None for all years
        :param start_year: Default start year if processing all years
        :param end_year: Default end year if processing all years (defaults to current year)
        :return: List of years to process
        """
        if year:
            return [year]
        else:
            if end_year is None:
                end_year = datetime.now().year
            return [y for y in range(start_year, end_year + 1)]
            
    def _ensure_dir_exists(self, directory):
        """
        Ensure a directory exists.
        
        :param directory: Directory path to ensure exists
        """
        _shell(f"mkdir -p \"{directory}\"")
        
    def _retry_operation(self, operation, max_retries=3, backoff_factor=2, 
                         error_handler=None, silent=False):
        """
        Retry an operation with exponential backoff.
        
        :param operation: Function to execute
        :param max_retries: Maximum number of retry attempts
        :param backoff_factor: Backoff multiplier for retries
        :param error_handler: Optional function to call with each error
        :param silent: Whether to suppress error messages
        :return: Result of the operation
        :raises: The last exception if all retries fail
        """
        attempt = 0
        last_exception = None
        
        while attempt <= max_retries:
            try:
                return operation()
            except Exception as e:
                last_exception = e
                attempt += 1
                
                if error_handler and callable(error_handler):
                    error_handler(e, attempt, max_retries)
                elif not silent:
                    print(f"Attempt {attempt}/{max_retries} failed: {str(e)}")
                
                if attempt > max_retries:
                    break
                    
                wait_time = backoff_factor ** (attempt - 1)
                time.sleep(wait_time)
        
        raise last_exception
        
    def _init_tracker(self, data_dir, operation_type='download'):
        """
        Initialize an operation tracker for the given data directory.
        
        :param data_dir: Directory for data storage and tracking
        :param operation_type: Type of operation being tracked ('download', 'undownload', etc.)
        :return: OperationTracker instance
        """
        self._ensure_dir_exists(data_dir)
        tracker = OperationTracker(data_dir)
        
        # Check if operation is already complete
        if operation_type == 'download' and tracker.is_operation_complete(operation_type):
            print(f"{self.__class__.__name__} download already marked as complete.")
            
        return tracker
        
    def _start_tracking(self, tracker, operation_type='download', **metadata):
        """
        Start tracking an operation.
        
        :param tracker: OperationTracker instance
        :param operation_type: Type of operation being tracked
        :param metadata: Additional metadata to store with the operation
        """
        tracker.start_operation(operation_type, **metadata)
        
    def _complete_tracking(self, tracker, operation_type='download', success=True, error=None, **metadata):
        """
        Complete tracking an operation.
        
        :param tracker: OperationTracker instance
        :param operation_type: Type of operation being tracked
        :param success: Whether the operation completed successfully
        :param error: Error information if the operation failed
        :param metadata: Additional metadata to store with the operation
        """
        tracker.complete_operation(operation_type, success=success, error=error, **metadata)
        
    def _record_error(self, tracker, operation_type, error, **metadata):
        """
        Record an error without changing operation status.
        
        :param tracker: OperationTracker instance
        :param operation_type: Type of operation being tracked
        :param error: Error that occurred
        :param metadata: Additional metadata about the error context
        """
        tracker.record_error(operation_type, error, **metadata)