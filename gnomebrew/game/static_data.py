"""
This module manages static data in python.
Static data is saved in the game's `data` directory and automatically loaded during boot to be available quickly, e.g.
for generation tasks.

Makes all CSV data in the `data` directory available as pandas dataframes.
"""

from gnomebrew import app
from os import listdir, walk
from os.path import isfile, join
import pandas as pd
import numpy as np

from gnomebrew.game import boot_routine
from gnomebrew.game.gnomebrew_io import GameResponse
from gnomebrew.game.testing import application_test


dataframes = dict()



@boot_routine
def load_all_data_sources():
    """
    This routine scans the data directory + subdirectories for valid data files and makes them available in game.
    """
    for root, dirs, files in walk(app.config['DATA_DIR']):
        for file in files:
            if file.lower().endswith('.csv'):
                # Generate File id
                file_id = file[:-4]
                assert file_id not in dataframes
                # Read in CSV file
                dataframes[file_id] = pd.read_csv(join(root, file))


@application_test(name='Import Data Test', category='Data')
def import_data_test():
    response = GameResponse()
    for root, dirs, files in walk(app.config['DATA_DIR']):
        response.log(f"{root=}, {dirs=}, {files=}")

    return response

@application_test(name='List Available Data Sources', category='Data')
def list_data_sources():
    response = GameResponse()

    for frame_id in dataframes:
        response.log(f"{frame_id} ({len(dataframes[frame_id].columns)} columns, {len(dataframes[frame_id])} rows)")

    return response
