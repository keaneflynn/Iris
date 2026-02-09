import requests
import json
import csv
import re
import os
import psycopg
from dotenv import load_dotenv
from datetime import datetime
from argparse import ArgumentParser
load_dotenv(override=True)


def fetchDataloggerData(client_file):
    # Get datalogger data from each client identified in the client file
    with open(client_file, 'r') as file:
        client_info = json.load(file)
    end_datetime = datetime.now().isoformat(timespec='seconds')
    raw_data = {}
    for key, values in client_info.items():
        # HTTP fetch url to Campbell datalogger API layer
        url = (
            f"http://{key}/csapi/?"           # IP address of datalogger
            f"command=DataQuery"
            f"&mode=date-range"
            f"&format=toa5"
            f"&uri=dl:{values['table_name']}" # Desired table name
            f"&p1={values['last_fetch']}"     # Beginning period since last fetch
            f"&p2={end_datetime}"             # Fetch to currrent datetime
        )
        try:
            # Standard response from modern datalogger
            response = requests.get(
                url, 
                auth=(values['username'], values['password']), 
                timeout=10
            )    
            if len(response.text.splitlines()) == 4:
            # This occurs when lake profiler tries the first API
            # call and returns the headers of the call and no data.
            # This invokes the following query to grab ALL of the
            # data off of the CR6 datalogger. For this OS version
            # this is the only dependable way of carrying this out
                url = (
                    f"http://{key}/csapi/?"
                    f"command=DataQuery"
                    f"&mode=since-record"
                    f"&format=toa5"
                    f"&uri=dl:{values['table_name']}"
                    f"&p1=0"
                )
                response = requests.get(
                    url, 
                    auth=(values['username'], values['password']), 
                    timeout=20 # Longer timeout for all data
                )
            entry = {
                key: {
                    "fetch_status": response.status_code,
                    "payload": response.text
                }
            }    
            raw_data.update(entry) 
        except OSError: 
            # Not really a 504 but a timeout occurs because 
            # there isn't a connection to the specified host
            entry = {
                key: {
                    "fetch_status": "504",
                    "payload": ""
                }
            }
            raw_data.update(entry)
        except Exception:
            # Using a 404 as a catch all for whatever I can't predict
            entry = {
                key: {
                    "fetch_status": "404",
                    "payload": ""
                }
            }
            raw_data.update(entry)
    return raw_data

def cast_type(value):
    # Converting raw str values from list 
    # to correct type for postgres append
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value

def formatData(raw_data, client_file):
    with open(client_file, 'r') as file:
        client_info = json.load(file)
    formatted_data = {}
    counter = 0
    for outer_key, outer_values in client_info.items(): # Clients file
        ref_key = outer_values['db_table']
        entry_no = 'entry_' + str(counter)
        counter += 1
        for inner_key, inner_values in raw_data.items(): # Raw data
            if inner_key == outer_key:
                try:
                    # Parse and format field names
                    static_fields = ('site', 'ip_address', 'latitude', 'longitude')
                    field_names = inner_values['payload'].split("\r\n")[1]
                    field_names_tuple = tuple(next(csv.reader([field_names])))
                    fields_raw = static_fields + field_names_tuple
                    # Lowercase all values
                    fields = [value.lower() for value in fields_raw] 
                    # Remove any non-underscore special characters
                    # Shouout YSI for writing shit datalogger code
                    fields = tuple(
                        re.sub(r'[^a-zA-Z0-9_]', '', value) 
                        for value in fields
                    )

                    # Parse and format data payload
                    static_values = (
                        outer_values['site'], outer_key, 
                        outer_values['latitude'], 
                        outer_values['longitude']
                    )
                    # First four lines are headers for raw data
                    # Last value from payload is always a blank
                    field_values = inner_values['payload'].split("\r\n")[4:][:-1]
                    values_raw = [
                        tuple(cast_type(i) for i in next(csv.reader([row])))
                        for row in field_values
                    ]
                    values_formatted = [static_values + row for row in values_raw]
                except IndexError:
                    # Exception for when network client is disconnected
                    continue
                entry = {
                    entry_no: {
                        "db_table": outer_values['db_table'],
                        "col_names": fields,
                        "data": values_formatted
                    }
                }
                formatted_data.update(entry)
            else:
                continue
    return formatted_data

def extractDatetime(values: tuple):
    # Extract the first datetime value from  
    # most recent payload from datalogger
    for value in values[-1]:
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            return value
        except:
            continue

def extractAddress(values: tuple):
    # Extract the first IP address value from  
    # most recent data payload from datalogger
    for value in values[-1]:
        if value.count('.') == 3:
            return value
        else:
            continue

def postgresAppend(formatted_data):
    # Append data to respective Postgres tables 
    # and cache successful append times to list
    cache_list = {}
    for key, value in formatted_data.items():
        table_name = value['db_table']
        col_names = value['col_names']
        values = value['data']
        # Grab IP address and timestamp for 
        # most recent record for each client
        datetime = extractDatetime(values)
        ip_address = extractAddress(values)
        entry = {
            ip_address: datetime
        }
        # Proper formatting for Postgres append
        col_identifiers = [psycopg.sql.Identifier(col) for col in col_names]
        placeholders = [psycopg.sql.Placeholder() for _ in col_names]
        vals = psycopg.sql.SQL(", ").join(placeholders)
        # Build append-safe full SQL query
        query = psycopg.sql.SQL("""
            INSERT INTO {table} (uuid, {cols})
            VALUES (uuid_generate_v4(), {vals})
            ON CONFLICT (timestamp, site, record) DO NOTHING
        """).format(
            table=psycopg.sql.Identifier(table_name),
            cols=psycopg.sql.SQL(", ").join(col_identifiers),
            vals=psycopg.sql.SQL(", ").join(placeholders)
        )
        try:
            # Connect and append data from query statement
            with psycopg.connect(
                dbname = os.getenv('DBNAME'),
                user = os.getenv('USERNAME'),
                password = os.getenv('PASSWORD'),
                host = os.getenv('HOST'),
                port = os.getenv('PORT')
            ) as conn:
                with conn.cursor() as cur:
                    cur.executemany(query, values)
                conn.commit()
            cache_list.update(entry)
        except psycopg.OperationalError as e:
            print("""OperationError, cannot connect to postgres DB
                  Please check connection credentials.
                  Error: {}""".format(e))
    return cache_list

def cacheFetchTimes(cache_list, client_file):
    with open(client_file, 'r') as read_file:
        client_info = json.load(read_file)
    for outer_key, outer_value in client_info.items():
        for address in cache_list:
            if outer_key == address:
                dt_raw = datetime.strptime(
                    cache_list[address], 
                    '%Y-%m-%d %H:%M:%S'
                )
                dt = dt_raw.isoformat()
                outer_value['last_fetch'] = dt
    with open(client_file, 'w') as write_file:
        json.dump(client_info, write_file, indent=4)
        

def main():
    parser = ArgumentParser(
        description='Concentrator, broker, and appender of ' \
                    'Campbell datalogger data to Postgres'
    )
    parser.add_argument('client_file', type=str, help='path/to/client_file')
    args = parser.parse_args()

    raw_data = fetchDataloggerData(args.client_file)
    formatted_response = formatData(raw_data, args.client_file)
    cache_list = postgresAppend(formatted_response)
    cacheFetchTimes(cache_list, args.client_file)


if __name__ == '__main__':
    main()
