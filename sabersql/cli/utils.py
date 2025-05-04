#!/usr/bin/env python3

import sys
import shutil

def progress(fraction, status=''):
    """
    Simple progress display that properly overwrites the entire line.
    
    :param fraction: Progress value between 0.0 and 1.0
    :param status: Status message to display
    """
    term_width = shutil.get_terminal_size(fallback=(80, 24)).columns
    
    bar_len = 40
    filled_len = int(round(bar_len * fraction))
    bar = '=' * filled_len + ' ' * (bar_len - filled_len)
    
    percents = round(100.0 * fraction, 1)
    
    text = f'[{bar}] {percents}% ...{status}'
    
    padded_text = text.ljust(term_width - 1)
    
    sys.stdout.write('\r' + padded_text)
    sys.stdout.flush()
    
    if fraction >= 1:
        sys.stdout.write('\n')
        sys.stdout.flush()