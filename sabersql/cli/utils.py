#!/usr/bin/env python3

import sys

def progress(fraction, status=''):
    """
    Display a progress bar in the console.
    
    :param fraction: Number between 0 and 1 indicating progress
    :param status: Status message to display
    """
    bar_len = 40
    filled_len = int(round(bar_len * fraction))

    percents = round(100.0 * fraction, 1)
    bar = '=' * filled_len + ' ' * (bar_len - filled_len)

    text = '[%s] %s%% ...%s' % (bar, percents, status)
    sys.stdout.write(text)
    sys.stdout.write('\b' * len(text))
    sys.stdout.flush()

    if fraction >= 1:
        sys.stdout.write('\n')
        sys.stdout.flush()