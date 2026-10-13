"""Explicit demo-only multipart receipt; no tokens, contents or customer names."""
import json
import logging
import os
import re


def record_demo_receipt(application_id, path, groups, cutoff=None):
    if os.getenv('PRISM_ENV') != 'demo' or os.getenv('PRISM_DEMO_FIXTURES') != 'true':
        return
    files = [{"field": field, "filename": file.filename if re.fullmatch(
        r'(?:Bank_Statement|Credit_Card|Salary_Slip|Utility_Bill)_2026-0[3-8]\.pdf', file.filename or '')
        else '[REDACTED NON-FIXTURE FILENAME]'} for field, selected in groups.items() for file in selected]
    logging.getLogger('uvicorn.error').info('demo_upload %s', json.dumps({
        'application_id': application_id, 'path': path, 'files': files,
        'prediction_cutoff_month': cutoff, 'authentication': 'authenticated borrower; token redacted'}))
