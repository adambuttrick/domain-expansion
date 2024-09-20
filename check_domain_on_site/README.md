# Check Domain on Site

Checks for domains in site and contact page HTML using Selenium.

## Installation

1. Install the required dependencies:

```
pip install -r requirements.txt
```

2. Make sure you have Chrome and ChromeDriver installed. You'll need to provide the path to ChromeDriver when running the script.

## Input Files

1. CSV File:
   - Contains records with `ror_id` and `extracted_domain` columns.

## Usage

```
python check_domain_on_site.py -i INPUT_CSV [-o OUTPUT_FILE] [-c CHROMEDRIVER_PATH]
```

Arguments:
- `-i`, `--input_file`: Required. Path to the input CSV file containing ROR IDs and domains.
- `-o`, `--output_file`: Optional. Path for the output CSV file. Default is `domains_on_sites.csv`.
- `-c`, `--chromedriver`: Optional. Path to the ChromeDriver executable. Default is `/opt/homebrew/bin/chromedriver`.

## Process

For each record in the input CSV:
1. Attempts to access the website using the provided domain.
2. Checks the main page HTML for the presence of an email with the given domain.
3. If not found on the main page, identifies potential contact pages.
4. Checks identified contact pages for the email domain.
5. Records whether the email domain was found on any page.

## Output

Generates a CSV file with the following columns:
- All columns from the input CSV
- `email_found`: Boolean indicating whether the email domain was found on the website
