# Iris
**Author**: Keane Flynn\
**Date**: 2025-12-12\
**Contact**: keaneflynn1@gmail.com

## Overview
Iris is an application to collect, broker, and append campbell datalogger data 
to a PostgreSQL database. This is carried out by making
an API query to the datalogger's internal backend for its most-recent, 
non-appended data. The program injests a text file in json format and uses
the relevant information to concatenate with datalogger data to create
comprehensive data table records for each device. This program should work 
universally with all Campbell data logger devices but this cannot be promised 
for non-CR6 or CR1000Xe datalogger models.

## Prerequisites
We will start by setting up the database tables for the climate, stream gauge,
lake level, and lake profiler. To do so, we will execute the construct.sql file
included in this repository. After cloning the repository and migrating to its
home directory, issue the following command:
```
psql -f construct.sql -U postgres
```
You will then be prompted to enter the login credentials for the database. This
will construct all the necessary tables, add the unique constraints to avoid
duplicate entries, and add correct indexing to speed up API requests based on 
website design.

## Hardware
The server side of this application can run on literally anything, I could 
probably run this on a microwave; it's that simple of code.

While only tested on Campbell CR1000XEs and CR6s, this application should be 
able to retrieve data from any modern Cambpbell datalogger with an operating
system that is from 2022 - present. The only change you might need to make
is to enable ICMP to allow for watchdog monitoring and to obtain the http login
password and data table name through Device Configuration Utility. These values
will be used in the next section of this document. 

## Input & Output
To see necessary inputs, run `python iris.py -h`

### Inputs
For this program to gather the proper login credentials and ancillary information
to correctly append data to Postgres, a client file in json format must be 
injested by the program. An abbreviated version of this file can be seen below.
The input parameters are as follows:

*ip_address*: the key value is the datalogger IP address\
*site*: string value for arbitraty site name\
*latitude*: latitude value for location of sensor\
*longitude*: longitude value for location of sensor\
*table_name*: name of data table on Campbell datalogger to retrieve\
*username*: http username for Campbell datalogger\
*password*: http password for Campbell datalogger\
*last_fetch*: only needs to be manually set the first time, 
after that it will auto-update every time the program runs\
*db_table*: name of postgres table for Campbell data to be appended to

The text file should follow the format below, add additional clients as needed:
```
{
    "10.10.10.1": {
        "site": "site1",
        "latitude": 45.11111,
        "longitude": -110.22222,
        "table_name": "datalogger_table1",
        "username": "admin",
        "password": "1111-AAAA-22BB",
        "last_fetch": "2025-01-01T00:00:00",
        "db_table": "climate"
    },
    "10.10.10.2": {
        "site": "site2",
        "latitude": 45.33333,
        "longitude": -110.44444,
        "table_name": "datalogger_table2",
        "username": "admin",
        "password": "3333-CCCC-44DD",
        "last_fetch": "2025-01-01T00:00:00",
        "db_table": "stream_gauge"
    }
}

```

You will also need to create a .env file for your internal postgres database
credentials:
```
DBNAME=
USERNAME=
PASSWORD=
HOST=
PORT=
```

### Outputs
Outputs will be appended records to the respective postgres database tables. 
While each table is unique (see construct.sql for table schema), each record
will consist of the same first values such as UUID, site, ip_address, latitude,
longitude, timestamp, and record. All values after will vary according to the 
sensors hooked up to the datalogger.

## How To Use
Issue the following command in your terminal to clone the repository:
```
git clone https://github.com/keaneflynn/Iris.git
```
You will then need to change directories into the one you just cloned with 
`cd Iris/`\
Create a directory to store error messages for logging purposes `mkdir errorLogs`
Create a python virtual environment to install the correct dependencies
```
python -m venv ./
```
Then activate the virtual environment:
```
source bin/activate
```
You should probably update pip just in case:
```
python -m pip install --upgrade pip
```
Install the necessary dependencies for this repository:
```
pip install -r requirements.txt
```
You can then deactivate the virtual environment with `deactivate`

This program is designed to be run from crontab but can be manually run using
```
source bin/activate
python iris.py <PATH/TO/CLIENTS_FILE.TXT>
```

### Running as Cronjob
This program is primarily designed to be run on a server as a cronjob.
To SLPT staff, in short, this means that given the proper instruction, it will 
run continuously on start up and restart if the program crashes for some reason. 
To make this work, you will need to modify the crontab file using the following 
command:
```
crontab -e
```
You will then need to insert a new line at the end of this file with the info
from the cron/sampleCron.txt file:
```
0 */1 * * * /path/to/venv/bin/python3 /path/to/venv/iris.py /path/to/venv/src/clients.txt 
> /path/to/venv/errorLogs/output.log 2>&1
```
And just like that, the program will be set to run at the top of every hour.

## Troubleshooting
Please see error logs as referenced above to troubleshoot data transmission issues. 
Most of the issues likely to arise with this software will derive from hardware 
issues from the datalogger-based systems (i.e., disconnected solar, rodents 
messed with wires, etc.). Please refer to the network_connection database table 
to troubleshoot connectivity issues prior to making software adjustments.


