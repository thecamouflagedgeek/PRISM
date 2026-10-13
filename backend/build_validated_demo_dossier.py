"""Reproducible synthetic repairs. Originals and bank ledger remain untouched."""
import calendar
import hashlib
import json
from datetime import date
from pathlib import Path
import zipfile
import fitz
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.pagesizes import A4

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / 'backend/test_fixtures/aarav_original'
DEST = REPO / 'tests/fixtures/prism_demo_validated'


def build():
    DEST.mkdir(parents=True, exist_ok=True)
    truth = json.loads((SOURCE / 'ground_truth.json').read_text())
    originals, manifest = [], []
    styles = getSampleStyleSheet()
    styles['Normal'].fontSize = 9
    styles['Normal'].leading = 12
    for source in sorted(SOURCE.glob('*.pdf')):
        kind, month = source.stem.rsplit('_', 1)
        with fitz.open(source) as original:
            text = '\n'.join(p.get_text() for p in original)
            issue = ['DECLARED_PAGE_SEQUENCE_MISSING']
            audit = {'filename':source.name, 'category':kind, 'month':month, 'pages':len(original),
                'native_text':bool(text.strip()), 'original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                'account_reference':truth['card_reference'] if kind == 'Credit_Card' else truth['account_reference'] if kind == 'Bank_Statement' else None,
                'issues':issue}
            target = DEST / source.name
            if kind != 'Credit_Card':
                for n, page in enumerate(original):
                    identity_label = {'Bank_Statement':'Account Name', 'Salary_Slip':'Employee Name',
                                      'Utility_Bill':'Consumer Name'}[kind]
                    page.insert_text((40, 805), f'{identity_label}: {truth["borrower"]}', fontsize=8)
                    page.insert_text((40, 820), f'Page {n+1} of {len(original)} | VALIDATED SYNTHETIC FIXTURE - FICTIONAL', fontsize=8)
                original.save(target)
            else:
                row = next(r for r in truth['credit_card_monthly_evidence'] if r['month'] == month)
                year, m = map(int, month.split('-'))
                prior = date(year if m>1 else year-1, m-1 if m>1 else 12, 1)
                period_end = prior.replace(day=calendar.monthrange(prior.year,prior.month)[1])
                statement_date = date(year,m,1)
                due = date(year,m,20 if row['repayment_status_code']==0 else 15)
                paid = date(year,m,17) # Exact bank ledger payment date, not invented.
                observed = date(year,m,calendar.monthrange(year,m)[1])
                audit.update({'issues':issue+['DUE_DATE_BEFORE_STATEMENT_DATE','PAYMENT_PRECEDES_STATEMENT_ISSUE_DATE','REPAYMENT_OBSERVATION_DATE_UNDECLARED','STATEMENT_PAYMENT_REFERENCE_UNDECLARED'],
                    'original_statement_date':observed.isoformat(), 'original_due_date':row['payment_due_date'],
                    'ledger_payment_date':paid.isoformat()})
                row.update({'statement_date':statement_date.isoformat(), 'payment_due_date':due.isoformat(),
                    'payment_date':paid.isoformat(), 'repayment_observation_date':observed.isoformat(),
                    'statement_reference':f'TEST-CARD-4821-{month}', 'payment_statement_reference':f'TEST-CARD-4821-{month}',
                    'billing_period':[prior.isoformat(),period_end.isoformat()], 'repayment_status':'CURRENT' if row['repayment_status_code']==0 else 'DELINQUENT'})
                content = [Paragraph('SYNTHETIC TEST DOCUMENT - FICTIONAL - NEVER USE AS A GENUINE FINANCIAL RECORD',styles['Heading2']),
                    Paragraph('CREDIT CARD MONTHLY STATEMENT',styles['Heading1']),
                    Paragraph('Validated software-testing fixture. No financial institution issued this document.',styles['Normal']), Spacer(1,12)]
                fields = [('Customer',truth['borrower']),('Issuer','PRISM DEMO CARD SERVICES (fictional)'),('Card reference',truth['card_reference']),
                    ('Card number','XXXX-XXXX-XXXX-4821'),('Statement month',month),('Statement date',statement_date.strftime('%d/%m/%Y')),
                    ('Statement period',f'{prior:%d/%m/%Y} - {period_end:%d/%m/%Y}'),('Payment due date',due.strftime('%d/%m/%Y')),
                    ('Statement reference',row['statement_reference']),('Statement balance',f"INR {row['statement_balance']:,.2f}"),
                    ('Total amount due',f"INR {row['statement_balance']:,.2f}"),('Minimum amount due',f"INR {row['statement_balance']*.05:,.2f}"),
                    ('Payment applied to this statement',f"INR {row['payment_applied_to_statement']:,.2f}"),('Payment date',paid.strftime('%d/%m/%Y')),
                    ('Payment statement reference',row['payment_statement_reference']),('Payment settlement status','SETTLED'),
                    ('Repayment status',row['repayment_status']),('Explicit delinquency level',str(row['repayment_status_code'])),
                    ('Repayment observation date',observed.strftime('%d/%m/%Y')),('Currency','INR'),('Prediction cutoff month (exclusive)','2026-09')]
                for label,value in fields: content.append(Paragraph(f'{label}: {value}',styles['Normal']))
                content += [Spacer(1,14),Paragraph('Fictional purchases in the preceding billing period (dates corrected to precede issue):',styles['Normal'])]
                tx = [['Date','Transaction','Amount INR']] + [[f'{d:02}/{prior.month:02}/{prior.year}','Fictional '+label,f'{row["statement_balance"]*share:,.2f}'] for d,label,share in [(5,'retail purchases',.55),(13,'travel and dining',.25),(21,'other purchases and charges',.2)]]
                table=Table(tx,colWidths=[85,260,95]); table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
                content += [table,Spacer(1,12),Paragraph('Explicit severity values are constructed categorical test labels carried forward from the original fixture, not an issuer-certified days-past-due history. See the manifest for all synthetic date assumptions.',styles['Normal'])]
                def footer(canvas,doc): canvas.setFont('Helvetica',8); canvas.drawString(40,24,'Page 1 of 1 | SYNTHETIC / FICTIONAL | Validated demo fixture')
                SimpleDocTemplate(str(target),pagesize=A4,rightMargin=40,leftMargin=40,topMargin=38,bottomMargin=45).build(content,onFirstPage=footer)
            originals.append(audit)
        manifest.append({'category':{'Bank_Statement':'bank','Credit_Card':'creditCards','Salary_Slip':'salary','Utility_Bill':'utility'}[kind],
            'name':source.name, 'sha256':hashlib.sha256(target.read_bytes()).hexdigest(), 'original_sha256':audit['original_sha256']})
    assumptions = [
        'All 24 files are fictional synthetic repairs; originals are unchanged negative fixtures.',
        'All page declarations are added to the existing one-page synthetic layouts; no pages/transactions are inferred for genuine documents.',
        'The 48-row bank ledger, dates, debit/credit amounts, narration and opening/closing balances are unchanged.',
        'Cards issue on day 1 of their explicit statement month. Purchase dates move to the preceding calendar billing period; purchase and balance/payment amounts are unchanged.',
        'Card payment date is day 17 from the preserved bank ledger. Due dates are day 20 for explicit CURRENT labels and day 15 for explicit DELINQUENT labels; these are new fictional schedule assumptions.',
        'Severity codes 0,0,1,1,2,1 are the original constructed categorical labels, not inferred from payment dates or claimed issuer-certified DPD buckets. July level 2 is a supplied synthetic history assumption.',
        'Monthly repayment status is explicitly observed at month end. Every observation and settled payment precedes the exclusive historical cutoff 2026-09.',
        'Each payment amount is explicitly applied to its matching TEST-CARD-4821-YYYY-MM statement reference; the matching bank debit remains unchanged.',
        'Frozen features retain their exact existing definitions and units; no supporting salary/utility values enter the frozen model.'
    ]
    manifest_doc={'label':'VALIDATED SYNTHETIC / FICTIONAL DOSSIER - NOT CUSTOMER DATA','cutoff_month':'2026-09','assumptions':assumptions,'files':manifest}
    (DEST/'manifest.json').write_text(json.dumps(manifest_doc,indent=2))
    (DEST/'ground_truth.json').write_text(json.dumps(truth,indent=2))
    (DEST/'original_validation_report.json').write_text(json.dumps({'documents':originals,'bank_ledger_expected_rows':48,'credit_features':truth['frozen_model_input_candidates'],'assumptions':assumptions},indent=2))
    (DEST/'README.md').write_text('# VALIDATED SYNTHETIC / FICTIONAL DOSSIER\n\nUpload all 24 PDFs using the normal four category controls. Explicitly select historical exclusive card cutoff **2026-09**, confirm card consent and Run Assessment. Or use the development-only Load Validated Synthetic Dossier button.\n\nThese are constructed software-test records, never genuine financial evidence. See manifest.json for every date and repayment assumption. Bank ledger and all balance/payment amounts are preserved. Original defects are recorded in original_validation_report.json.\n')
    archive = REPO/'output/PRISM_Validated_Synthetic_Dossier.zip'; archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(DEST.iterdir()): zipped.write(path,path.name)
    print(f'Built {len(manifest)} corrected PDFs and {archive}')


if __name__=='__main__': build()
