"""Coordinate-based native tables. Unsupported/reflowed layouts fail for review."""
import re
from pathlib import Path
import fitz
import pandas as pd

DATE = re.compile(r"^'?\d{1,2}[-/](?:\d{1,2}|[A-Za-z]{3,9})[-/]\d{2,4}$|^\d{4}-\d{2}-\d{2}$")
MONEY = re.compile(r'^(?:\d{1,3}(?:,\d{2,3})*|\d+)\.\d{2}(?:CR|DR)?$', re.I)
HEADERS = {'debit':{'debit','withdrawal','withdrawals'}, 'credit':{'credit','deposit','deposits'}, 'balance':{'balance'}}

def extract_native_table(path, password=None):
    if Path(path).suffix.lower() != '.pdf': return None
    rows, rejected, columns = [], [], None
    with fitz.open(path) as document:
        if document.needs_pass and not document.authenticate(password or ''):
            raise ValueError('DOCUMENT_COULD_NOT_BE_READ: encrypted PDF requires a password')
        for page_no, page in enumerate(document, 1):
            words = page.get_text('words', sort=True)
            header = None
            for candidate in words:
                if candidate[4].lower() not in HEADERS['debit']: continue
                # Header baselines can differ slightly (e.g. a lower-case
                # Balance glyph descender) while still belonging to one row.
                aligned = [w for w in words if abs(w[1]-candidate[1])<8]
                mapping = {key:next((w[0] for w in aligned if w[4].lower() in aliases),None) for key,aliases in HEADERS.items()}
                if all(value is not None for value in mapping.values()):
                    columns, header = mapping, candidate[1]
                    break
            if columns is None: continue
            # Bank PDFs often right-align amounts while headers are left-aligned.
            # Treat each amount column as the interval between neighboring headers,
            # rather than requiring the number's left edge to sit on the header x.
            ordered_columns = sorted(columns.items(), key=lambda item: item[1])
            column_bounds = {}
            for index, (key, x) in enumerate(ordered_columns):
                left = x - 40 if index == 0 else (ordered_columns[index-1][1] + x) / 2
                right = (x + ordered_columns[index+1][1]) / 2 if index+1 < len(ordered_columns) else page.rect.width
                column_bounds[key] = (left, right)
            dates = [w for w in words if DATE.fullmatch(w[4]) and not w[4].startswith('(')
                     and (header is None or w[1]>header+4) and w[0]<min(columns.values())-40]
            # A date must occupy the date column, not a statement-period date in
            # a summary block on a continuation page. Keep the dominant aligned
            # date column; an ambiguous tie still fails closed.
            if dates and max(w[0] for w in dates)-min(w[0] for w in dates)>20:
                clusters=[]
                for word in sorted(dates,key=lambda item:item[0]):
                    cluster=next((group for group in clusters if word[0]-group[0][0]<=20),None)
                    if cluster is None:
                        clusters.append([word])
                    else:
                        cluster.append(word)
                clusters.sort(key=len,reverse=True)
                if len(clusters[0])<2 or (len(clusters)>1 and len(clusters[0])==len(clusters[1])):
                    rejected.append({'source_page':page_no,'reason':'REFLOWED_DATE_COLUMN'});continue
                dates=clusters[0]
            for index, date in enumerate(dates):
                # Transaction amounts share the date's baseline. A broad band
                # up to the next date can accidentally absorb statement-summary
                # balances after the final transaction on a page.
                band=[w for w in words if date[1]-3<=w[1]<=date[1]+8]
                values={}
                for key,(left,right) in column_bounds.items():
                    candidates=[w for w in band if MONEY.fullmatch(w[4]) and left<=w[0]<right]
                    # Some bank exports print 0.00 in the unused debit/credit
                    # cell instead of leaving it blank. Treat that as an empty
                    # side of a transfer; a zero balance remains a valid value.
                    if key in {'debit','credit'}:
                        candidates=[w for w in candidates if float(re.sub(r'CR|DR','',w[4],flags=re.I).replace(',','')) != 0]
                    if len(candidates)>1: values[key]=None
                    elif candidates:
                        token=candidates[0][4];value=float(re.sub(r'CR|DR','',token,flags=re.I).replace(',',''))
                        values[key]=-value if key=='balance' and token.upper().endswith('DR') else value
                    else: values[key]=None
                debit,credit,balance=values.get('debit'),values.get('credit'),values.get('balance')
                if balance is None or (debit is None)==(credit is None):
                    rejected.append({'source_page':page_no,'source_line':index+1,'reason':'AMBIGUOUS_AMOUNT_COLUMN'});continue
                description=' '.join(w[4] for w in band if date[2]+3<w[0]<min(columns.values())-8)
                date_text=date[4].lstrip("'")
                parsed=pd.to_datetime(date_text,format='%Y-%m-%d' if re.match(r'^\d{4}-',date_text) else 'mixed',dayfirst=True,errors='coerce')
                if pd.isna(parsed):
                    rejected.append({'source_page':page_no,'source_line':index+1,'reason':'INVALID_DATE'});continue
                rows.append({'date':parsed,'narration':description,'debit':debit,'credit':credit,
                    'amount':credit if credit is not None else debit,'type':'CR' if credit is not None else 'DR',
                    'closing_balance':balance,'source_page':page_no,'source_line':index+1,'extraction_confidence':1.0})
        if not rows and not rejected:return None
        return pd.DataFrame(rows), {'adapter':'generic-coordinate-v1','rejected_rows':rejected,
            'quality_score':len(rows)/(len(rows)+len(rejected)) if rows or rejected else 0,
            'extraction_confidence':len(rows)/(len(rows)+len(rejected)) if rows or rejected else 0}
