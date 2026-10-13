import pytest
from pathlib import Path
from ingestion.bank_layout import extract_native_table
from ingestion.universal_pipeline import BankExtractor
import fitz


def make_statement(path, swapped=False, invalid=False):
 d=fitz.open();p=d.new_page()
 p.insert_text((40,40),'Bank statement INR')
 for x,text in [(40,'Date'),(140,'Narration'),(300,'Credit' if swapped else 'Debit'),(390,'Debit' if swapped else 'Credit'),(480,'Balance')]:p.insert_text((x,80),text)
 for y,date,direction,amount,balance in [(110,'01-Jan-2026','CR','1,00,000.00','1,01,000.00'),(150,'02-Jan-2026','DR','1,000.00','1,00,000.00')]:
  p.insert_text((40,y),date);p.insert_text((140,y),'Income' if direction=='CR' else 'Expense')
  x=(300 if swapped else 390) if direction=='CR' else (390 if swapped else 300)
  p.insert_text((x,y),'unreadable' if invalid and direction=='DR' else amount);p.insert_text((480,y),balance)
 d.save(path);d.close()

@pytest.mark.parametrize('swapped',[False,True])
def test_coordinates_preserve_column_roles(tmp_path,swapped):
 p=tmp_path/'statement.pdf';make_statement(p,swapped)
 rows,meta=extract_native_table(p)
 assert not meta['rejected_rows'];assert rows.type.tolist()==['CR','DR'];assert rows.amount.tolist()==[100000,1000]
 assert rows.closing_balance.tolist()==[101000,100000];assert rows.source_page.tolist()==[1,1]

def test_unreadable_amount_is_rejected(tmp_path):
 p=tmp_path/'bad.pdf';make_statement(p,invalid=True)
 rows,meta=extract_native_table(p)
 assert len(rows)==1 and meta['rejected_rows'][0]['reason']=='AMBIGUOUS_AMOUNT_COLUMN'

def test_right_aligned_amounts_are_assigned_by_column_interval(tmp_path):
 p=tmp_path/'right-aligned.pdf';d=fitz.open();page=d.new_page()
 for x,text in [(40,'Date'),(140,'Narration'),(300,'Debit'),(390,'Credit'),(480,'Balance')]:page.insert_text((x,80),text)
 for y,date,narration,debit,credit,balance in [
  (110,'01/05/2026','Salary credit','-', '82,000.00','192,700.00'),
  (150,'02/05/2026','House rent','20,893.60','-','171,806.40')]:
  page.insert_text((40,y),date);page.insert_text((140,y),narration)
  if debit!='-':page.insert_text((330,y),debit)
  if credit!='-':page.insert_text((420,y),credit)
  page.insert_text((520,y),balance)
 d.save(p);d.close()
 rows,meta=extract_native_table(p)
 assert not meta['rejected_rows']
 assert rows.type.tolist()==['CR','DR']
 assert rows.amount.tolist()==[82000,20893.6]
 assert rows.closing_balance.tolist()==[192700,171806.4]

def test_apostrophe_dates_zero_unused_amounts_and_lower_balance_header(tmp_path):
 p=tmp_path/'bank-export.pdf';d=fitz.open();page=d.new_page()
 for x,text,y in [(40,'Date',80),(140,'Narration',80),(300,'Debit',80),(390,'Credit',80),(480,'Balance',84)]:page.insert_text((x,y),text)
 for y,date,narration,debit,credit,balance in [
  (110,"'01-09-2026",'Income','0.00','5,000.00','15,000.00'),
  (150,"'02-09-2026",'Expense','1,000.00','0.00','14,000.00')]:
  page.insert_text((40,y),date);page.insert_text((140,y),narration)
  page.insert_text((300,y),debit);page.insert_text((390,y),credit);page.insert_text((480,y),balance)
 # A closing-balance summary after the last dated row must not be counted as
 # a second balance value for that transaction.
 page.insert_text((450,165),'Closing Balance')
 page.insert_text((480,165),'14,000.00')
 d.save(p);d.close()
 rows,meta=extract_native_table(p)
 assert not meta['rejected_rows']
 assert rows.date.dt.strftime('%Y-%m-%d').tolist()==['2026-09-01','2026-09-02']
 assert rows.type.tolist()==['CR','DR']
 assert rows.amount.tolist()==[5000,1000]
 assert rows.closing_balance.tolist()==[15000,14000]

def test_indian_payment_rail_confirms_currency_when_symbol_is_omitted():
 from ingestion.universal_pipeline import TextExtractor
 assert TextExtractor._safe_source_metadata('Payment mode: UPI','native_text',False)['currency']=='INR'
 assert TextExtractor._safe_source_metadata('Payment mode: card','native_text',False)['currency'] is None

def test_continuation_page_ignores_summary_dates_outside_dominant_date_column(tmp_path):
 source=tmp_path/'first-page.pdf';p=tmp_path/'continued.pdf';make_statement(source)
 d=fitz.open();base=fitz.open(source);d.insert_pdf(base);base.close();page=d.new_page()
 for y,date,narration,debit,balance in [(110,'03-Jan-2026','Expense','500.00','99,500.00'),
  (150,'04-Jan-2026','Expense','250.00','99,250.00')]:
  page.insert_text((40,y),date);page.insert_text((140,y),narration)
  page.insert_text((300,y),debit);page.insert_text((480,y),balance)
 page.insert_text((150,220),'01/01/2026');page.insert_text((190,220),'31/01/2026')
 d.save(p);d.close()
 rows,meta=extract_native_table(p)
 assert not meta['rejected_rows'] and len(rows)==4
 assert rows.source_page.tolist()==[1,1,2,2]

def test_encrypted_statement_password_reaches_bank_assessment_route(postgres_demo,tmp_path):
 from database.models import Consent
 from test_credit_card_document_assessment import multipart
 plain=tmp_path/'plain.pdf';make_statement(plain)
 document=fitz.open(plain);encrypted=tmp_path/'encrypted-statement.pdf'
 document.save(encrypted,encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='test-owner',user_pw='test-reader');document.close()
 state=postgres_demo;db=state['db'];headers={'session-id':state['borrower'].session_id}
 consent=db.query(Consent).filter_by(application_id=state['application'].application_id).one()
 consent.bank_consent=True;db.commit()
 response=state['client'].post('/assess/bank-cashflow',headers=headers,
  data={'assessment_profile':'auto','statement_password':'test-reader'},files=multipart([encrypted]))
 assert response.status_code==200,response.text
 result=response.json()
 assert result['score'] is not None and result['transaction_count']==2

def test_single_month_snapshot_can_use_reconciled_source_order_for_posted_dates():
 import pandas as pd
 from route.bank_cashflow_routes import _single_month_snapshot_order_valid
 tx=pd.DataFrame({'date':pd.to_datetime(['2026-05-01','2026-05-03','2026-05-02']),
  'amount':[100,20,30],'type':['CR','DR','DR'],'closing_balance':[100,80,50],
  'source_page':[1,1,2],'source_line':[1,2,1],'source_document_id':['one']*3})
 metadata=[{'statement_period':{'start':'2026-05-01','end':'2026-05-31'}}]
 assert _single_month_snapshot_order_valid(tx,metadata)
 tx.loc[2,'closing_balance']=51
 assert not _single_month_snapshot_order_valid(tx,metadata)

def test_missing_amount_is_unknown():
 df=BankExtractor()._build_df([{'date':'01/01/2026','narration':'unknown','debit':None,'credit':None,'closing_balance':100,'source_page':1,'source_line':1}])
 assert df.amount.isna().all()

def test_multi_page_and_encrypted_inspection(tmp_path):
 p=tmp_path/'one.pdf';make_statement(p)
 document=fitz.open(p);document.insert_pdf(fitz.open(p));multi=tmp_path/'multi.pdf';document.save(multi);document.close()
 rows,meta=extract_native_table(multi)
 assert len(rows)==4 and rows.source_page.tolist()==[1,1,2,2]
 encrypted=tmp_path/'encrypted.pdf';document=fitz.open(p);document.save(encrypted,encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='test-owner',user_pw='test-reader');document.close()
 with pytest.raises(ValueError,match='DOCUMENT_COULD_NOT_BE_READ'):extract_native_table(encrypted)
 assert len(extract_native_table(encrypted,'test-reader')[0])==2


def test_period_four_digit_dates_not_prefix_duplicates():
 from ingestion.universal_pipeline import TextExtractor
 meta=TextExtractor._safe_source_metadata('Statement of account for period of 01/01/2026 to 30/06/2026','native_text',False)
 assert meta['statement_period']=={'start':'2026-01-01','end':'2026-06-30'}


def test_consented_preview_and_auto_index(postgres_demo):
 from test_validated_demo_dossier import ROOT
 from test_credit_card_document_assessment import multipart
 from database.models import Consent
 state=postgres_demo;headers={'session-id':state['borrower'].session_id};client=state['client']
 bank=ROOT/'Bank_Statement_2026-03.pdf'
 assert client.post('/assess/bank-cashflow/preview',headers=headers,files=multipart([bank])).status_code==403
 consent=state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one();consent.bank_consent=True;state['db'].commit()
 preview=client.post('/assess/bank-cashflow/preview',headers=headers,files=multipart([bank]))
 assert preview.status_code==200,preview.text
 row=preview.json()['documents'][0];assert row['transaction_count']==8 and row['balances_reconciled'] is True
 assert row['total_credits']==92000 and row['total_debits']==72550
 assert len(row['transactions'])==8 and all(tx['source_page']==1 for tx in row['transactions'])
 all_banks=sorted(ROOT.glob('Bank_Statement_*.pdf'))
 result=client.post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'auto'},files=multipart(all_banks))
 assert result.status_code==200,result.text
 assert result.json()['model_version']=='BANK_FINANCIAL_HEALTH_INDEX_V1' and result.json()['score']==775

from test_credit_card_document_assessment import postgres_demo

def test_authorized_sbi_sample_against_source_words():
 import re,pandas as pd
 p=Path(__file__).parents[1]/'data'/'real world'/'448392605-Bank-Statement-1.pdf'
 if not p.exists():pytest.skip('Private compatibility sample not installed')
 rows,metadata=extract_native_table(p)
 with fitz.open(p) as document:
  words=document[0].get_text('words')
  date_words=[w[4] for w in words if 420<w[1]<575 and w[0]<90 and re.fullmatch(r'\d{2}-[A-Za-z]{3}-\d{2}',w[4])]
  money_words=[float(w[4].replace(',','')) for w in words if 420<w[1]<575 and w[0]>340 and re.fullmatch(r'[\d,]+\.\d{2}',w[4])]
 assert len(rows)==6 and not metadata['rejected_rows']
 assert bool(rows.date.tolist()==[pd.to_datetime(value,format='%d-%b-%y') for value in date_words])
 assert bool(sorted(rows.amount.tolist()+rows.closing_balance.tolist())==sorted(money_words))
 assert bool(rows.type.tolist()==['DR','DR','DR','DR','CR','DR'])
 reconciled=bool((abs(rows.closing_balance.diff().iloc[1:].to_numpy()-(rows.amount*rows.type.map({'CR':1,'DR':-1})).iloc[1:].to_numpy())<=0.05).all())
 assert reconciled


def test_multiple_account_references_do_not_link(monkeypatch):
 from ingestion.universal_pipeline import TextExtractor
 monkeypatch.setenv('PRISM_ACCOUNT_REFERENCE_SALT','test-only-reference-salt')
 meta=TextExtractor._safe_source_metadata('Account number: 11111111111\nAccount number: 22222222222','native_text',False)
 assert meta['account_reference_token'] is None

def test_descending_same_day_rows_across_pages_reconcile():
 import pandas as pd
 from route.bank_cashflow_routes import _observed_balance_validation
 # Newest first: reversing dates alone leaves same-day rows in the wrong order.
 tx=pd.DataFrame({'date':pd.to_datetime(['2026-02-02','2026-02-02','2026-02-01']),
  'amount':[20,30,100],'type':['DR','DR','CR'],'closing_balance':[50,70,100],
  'source_document_id':['one']*3,'source_page':[1,2,2],'source_line':[1,1,2]})
 assert _observed_balance_validation(tx)
 tx.loc[1,'closing_balance']=71
 assert not _observed_balance_validation(tx)

def test_testing_indian_bank_auto_scores(postgres_demo):
 from test_credit_card_document_assessment import multipart
 from database.models import Consent
 p=Path(__file__).parents[1]/'data'/'testing'/'749911810-indian-bank-6-mnths-1.pdf'
 if not p.exists():pytest.skip('Private compatibility sample not installed')
 state=postgres_demo;headers={'session-id':state['borrower'].session_id}
 consent=state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one();consent.bank_consent=True;state['db'].commit()
 response=state['client'].post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'auto'},files=multipart([p]))
 assert response.status_code==200
 result=response.json();assert result['score']==438 and result['transaction_count']==233
 assert result['months_observed']==6 and result['coverage']['balance_verification_scope']=='OBSERVED_SUCCESSIVE_RUNNING_BALANCES'

def test_actual_sbi_auto_scores_and_rejects_balance_corruption(postgres_demo):
 from test_credit_card_document_assessment import multipart
 from database.models import Consent
 from ingestion.parsers.bank_parser import BankParser
 from route.bank_cashflow_routes import _observed_balance_validation
 p=Path(__file__).parents[1]/'data'/'real world'/'448392605-Bank-Statement-1.pdf'
 if not p.exists():pytest.skip('Private compatibility sample not installed')
 state=postgres_demo;headers={'session-id':state['borrower'].session_id}
 consent=state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one();consent.bank_consent=True;state['db'].commit()
 response=state['client'].post('/assess/bank-cashflow',headers=headers,data={'assessment_profile':'auto'},files=multipart([p]))
 assert response.status_code==200
 result=response.json();assert result['score']==308 and result['transaction_count']==6
 assert result['coverage']['declared_opening_closing_verified'] is False
 assert result['coverage']['balance_verification_scope']=='OBSERVED_SUCCESSIVE_RUNNING_BALANCES'
 parser=BankParser();tx=parser.extract(str(p));tx['source_document_id']='sample'
 assert _observed_balance_validation(tx)
 tx.loc[tx.index[2],'closing_balance']+=100
 assert not _observed_balance_validation(tx)
 assert not _observed_balance_validation(tx.iloc[:1])


def test_latest_failed_history_does_not_hide_scored_bank(postgres_demo):
 from test_validated_demo_dossier import ROOT
 from test_credit_card_document_assessment import multipart
 from database.models import Consent
 state=postgres_demo;headers={'session-id':state['borrower'].session_id};client=state['client']
 consent=state['db'].query(Consent).filter_by(application_id=state['application'].application_id).one();consent.bank_consent=True;state['db'].commit()
 good=client.post('/assess/bank-cashflow',headers=headers,files=multipart(sorted(ROOT.glob('Bank_Statement_*.pdf')))).json()
 bad=client.post('/assess/bank-cashflow',headers=headers,files=multipart([ROOT/'Bank_Statement_2026-03.pdf'])).json()
 assert bad['score'] is None
 assert client.get('/assess/bank-cashflow/latest',headers=headers).json()['assessment_id']==good['assessment_id']
 lender=client.get(f"/lender/applications/{state['application'].application_id}",headers={'session-id':state['lender'].session_id}).json()
 assert lender['bank_cashflow_assessment']['assessment_id']==good['assessment_id']
 assert 'monthly_balance_trend' in good and len(good['monthly_balance_trend'])==6

def test_native_validated_rows_equal_independent_ground_truth():
 import pandas as pd
 from test_validated_demo_dossier import ROOT,TRUTH
 actual=pd.concat([extract_native_table(p)[0] for p in sorted(ROOT.glob('Bank_Statement_*.pdf'))],ignore_index=True)
 expected=TRUTH['bank_transactions']
 assert len(actual)==len(expected)==48
 for row,truth in zip(actual.itertuples(),expected):
  assert row.date.strftime('%Y-%m-%d')==truth['date']
  assert row.type==('CR' if truth['credit']>0 else 'DR')
  assert row.amount==(truth['credit'] if truth['credit']>0 else truth['debit'])
  assert row.closing_balance==truth['balance']
