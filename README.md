# SaberSQL

SaberSQL is a software tool to help scrape data on MLB games from [Retrosheet](https://www.retrosheet.org) (dating back
to 1903) and [BaseballSavant](https://baseballsavant.mlb.com), as well as information on players, umpires, and managers
(via the [Chadwick Baseball Bureau Register](https://github.com/chadwickbureau/register)). This data can then be
imported to a MySQL database, allowing you to do customized queries on over a century of data.

## Installation
### Requirements
For SaberSQL to work, you must have already installed [MySQL Community Server](https://dev.mysql.com/downloads/mysql/)
and [Chadwick](http://chadwick.sourceforge.net/doc/index.html). MySQL is straightforward to install, and there is an
excellent guide to install Chadwick
[here](https://www.pitchbypitch.com/2013/11/29/installing-chadwick-software-on-mac/).
### Install SaberSQL
To install:
```bash
pip3 install sabersql
```

## Usage
SaberSQL provides commands for managing different baseball data sources. Each command supports date-based filtering and various operations.

### Basic Structure
```bash
sabersql [options] {command} [command-options] [path]
```

Global options:
- `--config CONFIG` - Path to a configuration file
- `-u USER`, `--user USER` - MySQL username
- `-p PASSWORD`, `--password PASSWORD` - MySQL password
- `-a ADDRESS`, `--address ADDRESS` - MySQL server address
- `-s SCHEMA`, `--schema SCHEMA` - MySQL schema name

Available commands:
- `retrosheet` - Manage Retrosheet data
- `statcast` - Manage BaseballSavant Statcast data
- `people` - Manage player, manager, and umpire data
- `weather` - Manage weather data
- `enrich` - Enrich pitch data with additional information

### Command Operations
Most commands support these subcommands:
- `download` - Download data only
- `import` - Import previously downloaded data
- `process` - Download and import data (combined operation)

Most commands also support:
- `--start-date DATE` - Process data from this date (YYYY-MM-DD format)
- `--end-date DATE` - Process data up to this date (YYYY-MM-DD format)
- `--undo` - Undo the operation

### Examples

#### Download Retrosheet data for a date range:
```bash
sabersql retrosheet download [path] --start-date 2023-01-01 --end-date 2023-12-31
```

#### Import Statcast data that's already been downloaded:
```bash
sabersql statcast import [path] --start-date 2022-04-01 --end-date 2022-10-31
```

#### Download and import people data:
```bash
sabersql people process [path]
```

#### Manage weather data:
```bash
sabersql weather download [path] --start-date 2023-04-01 --end-date 2023-10-31 --stadiums stadiums.csv --stations stations.csv
```

#### Enrich pitch data:
The `enrich` command has a simplified structure without subcommands:
```bash
sabersql enrich [path] --timestamps --venues
```

Options for enrichment:
- `--timestamps` - Add pitch timestamps
- `--venues` - Add venue information
- `--batch-size SIZE` - Number of records to process in each batch
- `--start-date DATE` - Only enrich pitches from this date
- `--end-date DATE` - Only enrich pitches up to this date

If neither `--timestamps` nor `--venues` is specified, both will be processed.

### Using a Configuration File
You can create a configuration file to set default values:

```ini
[DEFAULT]
path=/path/to/data
user=root
password=yourpassword
address=localhost
schema=baseball
```

Then use it with:
```bash
sabersql --config config.ini retrosheet download --start-date 2023-01-01 --end-date 2023-12-31
```

#### Notes
- Data will not be re-downloaded or re-imported if a command is run multiple times. Additionally, a process will resume
from where it left off if restarted.
- These processes are not fast. It will take many hours to download and import all data.

## Schema
The structure of the database is five tables: [person](#person), [pitch](#pitch), [event](#event), [game](#game),
[sub](#sub), [weather](#weather), and [venue](#venue).

#### <a name="person"></a>person
Each entry in this table represents someone who was a player, umpire, and/or manager.
#### <a name="pitch"></a>pitch
Each entry in this table represents a pitch recorded by BaseballSavant. Descriptions of each field can be found
[here](https://baseballsavant.mlb.com/csv-docs). Timestamps and venue data from [statsapi](https://pypi.org/project/MLB-StatsAPI/) can also be added.
#### <a name="event"></a>event
Each entry in this table represents an event that Chadwick processed from Retrosheet data. Descriptions of each field
can be found [here](http://chadwick.sourceforge.net/doc/cwevent.html).
#### <a name="game"></a>game
Each entry in this table represents a game that Chadwick processed from Retrosheet data. Descriptions of each field
can be found [here](http://chadwick.sourceforge.net/doc/cwgame.html).
#### <a name="sub"></a>sub
Each entry in this table represents a substitution in a game that Chadwick processed from Retrosheet data. Descriptions
of each field can be found [here](http://chadwick.sourceforge.net/doc/cwsub.html).
#### <a name="weather"></a>weather
Each entry in this table a weather station measurement from the [Iowa Enviroment Mesonet](https://mesonet.agron.iastate.edu/request/download.phtml). Each weather station is the closest station to each venue.
#### <a name="venue"></a>venue
Each entry in this table contains mlb stadium info.

## License
Copyright 2019 William Stevenson

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit
persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.