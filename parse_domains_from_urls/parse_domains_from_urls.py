import re
import csv
import json
import argparse
from furl import furl


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Extract website domains from ROR records")
    parser.add_argument("-i", "--input_file", required=True,
                        help="Path to the input CSV file")
    parser.add_argument("-d", "--data_dump", required=True,
                        help="Path to the input JSON file")
    parser.add_argument("-o", "--output_file",
                        default="parsed_domains.csv", help="Path to the output CSV file")
    return parser.parse_args()


def read_csv(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f_in:
            reader = csv.DictReader(f_in)
            return list(reader)
    except IOError as e:
        print(f"Error reading CSV file: {e}")
        return []


def read_json(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as jsonfile:
            return json.load(jsonfile)
    except IOError as e:
        print(f"Error reading JSON file: {e}")
        return []


def extract_website(record):
    for link in record.get("links", []):
        if link.get("type") == "website":
            return link.get("value")
    return None


def reduce_to_domain(url):
    try:
        domain = furl(url).host
        if domain:
            domain = re.sub(r'^w{3}\d?\.', '', domain)
            domain = re.sub(r'^(english\.|en\.|eng\.|e\.|about\.|international\.|web\.|eweb\.|old\.|about\.)', '', domain)
            return domain
        else:
            print(f"No domain found in URL: {url}")
            return None
    except ValueError:
        print(f"Invalid URL: {url}")
        return None


def process_data(csv_data, json_data):
    json_dict = {record["id"]: record for record in json_data}
    for row in csv_data:
        ror_id = row["ror_id"]
        record = json_dict.get(ror_id)
        if record:
            website = extract_website(record)
            if website:
                domain = reduce_to_domain(website)
                row["website"] = website
                row["extracted_domain"] = domain
            else:
                print(f"No website found for ROR ID: {ror_id}")
                row["website"] = ""
                row["extracted_domain"] = ""
        else:
            print(f"No matching record found for ROR ID: {ror_id}")
            row["website"] = ""
            row["extracted_domain"] = ""
    return csv_data


def write_csv(data, file_path):
    try:
        with open(file_path, 'w', encoding='utf-8', newline='') as f_out:
            fieldnames = data[0].keys()
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
    except IOError as e:
        print(f"Error writing CSV file: {e}")


def main():
    args = parse_arguments()
    csv_data = read_csv(args.input_file)
    json_data = read_json(args.data_dump)
    if not csv_data or not json_data:
        print("Error: Unable to process input files")
        return
    results = process_data(csv_data, json_data)
    write_csv(results, args.output_file)
    print(f"Processing complete. Results written to {args.output_file}")


if __name__ == "__main__":
    main()
