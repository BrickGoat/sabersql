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
        self._repo_base_url = "https://github.com/chadwickbureau/register"
        self._raw_data_url = "https://github.com/chadwickbureau/register/raw/master/data"

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
            print("No people-*.csv files found in the repository. Falling back to people.csv")
            files_to_download = ["people.csv"]
        
        total_files = len(files_to_download)
        downloaded_files = 0
        
        print(f"Found {total_files} files to download")
        
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
        Discover all people-*.csv files in the repository
        
        :return: List of filenames matching the people-*.csv pattern
        """
        try:
            def fetch_repo_listing():
                response = requests.get(f"{self._repo_base_url}/tree/master/data")
                response.raise_for_status()
                return response.text
            
            html_content = self._retry_operation(
                fetch_repo_listing,
                max_retries=3,
                error_handler=lambda e, a, m: print(f"Retry {a}/{m} for repository listing: {str(e)[:50]}")
            )
            
            # Look for all people-*.csv files in the HTML response
            pattern = r'href="[^"]+/blob/master/data/(people-[^"]+\.csv)"'
            matches = re.findall(pattern, html_content)
            
            return list(set(matches))
                
        except Exception as e:
            print(f"Error discovering people CSV files: {str(e)}")
            return []