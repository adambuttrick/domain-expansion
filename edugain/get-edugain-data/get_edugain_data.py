import csv
import json
import logging
import argparse
import requests
from io import StringIO


logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='Convert JSON data from edugain API to CSV format')
    parser.add_argument(
        '-o', '--output', default="edugain_data.csv", help='Output CSV file path')
    return parser.parse_args()


def fetch_json_data():
    url = "https://technical.edugain.org/api.php"
    params = {
        'action': 'list_entities',
        'type': 'idp',
        'format': 'json'
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Error fetching data from {url}: {e}")
        raise


def parse_json_data(json_data):
    try:
        if isinstance(json_data, list) and all(isinstance(item, list) for item in json_data):
            flattened_data = [
                item for sublist in json_data for item in sublist]
            return flattened_data
        else:
            raise ValueError("Unexpected JSON structure")
    except Exception as e:
        logging.error(f"Error parsing JSON data: {e}")
        raise


def convert_to_csv(data):
    if not data:
        logging.warning("No data to convert to CSV")
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)
    return output.getvalue()


def save_csv(csv_data, output_file):
    try:
        with open(output_file, 'w') as f:
            f.write(csv_data)
        logging.info(f"CSV data saved to {output_file}")
    except IOError as e:
        logging.error(f"Error saving CSV data to {output_file}: {e}")
        raise


def main():
    args = parse_arguments()
    try:
        json_data = fetch_json_data()
        parsed_data = parse_json_data(json_data)
        csv_data = convert_to_csv(parsed_data)
        save_csv(csv_data, args.output)
        logging.info("Conversion completed successfully")
    except Exception as e:
        logging.error(f"An error occurred during the conversion process: {e}")
        exit(1)


if __name__ == "__main__":
    main()
