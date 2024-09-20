# Match eduGAIN to ROR

Matches eduGAIN data to ROR IDs.

## Features

- Matches eduGAIN entities with ROR organizations based on name and URL
- Uses fuzzy matching for name comparison
- Performs parallel processing for improved performance
- Implements rate limiting for API requests
- Supports both name-based and URL-based searching

## Requirements

`pip install -r requirements.txt`)

## Usage

```
python match_edugain_ror.py -i INPUT_FILE [-o OUTPUT_FILE] [-v]
```

Arguments:
- `-i`, `--input`: Required. Path to the input CSV file containing eduGAIN data.
- `-o`, `--output`: Optional. Path for the output CSV file. Default is `{input_filename}_reconciled.csv`.
- `-v`, `--verbose`: Optional. Enable verbose logging.

## Input File Format

The input CSV file should contain the following columns:
- id
- entityid
- roles
- regauth
- e_displayname
- entity_cat
- roledesc
- r_displayname
- r_description
- role_service_name
- eccs_status
- clash
- validator_status
- coco_status
- coco_id
- sirtfi_status
- code
- scopes
- first_seen

## Output

The script will generate a CSV file with the original eduGAIN data and additional columns:
- matched_ror_id
- matched_name
- match_type
- match_ratio

## Rate Limiting

The script implements rate limiting to comply with the ROR API usage guidelines:
- Maximum 1000 calls per 5-minute period
- Maximum 5 parallel requests

## Notes

The script uses multiprocessing to improve performance and implements rate limiting to comply with the ROR API usage guidelines:
- Maximum 1000 calls per 5-minute period
- Maximum 5 parallel requests. 

Adjust `MAX_PARALLEL_REQUESTS` if needed.