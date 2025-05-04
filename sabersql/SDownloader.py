#!/usr/bin/env python3

import os
from datetime import datetime
from .Utilities import _shell
from .BaseDownloader import BaseDownloader
import logging
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr

class StatcastDownloader(BaseDownloader):
    """
    Manages Statcast downloads using the pybaseball library.
    """
    
    def __init__(self, path):
        """
        Initializes a SDownloader based on the path to the SaberSQL data
        
        :param path: the path to the folder for all SaberSQL data
        """
        super().__init__(path)
        logging.getLogger("pybaseball").setLevel(logging.ERROR)
        
    def download(self, year=None, handler=lambda *args: None, force=False):
        """
        Downloads BaseballSavant files using pybaseball
        
        :param year: the year to be downloaded; defaults to all years 1999 to present
        :param handler: a function that takes in a double, representing the completion percentage of the download
        :param force: If True, download data even if already present
        """
        try:
            from pybaseball import statcast
        except ImportError:
            raise ImportError("pybaseball library is required for Statcast downloads. Install with 'pip install pybaseball'")
            
        years = self._get_years_range(year, start_year=1999)
        
        # Baseball months (March through November)
        months = list(range(3, 12))
        
        base_dir = os.path.join(self._path, "BaseballSavant")
        self._ensure_dir_exists(base_dir)
        
        tracker = self._init_tracker(base_dir)
        self._start_tracking(tracker, 'download', 
                          years=years, 
                          start_year=min(years), 
                          end_year=max(years),
                          force=force)
        
        try:
            # Create a list of all year/month combinations to download
            download_tasks = []
            for y in years:
                year_dir = os.path.join(base_dir, str(y))
                self._ensure_dir_exists(year_dir)
                for m in months:
                    month_name = datetime(y, m, 1).strftime("%m_%B")
                    csv_path = os.path.join(year_dir, f"{month_name}.csv")
                    if not force and os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                        continue
                    download_tasks.append((y, m))
            
            if not download_tasks:
                print("No Statcast data downloads needed - all data already exists")
                self._complete_tracking(tracker, 'download', success=True, 
                                     message="All data already downloaded",
                                     files_downloaded=0)
                handler(1, status="Statcast data download complete (no new data needed)")
                return
            
            total_tasks = len(download_tasks)
            completed_tasks = 0
            
            handler(0, status="Downloading Statcast data")
            
            all_results = []
            
            for y, m in download_tasks:
                try:
                    result = self._download_month_data(y, m)
                    all_results.append(result)
                    
                    completed_tasks += 1
                    progress = completed_tasks / total_tasks
                    
                    if result['status'] == 'success':
                        status = f"Downloading Statcast data - {result['month_name']} - {result.get('records', 0)} records"
                    elif result['status'] == 'empty':
                        status = f"Downloading Statcast data - {result['month_name']} - no data found"
                    elif result['status'] == 'skipped':
                        status = f"Downloading Statcast data - {result['month_name']} - already exists"
                    else:
                        status = f"Downloading Statcast data - {result['month_name']} - {result['status']}"
                    
                    handler(progress, status=status)
                    
                except Exception as e:
                    self._record_error(tracker, 'download', e, 
                                     year=y, month=m,
                                     completed=completed_tasks, 
                                     total=total_tasks)
                    completed_tasks += 1
                    progress = completed_tasks / total_tasks
                    handler(progress, status=f"Error downloading {y}/{m}: {str(e)[:50]}")
            
            success_count = sum(1 for r in all_results if r['status'] == 'success')
            error_count = sum(1 for r in all_results if r['status'] == 'error')
            empty_count = sum(1 for r in all_results if r['status'] == 'empty')
            skipped_count = sum(1 for r in all_results if r['status'] == 'skipped')
            total_records = sum(r.get('records', 0) for r in all_results)
            
            # Final summary status and tracking completion
            success = success_count > 0
            summary = f"Complete: {total_records:,} records, {success_count} success, {error_count} errors"
            
            self._complete_tracking(tracker, 'download', success=success, 
                                 downloaded_files=success_count,
                                 total_records=total_records,
                                 errors=error_count,
                                 empty=empty_count,
                                 skipped=skipped_count)
            
            handler(1.0, status=summary)
            
        except Exception as e:
            self._complete_tracking(tracker, 'download', success=False, error=e)
            raise
    
    def _download_month_data(self, year, month):
        """
        Download data for a specific year and month.
        
        :param year: Year to download
        :param month: Month to download
        :return: Result dictionary
        """
        from pybaseball import statcast
        
        month_name = datetime(year, month, 1).strftime("%m_%B")
        
        try:
            year_dir = os.path.join(self._path, "BaseballSavant", str(year))
            self._ensure_dir_exists(year_dir)
            
            csv_path = os.path.join(year_dir, f"{month_name}.csv")
            
            if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
                return {
                    'year': year,
                    'month': month,
                    'month_name': month_name,
                    'status': 'skipped',
                    'message': 'File already exists'
                }
            
            month_start = f"{year}-{month:02d}-01"
            if month == 12:
                month_end = f"{year}-12-31"
            else:
                next_month = month + 1
                next_year = year
                if month == 12:
                    next_month = 1
                    next_year = year + 1
                month_end = f"{next_year}-{next_month:02d}-01"
            
            # Capture stdout/stderr from pybaseball to prevent output spew
            stdout_buffer = StringIO()
            stderr_buffer = StringIO()
            
            # Use retry logic from parent class
            def fetch_statcast():
                with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                    return statcast(start_dt=month_start, end_dt=month_end)
            
            def error_handler(e, attempt, max_retries):
                print(f"Retry {attempt}/{max_retries} for {year}/{month_name} - {str(e)[:50]}")
            
            month_data = self._retry_operation(
                fetch_statcast, 
                max_retries=3, 
                backoff_factor=2,
                error_handler=error_handler
            )
            
            if month_data is not None and not month_data.empty:
                month_data.to_csv(csv_path, index=False)
                
                return {
                    'year': year,
                    'month': month,
                    'month_name': month_name,
                    'status': 'success',
                    'records': len(month_data),
                    'message': f"Downloaded {len(month_data)} records"
                }
            elif month_data is None or month_data.empty:
                with open(csv_path, 'w') as f:
                    f.write(f"# No Statcast data found for {month_start} to {month_end}\n")
                return {
                    'year': year,
                    'month': month,
                    'month_name': month_name,
                    'status': 'empty',
                    'message': 'No data returned'
                }
        
        except Exception as e:
            error_message = str(e)
            try:
                with open(f"{csv_path}.error", 'w') as f:
                    f.write(f"# Error downloading data: {error_message}\n")
            except:
                pass
            return {
                'year': year,
                'month': month,
                'month_name': month_name,
                'status': 'error',
                'message': error_message
            }
    
    def undownload(self, year=None, handler=lambda *args: None):
        """
        Undoes downloads of BaseballSavant files
        
        :param year: the year to be un-downloaded; defaults to all years 1999 to present
        :param handler: a function that takes in a double, representing the completion percentage of the un-download
        """
        years = self._get_years_range(year, start_year=1999)
        base_dir = os.path.join(self._path, "BaseballSavant")
        
        tracker = self._init_tracker(base_dir, 'undownload')
        self._start_tracking(tracker, 'undownload', years=years)
        
        try:
            handler(0, status="Undoing Statcast download")
            
            for i, year in enumerate(years):
                year_dir = os.path.join(self._path, "BaseballSavant", str(year))
                if os.path.exists(year_dir):
                    _shell(f"rm -rf \"{year_dir}\"")
                handler((i + 1) / len(years), status=f"Undoing Statcast download for {year}")
                
            self._complete_tracking(tracker, 'undownload', success=True, years_removed=len(years))
            return True
            
        except Exception as e:
            self._complete_tracking(tracker, 'undownload', success=False, error=e)
            handler(1, status=f"Error undoing Statcast download: {str(e)}")
            return False