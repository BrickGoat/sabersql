#!/usr/bin/env python3

import os
import requests
import re
from .Utilities import _download, _shell
from .BaseDownloader import BaseDownloader


class PDownloader(BaseDownloader):
    """
    Manages player downloads.
    """

    def __init__(self, path):
        """
        Initializes a PDownloader based on the path to the SaberSQL data

        :param path: the path to the folder for all SaberSQL data
        """
        super().__init__(path)
        self._github_api_url = "https://api.github.com/repos/chadwickbureau/register/contents/data"
        self._raw_data_url = "https://raw.githubusercontent.com/chadwickbureau/register/master/data"

    def download(self, handler=lambda *args: None):
        """
        Downloads player files

        :param handler: a function that takes in a double, representing the completion percentage of the download
        """
        person_dir = os.path.join(self._path, "Person")
        self._ensure_dir_exists(person_dir)
        
        handler(0, status="Discovering people data files")
        
        files_to_download = self._get_people_csv_files()
        
        if not files_to_download:
            print("No people files found in repository. Defaulting to people.csv")
            files_to_download = ["people.csv"]
        
        total_files = len(files_to_download)
        downloaded_files = 0
        
        print(f"Found {total_files} files to download: {', '.join(files_to_download)}")
        
        handler(0, status="Downloading people data")
        
        for filename in files_to_download:
            source_url = f"{self._raw_data_url}/{filename}"
            destination = os.path.join(person_dir, filename)
            
            try:
                print(f"Downloading {filename}...")
                
                def download_file():
                    _download(source_url, destination)
                    return True
                
                self._retry_operation(
                    download_file,
                    max_retries=3,
                    error_handler=lambda e, a, m: print(f"Retry {a}/{m} for {filename}: {str(e)[:50]}")
                )
                
                downloaded_files += 1
                handler(downloaded_files / total_files, 
                        status=f"Downloading people data ({downloaded_files}/{total_files})")
            except Exception as e:
                print(f"Error downloading {filename}: {str(e)}")
        
        handler(1, status="People data download complete")
        
    def undownload(self, handler=lambda *args: None):
        """
        Undoes download of player files

        :param handler: a function that takes in a double, representing the completion percentage of the download undoing
        """
        status = "Undoing people download"
        handler(0, status=status)
        
        person_dir = os.path.join(self._path, "Person")
        
        if os.path.exists(person_dir):
            _shell(f"rm -f \"{person_dir}\"/*.csv")
            print(f"Removed all CSV files from {person_dir}")
        
        handler(1, status=status)
    
    def _get_people_csv_files(self):
        """
        Discover all people*.csv files in the repository using GitHub API
        
        :return: List of filenames matching the people*.csv pattern
        """
        try:
            def fetch_repo_contents():
                headers = {
                    'Accept': 'application/vnd.github.v3+json',
                    'User-Agent': 'SaberSQL-Downloader'
                }
                response = requests.get(
                    self._github_api_url,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                return response.json()
            
            # Fetch repository contents using GitHub API
            contents = self._retry_operation(
                fetch_repo_contents,
                max_retries=3,
                error_handler=lambda e, a, m: print(f"API request attempt {a}/{m} failed: {str(e)[:100]}")
            )
            
            # Filter files to include only CSV files starting with 'people'
            csv_files = []
            
            if isinstance(contents, list):
                for item in contents:
                    if (item.get('type') == 'file' and 
                        item.get('name', '').endswith('.csv') and 
                        item.get('name', '').startswith('people')):
                        csv_files.append(item['name'])
            
            if not csv_files:
                # If API request returned valid response but no matching files
                print("No people*.csv files found in repository contents.")
                return ["people.csv"]  # Default to single file
            
            print(f"GitHub API: Found {len(csv_files)} people*.csv files")
            return csv_files
                
        except Exception as e:
            print(f"Error querying GitHub API: {str(e)}")
            # Fallback method: try one final attempt with a direct request for people.csv
            print("Falling back to default file: people.csv")
            return ["people.csv"]