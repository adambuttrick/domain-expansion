# Parse Domains from URLs

Extracts domains from website values in ROR records.


## Installation

`pip install -r requirements.txt`


## Input Files

1. CSV File:
   - Records to be parsed from data dump and have the domains extracted from the website values. Should contain a `ror_id` column.

2. Data Dump:
   - Schema v2 ROR data dump in JSON format


## Usage

```
python parse_domains_from_urls.py -i INPUT_CSV -d DATA_DUMP [-o OUTPUT_FILE]
```

Arguments:
- `-i`, `--input_file`: Required. Path to the input CSV file containing ROR IDs and domains.
- `-d`, `--data_dump`: Required. Path to the input JSON file containing full ROR records.
- `-o`, `--output_file`: Optional. Path for the output CSV file. Default is `parsed_domains.csv`.



## Output

Generates a CSV file with the following columns:
- ror_id: The ROR ID of the organization
- website: The full website URL extracted from the ROR record
- extracted_domain: The domain name extracted from the website URL

