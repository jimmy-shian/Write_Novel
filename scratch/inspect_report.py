# -*- coding: utf-8 -*-
import sys
import os

sys.path.append(os.path.abspath("."))
import db

def main():
    novel_id = '8e86fdc7-0c26-468d-9781-3f75a1e9fec4'
    report = db.generate_validation_report(novel_id)
    print("Report generated successfully.")
    with open("scratch/validation_report_output.txt", "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == '__main__':
    main()
