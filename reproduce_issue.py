import csv
import io

csv_content = """Timestamp,Action,Details
"2025-08-10 23:38:28","Update","Details","RestoreDataValue"
"""

reader = csv.DictReader(io.StringIO(csv_content))
for row in reader:
    print(f"Keys: {list(row.keys())}")
    print(f"Row: {row}")
    if 'RestoreData' in row:
        print("RestoreData found")
    else:
        print("RestoreData NOT found")
