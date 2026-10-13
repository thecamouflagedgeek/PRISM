import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';

const root = resolve('../backend/test_fixtures');
const validated = resolve('../tests/fixtures/prism_demo_validated');
const manualFixtureDirectory = process.env.PRISM_MANUAL_FIXTURE_DIR || validated;
const truth = JSON.parse(readFileSync(resolve(validated, 'ground_truth.json')));
const artifact = JSON.parse(readFileSync(resolve('../backend/phase2/outputs/phase2f/frozen_shadow_scorecard.json')));
const output = resolve('../docs/live-demo');
mkdirSync(output, { recursive: true });

// Independent arithmetic from ground truth and immutable artifact, not API scores.
const features = truth.frozen_model_input_candidates;
let logit = artifact.logistic_regression.intercept;
for (const [name, value] of Object.entries(features)) {
  const bin = artifact.features[name].bins.find(b => !b.missing_bin &&
    (b.interval_closure.startsWith('[') ? value >= Number(b.lower_bound) : value > Number(b.lower_bound)) && value <= Number(b.upper_bound));
  if (!bin) throw new Error(`No independent frozen bin for ${name}`);
  logit += artifact.logistic_regression.coefficients[name] * bin.woe;
}
const pd = 1 / (1 + Math.exp(-logit));
const creditScore = 600 + 50 / Math.log(2) * Math.log((1 - pd) / pd / 20);
const rows = truth.bank_transactions;
const monthly = truth.monthly_summary.map(m => {
  const selected = rows.filter(r => r.date.startsWith(m.month));
  return { income: selected.reduce((s,r) => s+r.credit, 0), expense: selected.reduce((s,r) => s+r.debit, 0) };
});
const income = monthly.reduce((s,r) => s+r.income,0)/6;
const expense = monthly.reduce((s,r) => s+r.expense,0)/6;
const cv = Math.sqrt(monthly.reduce((s,r) => s+(r.income-income)**2,0)/5)/income;
const debt = rows.filter(r => /\bemi\b/i.test(r.description)).reduce((s,r) => s+r.debit,0)/6;
const bankFactors = { surplus_month_rate: monthly.filter(r => r.income>r.expense).length/6,
  expense_to_income: 1-expense/income, income_regularity: 1/(1+cv),
  liquidity_buffer: Math.min(1,rows.reduce((s,r)=>s+r.balance,0)/rows.length/(3*expense)), debt_burden:1-debt/income };
const bankIndex = Math.round(300+600*(bankFactors.surplus_month_rate*.25+bankFactors.expense_to_income*.25+bankFactors.income_regularity*.2+bankFactors.liquidity_buffer*.15+bankFactors.debt_burden*.15));

async function login(page, phone, lender=false) {
  await page.goto('/');
  await page.getByRole('button',{name:lender ? "I'm a Lender →" : "I'm a Borrower →",exact:true}).first().click();
  await page.getByRole('textbox').fill(phone);
  const otpLogOffset=readFileSync('.demo-runtime/backend.log','utf8').length;
  await page.getByRole('button',{name:'Continue →',exact:true}).click();
  let otp;
  await expect.poll(() => {
    const matches = [...readFileSync('.demo-runtime/backend.log','utf8').slice(otpLogOffset).matchAll(/Generated OTP: (\d+)\s+Phone: ([^\r\n]+)/g)];
    otp = matches.filter(m=>m[2]===phone).at(-1)?.[1]; return Boolean(otp);
  }).toBe(true);
  await page.getByRole('textbox').fill(otp);
  await page.getByRole('button',{name:'Verify OTP →',exact:true}).click();
}

test('defective optional card history does not block the primary bank snapshot', async ({page}) => {
  await login(page,'1998'+String(Date.now()).slice(-7));
  await page.getByText('Salary Slip Access',{exact:true}).click();
  await page.getByText('Utility Bill Access',{exact:true}).click();
  await page.getByRole('button',{name:'Record Consent & Continue →',exact:true}).click();
  for(const [button,prefix] of [['Add Salary Slip files','Salary_Slip'],['Add Utility Bill files','Utility_Bill'],['Add bank statement files','Bank_Statement'],['Add statement files','Credit_Card']]) {
    const chooser=page.waitForEvent('filechooser'); await page.getByRole('button',{name:button,exact:true}).click();
    await(await chooser).setFiles(['03','04','05','06','07','08'].map(m=>resolve(root,`aarav_original/${prefix}_2026-${m}.pdf`)));
  }
  await expect(page.getByText('24 documents uploaded',{exact:false})).toBeVisible();
  await page.getByRole('checkbox').check();
  const cr=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/assess/credit-card-statements'));
  const br=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/assess/bank-cashflow'));
  await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
  const credit=await(await cr).json(), bank=await(await br).json();
  expect(credit.score).toBeNull(); expect(bank.score).toBe(775);
  expect(credit.evidence_validation.blocking_reasons).toContain('MONTH_WINDOW_OR_CONTINUITY_INVALID');
  expect(bank.coverage.page_completeness_verified).toBe(false);
  expect(bank.transaction_count).toBe(48); expect(bank.months_observed).toBe(6);
  expect(bank.financial_metrics.average_monthly_expenses).toBeGreaterThan(0);
  await expect(page.getByTestId('primary-score')).toHaveText('775');
  await expect(page.getByText(/insufficient[_ ]evidence/i)).toHaveCount(0);
  writeFileSync(resolve(output,'original-negative-browser.json'),JSON.stringify({credit,bank,verification:'Original manual-upload reproduction'},null,2));
  await page.screenshot({path:resolve(output,'original-negative-browser.png')});
});

test('fresh authenticated borrower gets both real scorecards, refresh, simulations, PDFs and lender retrieval', async ({page, browser}, testInfo) => {
  const runOutput = resolve(output, process.env.PRISM_UI_REVIEW ? 'ui-refresh' : process.env.PRISM_FOLDER_FIXTURE_DIR ? 'downloads-folder-run' : process.env.PRISM_MANUAL_FIXTURE_DIR ? `real-integration-manual-${testInfo.repeatEachIndex+1}` : `validated-run-${testInfo.repeatEachIndex+1}`); mkdirSync(runOutput,{recursive:true});
  expect(creditScore).toBeCloseTo(454.635898966963,8);
  expect(pd).toBeCloseTo(.2727810906249319,10);
  expect(bankIndex).toBe(775);
  const network=[], pending=[];
  const captureResponse = response => {
    if (!response.url().startsWith(`http://127.0.0.1:${process.env.PRISM_DEMO_PORT || '8000'}`)) return;
    pending.push((async()=> {
      let body; try {body=await response.json();} catch {body={content_type:response.headers()['content-type']};}
      if(body?.session_id) body={...body,session_id:'[REDACTED]'};
      network.push({url:response.url(),method:response.request().method(),status:response.status(),body});
    })());
  };
  page.on('response', captureResponse);
  const phone='1999'+String(Date.now()).slice(-7);
  await login(page,phone);
  await page.getByText('Salary Slip Access',{exact:true}).click();
  await page.getByText('Utility Bill Access',{exact:true}).click();
  await page.getByRole('button',{name:'Record Consent & Continue →',exact:true}).click();
  if (process.env.PRISM_FOLDER_FIXTURE_DIR) {
    for (const [button,prefix] of [['Add bank statement files','Bank_Statement'],['Add statement files','Credit_Card']]) {
      const chooser = page.waitForEvent('filechooser'); await page.getByRole('button',{name:button,exact:true}).click();
      await(await chooser).setFiles(resolve(process.env.PRISM_FOLDER_FIXTURE_DIR,`${prefix}_2026-03.pdf`));
    }
    await page.getByRole('checkbox').check();
    await expect(page.getByRole('button',{name:'Run Assessment →',exact:true})).toBeEnabled();
    await page.getByText('Bulk import & fictional demo',{exact:true}).click();
    const chooser = page.waitForEvent('filechooser'); await page.getByRole('button',{name:'Select entire dossier folder',exact:true}).click();
    await(await chooser).setFiles(process.env.PRISM_FOLDER_FIXTURE_DIR);
    await expect(page.getByRole('checkbox')).not.toBeChecked();
    await expect(page.getByRole('alert')).toHaveCount(0);
  } else if (testInfo.repeatEachIndex === 1 || process.env.PRISM_MANUAL_FIXTURE_DIR) {
    for(const [button,prefix] of [['Add Salary Slip files','Salary_Slip'],['Add Utility Bill files','Utility_Bill'],['Add bank statement files','Bank_Statement'],['Add statement files','Credit_Card']]) {
      const chooser=page.waitForEvent('filechooser'); await page.getByRole('button',{name:button,exact:true}).click();
      await(await chooser).setFiles(['03','04','05','06','07','08'].map(m=>resolve(manualFixtureDirectory,`${prefix}_2026-${m}.pdf`)));
    }
    await page.getByText('Additional historical card assessment',{exact:true}).click();
    await page.getByRole('button',{name:'Use historical cutoff 2026-09',exact:true}).click();
  } else {
    await page.getByText('Bulk import & fictional demo',{exact:true}).click();
    await page.getByRole('button',{name:'Load Validated Synthetic Dossier',exact:true}).click();
  }
  await expect(page.getByText('24 documents uploaded',{exact:false})).toBeVisible();
  await expect(page.getByPlaceholder('YYYY-MM (optional)')).toHaveValue('2026-09');
  const manifest=JSON.parse(readFileSync(resolve(validated,'manifest.json')));
  for(const item of manifest.files) await expect(page.getByText(item.name,{exact:false})).toBeVisible();
  await page.screenshot({path:resolve(runOutput,'upload.png'),fullPage:true});
  const requests=[];
  page.on('request',req=>{
    if(req.method()==='POST' && /\/assess\/(bank-cashflow|credit-card-statements)$/.test(req.url())) {
      const payload=req.postDataBuffer()?.toString('latin1') || '';
      const filenames=[...payload.matchAll(/filename="([^"]+)"/g)].map(m=>m[1]);
      requests.push({url:req.url(),filenames,fields:[...payload.matchAll(/name="([^"]+)"/g)].map(m=>m[1]),authentication:'session-id header present; value redacted'});
      expect(req.headers()['session-id']).toBeTruthy();
    }
  });
  await page.getByRole('checkbox').check();
  const creditResponse=page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith('/assess/credit-card-statements'));
  const bankResponse=page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith('/assess/bank-cashflow'));
  await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
  const credit=await (await creditResponse).json(), bank=await (await bankResponse).json();
  expect(credit.score).toBeCloseTo(creditScore,8); expect(credit.probability_of_default).toBeCloseTo(pd,10);
  expect(bank.score).toBe(bankIndex); expect(bank.pd).toBeNull();
  expect(bank.transaction_count).toBe(48); expect(bank.months_observed).toBe(6); expect(bank.supporting_documents).toHaveLength(12);
  expect(bank.evidence.balance_reconciled).toBe(true);
  expect(bank.aggregation_receipt.debits_parsed).toBe(42); expect(bank.aggregation_receipt.credits_parsed).toBe(6);
  for(const [name,value] of Object.entries(features)) expect(Number(credit.feature_values[name])).toBeCloseTo(value,8);
  for(const [name,value] of Object.entries(bankFactors)) expect(bank.feature_values[name]).toBeCloseTo(value,5);
  await expect(page.getByTestId('credit-score')).toHaveText(creditScore.toFixed(2));
  await expect(page.getByTestId('bank-index')).toHaveText(String(bankIndex));
  await expect(page.getByRole('heading',{name:'Processing your documents',exact:true})).toHaveCount(0);
  const receipts = readFileSync('.demo-runtime/backend.log','utf8').split('\n').filter(line=>line.includes('demo_upload '))
    .map(line=>JSON.parse(line.split('demo_upload ')[1])).filter(r=>r.application_id===credit.application_id);
  expect(receipts.find(r=>r.path.endsWith('/bank-cashflow')).files).toHaveLength(18);
  expect(receipts.find(r=>r.path.endsWith('/credit-card-statements')).files).toHaveLength(6);
  expect(receipts.flatMap(r=>r.files.map(f=>f.filename)).sort()).toEqual(manifest.files.map(f=>f.name).sort());
  await page.screenshot({path:resolve(runOutput,'both-scorecards.png')});
  if (process.env.PRISM_UI_REVIEW) {
    expect(bank.fraud_findings.engine_version).toBe('P1-v1');
    expect(bank.fraud_findings.coverage.transactions_reviewed).toBe(48);
    await expect(page.getByRole('heading',{name:'Focus on what you can improve'})).toBeVisible();
    await page.getByRole('tab',{name:'Why this score',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Reason codes',exact:true})).toBeVisible();
    await page.screenshot({path:resolve(runOutput,'explainability.png'),fullPage:true});
    await page.getByRole('tab',{name:'Fraud flags',exact:true}).click();
    await expect(page.getByRole('heading',{name:'Fraud & integrity checks',exact:true})).toBeVisible();
    await expect(page.getByText('P1-v1',{exact:true})).toBeVisible();
    await page.screenshot({path:resolve(runOutput,'fraud.png'),fullPage:true});
    await page.getByRole('tab',{name:'Borrower rights',exact:true}).click();
    await expect(page.getByRole('link',{name:'RBI: Digital Lending Directions ↗'})).toHaveAttribute('href',/rbi.org.in/);
    await page.screenshot({path:resolve(runOutput,'rights.png'),fullPage:true});
    await page.getByRole('tab',{name:'Your next steps',exact:true}).click();
    await page.setViewportSize({width:390,height:844});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({path:resolve(runOutput,'mobile.png'),fullPage:true});
    await page.setViewportSize({width:1400,height:1000});
  }
  await page.reload();
  await expect(page.getByTestId('credit-score')).toHaveText(creditScore.toFixed(2));
  await expect(page.getByTestId('bank-index')).toHaveText(String(bankIndex));
  await page.getByRole('tab',{name:'What-if',exact:true}).click();
  await page.locator('input[type="number"]').filter({visible:true}).count();
  const creditWhatIf=page.waitForResponse(r=>r.url().endsWith(`/credit-card-assessments/${credit.assessment_id}/what-if`));
  await page.getByLabel('Payment-to-statement ratio',{exact:true}).fill('0.9');
  await page.getByRole('button',{name:'Simulate →',exact:true}).click();
  const scenario=await(await creditWhatIf).json(); expect(scenario.delta.score).toBeGreaterThan(0);
  await expect(page.getByText(scenario.scenario.scorecard.experimental_shadow_score.toFixed(1),{exact:true})).toBeVisible();
  await page.getByText('Explore bank cash flow',{exact:true}).click();
  await page.getByLabel('Monthly income',{exact:true}).fill('110000');
  const bankWhatIf=page.waitForResponse(r=>r.url().endsWith(`/bank-cashflow/${bank.assessment_id}/what-if`));
  await page.getByRole('button',{name:'Run hypothetical scenario',exact:true}).click();
  expect((await(await bankWhatIf).json()).score).toBe(790);
  await expect(page.getByText('Original: 775 · Scenario: 790 · Difference: +15',{exact:true})).toBeVisible();
  for(const [button,name] of [['Download persisted assessment PDF','credit.pdf'],['Download report PDF','bank.pdf']]) {
    const download=page.waitForEvent('download'); await page.getByRole('button',{name:button,exact:true}).click();
    await(await download).saveAs(resolve(runOutput,name));
  }
  await page.reload(); await expect(page.getByTestId('credit-score')).toHaveText(creditScore.toFixed(2)); await expect(page.getByTestId('bank-index')).toHaveText('775');
  await page.getByRole('button',{name:'Update documents for this application',exact:true}).click();
  await page.getByText('Bulk import & fictional demo',{exact:true}).click();
  await page.getByRole('button',{name:'Load Validated Synthetic Dossier',exact:true}).click();
  await expect(page.getByText('24 documents uploaded',{exact:false})).toBeVisible(); await page.getByRole('checkbox').check();
  const replayCredit=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/assess/credit-card-statements'));
  const replayBank=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/assess/bank-cashflow'));
  await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
  expect((await(await replayCredit).json()).assessment_id).toBe(credit.assessment_id);
  expect((await(await replayBank).json()).assessment_id).toBe(bank.assessment_id);
  const lender=await browser.newPage(); lender.on('response',captureResponse); await login(lender,'+19990000002',true);
  const row=lender.locator(`[data-testid="application-${credit.application_id}"]`);
  const lenderDetail=lender.waitForResponse(r=>r.url().endsWith(`/lender/applications/${credit.application_id}`));
  await row.getByRole('button',{name:'View →',exact:true}).click();
  const lenderSaved=await(await lenderDetail).json();
  expect(lenderSaved.experimental_assessment.assessment_id).toBe(credit.assessment_id);
  expect(lenderSaved.bank_cashflow_assessment.assessment_id).toBe(bank.assessment_id);
  await expect(lender.getByText(creditScore.toFixed(1),{exact:true})).toBeVisible();
  await expect(lender.getByTestId('bank-scorecard')).toContainText('775');
  await lender.screenshot({path:resolve(runOutput,'lender.png')});
  await Promise.all(pending);
  expect(network.filter(r=>[401,404,500].includes(r.status))).toEqual([]);
  writeFileSync(resolve(runOutput,'browser-evidence.json'),JSON.stringify({application_id:credit.application_id,credit,bank,selection_mode:process.env.PRISM_FOLDER_FIXTURE_DIR?'whole-folder upload':testInfo.repeatEachIndex===1||process.env.PRISM_MANUAL_FIXTURE_DIR?'ordinary manual upload':'development fixture selector',
    independent:{features,pd,creditScore,bankFactors,bankIndex},requests,receipts,network,verification:'Actual Playwright fresh borrower UI journey passed'},null,2));
});
