import json
import re
import os

output_file = "app/security_report_summarize.json"

if os.path.exists(output_file):
    with open(output_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    print(f"Loaded {len(results)} items.")
    
    for item in results:
        raw = item.get("summaries", {}).get("raw_output")
        if raw:
            print(f"--- File: {item['filename']} ---")
            print(f"Raw Type: {type(raw)}")
            print(f"Raw Length: {len(raw)}")
            print(f"Raw Start: {repr(raw[:50])}")
            print(f"Raw End: {repr(raw[-50:])}")
            
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                print("Regex Match: Found")
                try:
                    json.loads(match.group(0))
                    print("JSON Parse: Success")
                except Exception as e:
                    print(f"JSON Parse Error: {e}")
            else:
                print("Regex Match: NOT Found")
else:
    print("File not found.")
