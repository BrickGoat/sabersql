#!/usr/bin/env python3

import os
import pandas
import subprocess
import requests
import zipfile
import time
import sys
import random

def _download(url, target, unzip=None, overwrite=False):
    """
    Synchronously downloads a file to a given location, mimicking a browser
    
    :param url: the url of the file to download
    :param target: the location to download the file to
    :param unzip: location to unzip the downloaded file to (if applicable)
    :param overwrite: if True, the file will be overwritten if it already exists (default False)
    :return: None
    """
    # Create target directory if it doesn't exist
    os.makedirs(os.path.dirname(target), exist_ok=True)

    # Check if file needs to be downloaded
    if overwrite or (not unzip and not os.path.isfile(target)) or (unzip and not os.path.isdir(unzip)):
        # Common browser user agents (rotated randomly)
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36'
        ]
        
        # Browser-like headers
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        }
        
        # Create a session for connection pooling and cookie persistence
        session = requests.Session()
        
        # Now download the file
        try:
            start_time = time.time()
            with session.get(url, headers=headers, stream=True, timeout=60) as response:
                response.raise_for_status()  # Raise exception for HTTP errors
                
                # Get total file size if available
                total_size = int(response.headers.get('content-length', 0))
                
                # If we got a tiny response and we're expecting CSV data, it might be an error page
                if total_size < 500 and url.endswith('.csv') and 'text/html' in response.headers.get('Content-Type', ''):
                    print(f"\nWarning: Received very small response. This might be an error page, not actual CSV data.")
                
                # Download the file in chunks
                with open(target, 'wb') as f:
                    if total_size == 0:
                        # If content-length is not available
                        f.write(response.content)
                    else:
                        # Download with progress reporting
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                
                
                elapsed = time.time() - start_time
                print(f"\nDownload completed in {elapsed:.2f} seconds")
                
                # Unzip if requested
                if unzip:
                    print(f"Extracting to {unzip}...")
                    os.makedirs(unzip, exist_ok=True)
                    
                    with zipfile.ZipFile(target, 'r') as zip_ref:
                        zip_ref.extractall(unzip)
                    
                    # Remove the zip file
                    os.remove(target)
                    
                # Verify it's not an empty or HTML error page for CSV downloads
                if url.endswith('.csv') and os.path.exists(target) and os.path.getsize(target) > 0:
                    with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                        first_line = f.readline().strip()
                        if first_line.startswith('<!DOCTYPE html>') or first_line.startswith('<html'):
                            print(f"Warning: Downloaded file appears to be HTML, not CSV data. Server may have returned an error page.")
                            # Delete the HTML error page so we don't treat it as valid data
                            os.remove(target)
                            raise Exception("Server returned HTML instead of CSV data")
                time.sleep(5)
        except Exception as e:
            print(f"Download failed: {e}")
            # Fall back to curl with browser-like user agent
            print("Falling back to curl method...")
            
            # Use a random user agent
            user_agent = random.choice(user_agents)
            
            curl_command = (
                f'curl "{url}" -L '
                f'--user-agent "{user_agent}" '
                f'--connect-timeout 30 '
                f'--max-time 300 '
                f'-H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8" '
                f'-H "Accept-Language: en-US,en;q=0.5" '
                f'-H "Connection: keep-alive" '
                f'-o "{target}"'
            )
            
            _shell(curl_command)
            
            if unzip:
                _shell(f'unzip "{target}" -d "{unzip}"')
                _shell(f'rm "{target}"')

def _import_csv(path, header=None):
    """
    Reads a csv file into memory

    :param path: the path to the csv
    :param header: the header for the file (as array of strings); if None (default), the headers will come from the first line of the file
    :return: a pandas DataFrame of the csv
    """

    if header:
        return pandas.read_csv(path, header=None, names=header)
    else:
        dataframe = pandas.read_csv(path, low_memory=False)
        names_so_far = set()
        for col in dataframe.columns:
            if col in names_so_far:
                dataframe = dataframe.drop(columns=col)
            else:
                names_so_far.add(col + ".1")
        return dataframe


def _shell(command):
    """
    Calls a shell command

    :param command: the command to be run
    :return: (stdOut, stdErr)
    """

    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    if out is not None:
        out = out.decode('utf-8')
    if err is not None:
        err = err.decode('utf-8')
    return out, err