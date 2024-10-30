# Check Domain on Site

Checks for email domains in website and contact page HTML using Selenium.

## Installation

1. Install required dependencies:
```
pip install -r requirements.txt
```

2. Ensure Chrome and [ChromeDriver](https://developer.chrome.com/docs/chromedriver/downloads) are installed.

## Input Files

CSV file must contain these columns:
- `ror_id` (configurable ID field)
- `website` (URL field)
- `domains` (domain field to check)

## Usage

```
python check_domain_on_site.py -i INPUT_CSV [-o OUTPUT_FILE] [-d ID_FIELD] [-w WEBSITE_FIELD] [-f DOMAIN_FIELD] [-s SEPARATOR] [-t TIMEOUT] [-r MAX_REDIRECTS] [-v VERIFY_SSL]
```

Arguments:
- `-i`, `--input`: Required. Path to input CSV file
- `-o`, `--output`: Output CSV path. Default: `domains_on_sites.csv`
- `-d`, `--id`: ID field name. Default: `ror_id`
- `-w`, `--website`: Website field name. Default: `website`
- `-f`, `--field`: Domains field name. Default: `domains`
- `-s`, `--sep`: Domain separator for multiple domains. Default: None
- `-t`, `--timeout`: Request timeout in seconds. Default: 10
- `-r`, `--redirects`: Maximum redirects. Default: 5
- `-v`, `--verify`: Verify SSL certificates. Default: True

## Process

For each record:
1. Resolves website URL through multiple variations (https/http, www/non-www)
2. Checks main page HTML for email domains
3. If not found, identifies and checks contact pages
4. Records findings in output CSV

## Output

Generates CSV with original columns plus:
- `resolved_domain`: Domain that was checked
- `resolved_url`: Final resolved URL
- `resolution_method`: URL variation that succeeded
- `was_redirected`: Whether URL redirected
- `status_code`: HTTP status code
- `email_found`: Whether email domain was found
- `contact_page_checked`: Whether contact pages were checked