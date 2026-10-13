"""Read-only database and downloaded-PDF corroboration of three browser runs."""
import json
from pathlib import Path
import fitz
from sqlalchemy.orm import Session
from database.db import engine
from database.models import ExperimentalAssessment, BankCashflowAssessment, Document

def main():
    root = Path(__file__).resolve().parents[1]
    results = []
    with Session(engine) as db:
        for number in range(1, 4):
            folder = root / 'docs/live-demo' / f'validated-run-{number}'
            evidence = json.loads((folder / 'browser-evidence.json').read_text())
            app = evidence['application_id']
            card = db.query(ExperimentalAssessment).filter_by(application_id=app, assessment_id=evidence['credit']['assessment_id']).one()
            bank = db.query(BankCashflowAssessment).filter_by(application_id=app, assessment_id=evidence['bank']['assessment_id']).one()
            assert abs(float(card.score)-evidence['credit']['score']) < 1e-8
            assert bank.score == evidence['bank']['score'] == 775
            assert db.query(Document).filter_by(application_id=app).count() == 24
            assert db.query(ExperimentalAssessment).filter_by(application_id=app).count() == 1
            assert db.query(BankCashflowAssessment).filter_by(application_id=app).count() == 1
            for kind, identity, value in [('credit',card.assessment_id,'454.635898966963'),('bank',bank.assessment_id,'Index score: 775')]:
                with fitz.open(folder / f'{kind}.pdf') as pdf:
                    content = ''.join(page.get_text() for page in pdf)
                    assert identity in content and value in content and f'Application: {app}' in content
                    if number == 2:
                        for page_index, page in enumerate(pdf):
                            page.get_pixmap(matrix=fitz.Matrix(1.3,1.3)).save(root / 'docs/validated-dossier-preview' / f'report-{kind}-{page_index+1}.png')
            results.append({'run':number,'upload':'manual' if number==2 else 'fixture selector','application_id':app,'credit_id':card.assessment_id,'bank_id':bank.assessment_id,'document_count':24,'credit_assessment_count':1,'bank_assessment_count':1,'database_and_pdf_verified':True})
    (root/'docs/live-demo/validated-database-verification.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))

if __name__ == '__main__': main()
