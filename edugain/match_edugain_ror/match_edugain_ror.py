import os
import re
import sys
import csv
import json
import glob
import time
import string
import logging
import argparse
import itertools
import urllib.parse
import multiprocessing
import requests
from unidecode import unidecode
from rapidfuzz import fuzz
from functools import partial

MAX_PARALLEL_REQUESTS = 5
RATE_LIMIT_CALLS = 1000
RATE_LIMIT_PERIOD = 300


def setup_logging(verbose):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level, format='%(asctime)s - %(levelname)s - %(message)s')


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Match eduGAIN data with ROR identifiers.")
    parser.add_argument('-i', '--input', required=True,
                        help="Input CSV file path")
    parser.add_argument(
        '-o', '--output', default="matched_ror_edugain.csv", help="Output CSV file path")
    parser.add_argument('-v', '--verbose', action='store_true',
                        help="Enable verbose logging")
    return parser.parse_args()


def init_shared_rate_limiter():
    manager = multiprocessing.Manager()
    shared_calls = manager.list()
    shared_lock = manager.Lock()
    return GlobalRateLimiter(RATE_LIMIT_CALLS, RATE_LIMIT_PERIOD, shared_calls, shared_lock)


class GlobalRateLimiter:
    def __init__(self, max_calls, period, shared_calls, shared_lock):
        self.max_calls = max_calls
        self.period = period
        self.calls = shared_calls
        self.lock = shared_lock

    def wait(self):
        with self.lock:
            now = time.time()
            self.calls[:] = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                sleep_time = self.period - (now - self.calls[0])
                time.sleep(max(sleep_time, 0))
            self.calls.append(now)


def rate_limited_request(url, params=None, rate_limiter=None):
    if rate_limiter:
        rate_limiter.wait()
    return requests.get(url, params=params)


def normalize(text):
    text = unidecode(text.lower())
    return re.sub(r'[-\(\)]|\s\(.*\)|[^\w\s]', '', text)


class MatchInfo:
    def __init__(self):
        self.name_matches = set()
        self.url_match = False
        self.highest_ratio = 0

    def add_name_match(self, match_type, ratio):
        self.name_matches.add(match_type)
        self.highest_ratio = max(self.highest_ratio, ratio)

    def set_url_match(self):
        self.url_match = True

    def get_match_string(self):
        match_types = list(self.name_matches)
        if self.url_match:
            match_types.append('url')
        return '; '.join(sorted(match_types))


def ror_name_search(org_name, rate_limiter):
    normalized_org_name = normalize(org_name)
    query_params = {'query': f'"{normalized_org_name}"'}
    affiliation_params = {'affiliation': f'"{normalized_org_name}"'}
    all_params = [query_params, affiliation_params]
    ror_matches = {}
    for params in all_params:
        try:
            response = rate_limited_request(
                'https://api.ror.org/v2/organizations', params=params, rate_limiter=rate_limiter)
            response.raise_for_status()
            api_response = response.json()
        except requests.RequestException as e:
            logging.error(f"API request failed: {e}")
            continue
        if api_response['number_of_results'] == 0:
            continue
        for result in api_response.get('items', []):
            try:
                org_data = result.get('organization', result)

                ror_id = org_data.get('id')
                if not ror_id:
                    logging.warning(f"No 'id' found in result: {org_data}")
                    continue
                ror_name = next((name['value'] for name in org_data.get('names', [])
                                 if 'ror_display' in name.get('types', [])), None)
                if not ror_name:
                    logging.warning(f"No display name found for ROR ID: {ror_id}")
                    continue

                match_info = MatchInfo()

                aliases = set(name['value'] for name in org_data.get('names', [])
                              if 'ror_display' not in name.get('types', []))
                labels = set(name['value'] for name in org_data.get('names', [])
                             if 'label' in name.get('types', []))

                name_mr = fuzz.ratio(normalized_org_name, normalize(ror_name))
                if name_mr >= 90:
                    match_info.add_name_match('name', name_mr)

                for alias in aliases:
                    alias_mr = fuzz.ratio(
                        normalized_org_name, normalize(alias))
                    if alias_mr >= 90:
                        match_info.add_name_match('alias', alias_mr)

                for label in labels:
                    label_mr = fuzz.ratio(
                        normalized_org_name, normalize(label))
                    if label_mr >= 90:
                        match_info.add_name_match('label', label_mr)

                if match_info.name_matches:
                    ror_matches[ror_id] = (ror_name, match_info)

            except Exception as e:
                logging.error(f"Error processing result: {e}")
                logging.error(f"Problematic result: {result}")

    return ror_matches


def ror_url_search(url, rate_limiter):
    params = {'query.advanced': f'links.value:"*{url}*"'}
    try:
        response = rate_limited_request(
            'https://api.ror.org/v2/organizations', params=params, rate_limiter=rate_limiter)
        response.raise_for_status()
        api_response = response.json()
    except requests.RequestException as e:
        logging.error(f"API request failed: {e}")
        return {}

    ror_matches = {}
    if 'items' in api_response:
        for item in api_response['items']:
            ror_id = item.get('id')
            ror_name = next((name['value'] for name in item.get('names', [])
                             if 'ror_display' in name.get('types', [])), None)
            if ror_id and ror_name:
                match_info = MatchInfo()
                match_info.set_url_match()
                match_info.highest_ratio = 100  # Assuming 100% match for URL
                ror_matches[ror_id] = (ror_name, match_info)
            else:
                logging.warning(f"Incomplete organization data: {item}")
    else:
        logging.warning(f"Unexpected API response structure: {api_response}")

    return ror_matches


def parse_names(names):
    return [re.sub(r'\=\=[a-z]{2}', '', name) for name in names.split(';') if len(name) > 2]


def parse_urls(urls):
    return urls.split('==') if '==' in urls else [urls]


def perform_name_matching(names, rate_limiter):
    all_matches = {}
    for name in names:
        logging.info(f"Searching for {name}...")
        ror_matches = ror_name_search(name, rate_limiter)
        for ror_id, (ror_name, match_info) in ror_matches.items():
            if ror_id in all_matches:
                all_matches[ror_id][1].name_matches.update(
                    match_info.name_matches)
                all_matches[ror_id][1].highest_ratio = max(
                    all_matches[ror_id][1].highest_ratio, match_info.highest_ratio)
            else:
                all_matches[ror_id] = (ror_name, match_info)
    return all_matches


def get_ror_urls(ror_id, rate_limiter):
    try:
        response = rate_limited_request(
            f'https://api.ror.org/v2/organizations/{ror_id}', rate_limiter=rate_limiter)
        response.raise_for_status()
        org_data = response.json()
        website_urls = [link['value'] for link in org_data.get('links', [])
                        if link.get('type') == 'website']
        if not website_urls:
            logging.warning(f"No website URL found for ROR ID: {ror_id}")

        return website_urls
    except requests.RequestException as e:
        logging.error(f"Failed to fetch ROR URLs for {ror_id}: {e}")
        return []


def check_urls_against_matches(name_matches, urls, rate_limiter):
    verified_matches = {}
    for ror_id, (ror_name, match_info) in name_matches.items():
        ror_urls = get_ror_urls(ror_id, rate_limiter)
        if any(url in ror_url or ror_url in url for url in urls for ror_url in ror_urls):
            match_info.set_url_match()
        verified_matches[ror_id] = (ror_name, match_info)
    return verified_matches


def perform_url_matching(urls, rate_limiter):
    all_matches = {}
    for url in urls:
        logging.info(f"Searching for URL {url}...")
        ror_matches = ror_url_search(url, rate_limiter)
        all_matches.update(ror_matches)
    return all_matches


def process_row(row, file_header, ror_header, rate_limiter):
    names = parse_names(row['e_displayname'])
    urls = parse_urls(row['scopes'])
    name_matches = perform_name_matching(names, rate_limiter)
    if name_matches:
        final_matches = check_urls_against_matches(
            name_matches, urls, rate_limiter)
    else:
        final_matches = perform_url_matching(urls, rate_limiter)

    results = []
    if final_matches:
        for ror_id, (ror_name, match_info) in final_matches.items():
            match_type = match_info.get_match_string()
            match_ratio = match_info.highest_ratio
            results.append({**row, **dict(zip(ror_header, [ror_id, ror_name, match_type, match_ratio]))})
    else:
        results.append(row)

    return results


def search_json(input_file, output_file):
    file_header = ['id', 'entityid', 'roles', 'regauth', 'e_displayname', 'entity_cat',
                   'roledesc', 'r_displayname', 'r_description', 'role_service_name', 'eccs_status', 'clash',
                   'validator_status', 'coco_status', 'coco_id', 'sirtfi_status', 'code', 'scopes', 'first_seen']
    ror_header = ["matched_ror_id", "matched_name",
                  "match_type", "match_ratio"]

    with open(input_file, 'r') as f_in, open(output_file, 'w', newline='') as f_out:
        reader = csv.DictReader(f_in)
        writer = csv.DictWriter(f_out, fieldnames=file_header + ror_header)
        writer.writeheader()
        shared_rate_limiter = init_shared_rate_limiter()
        pool = multiprocessing.Pool(MAX_PARALLEL_REQUESTS)
        chunk_size = 100
        rows = list(reader)
        total_rows = len(rows)
        for i in range(0, total_rows, chunk_size):
            chunk = rows[i:i+chunk_size]
            logging.info(f"Processing chunk {i//chunk_size + 1} of {(total_rows-1)//chunk_size + 1}")

            process_row_partial = partial(
                process_row, file_header=file_header, ror_header=ror_header, rate_limiter=shared_rate_limiter)
            results = pool.map(process_row_partial, chunk)

            for result_list in results:
                for result in result_list:
                    writer.writerow(result)
        pool.close()
        pool.join()


def main():
    args = parse_arguments()
    setup_logging(args.verbose)
    input_file = args.input
    output_file = args.output or f'{os.path.splitext(input_file)[0]}_reconciled.csv'
    logging.info(f"Processing input file: {input_file}")
    logging.info(f"Output will be written to: {output_file}")
    search_json(input_file, output_file)
    logging.info("Processing complete.")


if __name__ == '__main__':
    main()
