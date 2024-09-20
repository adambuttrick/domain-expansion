## Get eduGAIN Data

Retrieves records from the eduGAIN API and converts it to CSV format.

## Setup
   ```
   pip install -r requirements.txt
   ```

## Usage
```
python get_edugain_data.py [-o OUTPUT_FILE]
```

Options:
- `-o`, `--output`: Specify the output CSV file path (default: "edugain_data.csv")

## Example
```
python get_edugain_data.py -o my_edugain_data.csv
```