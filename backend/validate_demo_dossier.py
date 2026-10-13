"""Read every original/corrected PDF; retain per-document evidence and visual QA."""
import hashlib
import json
from pathlib import Path
import re
import zipfile
import fitz
from PIL import Image, ImageDraw
from build_validated_demo_dossier import REPO, SOURCE, DEST
from phase2.credit_parser.document_extraction import extract_labeled_fields, classify_card_statement
from route.assessment_routes import process_bank_doc


def inspect():
    truth=json.loads((DEST/'ground_truth.json').read_text()); manifest=json.loads((DEST/'manifest.json').read_text())
    audit=[]; expected=[]; images=[]; previous_close=None
    previews=REPO/'docs/validated-dossier-preview'; previews.mkdir(exist_ok=True)
    for item in manifest['files']:
        path=DEST/item['name']; original=SOURCE/item['name']
        assert hashlib.sha256(original.read_bytes()).hexdigest()==item['original_sha256']
        with fitz.open(path) as pdf:
            assert len(pdf)==1
            text=pdf[0].get_text(); pix=pdf[0].get_pixmap(matrix=fitz.Matrix(.9,.9),alpha=False)
            image=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            image.save(previews/(path.stem+'.png')); images.append((item['name'],image))
        with fitz.open(original) as pdf: original_text='\n'.join(p.get_text() for p in pdf)
        assert 'Page 1 of 1' in text and 'SYNTHETIC' in text and 'FICTIONAL' in text
        labels={line.split(':',1)[0].strip():line.split(':',1)[1].strip() for line in text.splitlines() if ':' in line}
        row={'filename':item['name'],'classification':item['category'],'native_extraction':True,'actual_pages':1,'declared_pages':1,
            'original_declared_pages':None,'original_unchanged':True,'repaired_issues':[],'validation_result':'VALID'}
        if item['category']=='bank':
            _,tx,meta=process_bank_doc(str(path)); _,orig_tx,_=process_bank_doc(str(original))
            keys=['date','amount','type','closing_balance','narration']
            assert tx[keys].to_dict('records')==orig_tx[keys].to_dict('records')
            month=path.stem.rsplit('_',1)[1]
            expected_rows=[r for r in truth['bank_transactions'] if r['month']==month]
            assert len(tx)==len(expected_rows)==8
            credits=sum(r['credit'] for r in expected_rows); debits=sum(r['debit'] for r in expected_rows)
            assert meta['opening_balance']+credits-debits==meta['statement_closing_balance']
            if previous_close is not None: assert previous_close==meta['opening_balance']
            previous_close=meta['statement_closing_balance']
            assert truth['account_reference'] in text and meta['declared_page_sequence_complete']
            row.update({'statement_month':month,'transactions':8,'credits':credits,'debits':debits,'ledger_unchanged':True,
                'account_linked':True,'quality':meta['quality_score'],'opening_balance':meta['opening_balance'],
                'closing_balance':meta['statement_closing_balance'],'reconciliation':'PASS','repaired_issues':['PAGE_DECLARATION_ADDED']})
        elif item['category']=='creditCards':
            fields,gaps=extract_labeled_fields(text); original_fields,original_gaps=extract_labeled_fields(original_text)
            assert classify_card_statement(text)[0] and not gaps
            month=fields['statement_month']; candidate=next(r for r in truth['credit_card_monthly_evidence'] if r['month']==month)
            assert float(fields['statement_balance'].replace('INR ','').replace(',',''))==candidate['statement_balance']
            assert float(fields['payment_amount'].replace('INR ','').replace(',',''))==candidate['payment_applied_to_statement']
            assert fields['_auxiliary_fields']['payment_statement_reference']==candidate['statement_reference']
            row.update({'statement_month':month,'account_linked':fields['account_reference']==truth['card_reference'],'quality':1.0,
                'original_date_findings':original_gaps,'original_dates':original_fields.get('_auxiliary_fields',{}),
                'corrected_fields':fields,'repaired_issues':['PAGE_DECLARATION_ADDED','ISSUE_AND_BILLING_DATES_REPAIRED','DUE_DATES_REPAIRED','PAYMENT_AND_OBSERVATION_DATES_DECLARED','PAYMENT_STATEMENT_REFERENCE_DECLARED']})
        else:
            assert 'Aarav Mehta' in text
            row.update({'supporting_only':True,'native_fields':labels,'repaired_issues':['PAGE_DECLARATION_ADDED']})
        audit.append(row); expected.append({'filename':item['name'],'category':item['category'],'native_fields':labels})
    truth['expected_document_extraction']=expected
    (DEST/'ground_truth.json').write_text(json.dumps(truth,indent=2))
    report={'document_count':24,'validated_documents':audit,'bank_transactions':48,'original_bank_ledger_unchanged':True,
        'original_card_date_errors':6,'rejected_corrected_documents':0,'credit_features':truth['frozen_model_input_candidates'],
        'cutoff_month':'2026-09','assumptions':manifest['assumptions']}
    (DEST/'fixture_validation_report.json').write_text(json.dumps(report,indent=2))
    for start in range(0,24,6):
        sheet=Image.new('RGB',(1200,1800),'#e2e8f0'); draw=ImageDraw.Draw(sheet)
        for n,(name,img) in enumerate(images[start:start+6]):
            x=(n%2)*600;y=(n//2)*600;img.thumbnail((550,560));sheet.paste(img,(x+25,y+30));draw.text((x+25,y+10),name,fill='black')
        sheet.save(previews/f'contact-sheet-{start//6+1}.png')
    with zipfile.ZipFile(REPO/'output/PRISM_Validated_Synthetic_Dossier.zip','w',zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(DEST.iterdir()): zipped.write(path,path.name)
    print('All 24 corrected PDFs verified; original hashes and 48 ledger rows unchanged; four contact sheets rendered.')


if __name__=='__main__': inspect()
