import { test, expect } from '@playwright/test';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve } from 'node:path';
const fixtures=resolve('../tests/fixtures/prism_demo_validated');
const output=resolve('../docs/live-demo/thin-file');mkdirSync(output,{recursive:true});
async function login(page,phone,lender=false){await page.goto('/');await page.getByRole('button',{name:lender?"I'm a Lender →":"I'm a Borrower →",exact:true}).first().click();await page.getByRole('textbox').fill(phone);const otpLogOffset=readFileSync('.demo-runtime/backend.log','utf8').length;await page.getByRole('button',{name:'Continue →',exact:true}).click();let otp;await expect.poll(()=>{const matches=[...readFileSync('.demo-runtime/backend.log','utf8').slice(otpLogOffset).matchAll(/Generated OTP: (\d+)\s+Phone: ([^\r\n]+)/g)];otp=matches.filter(match=>match[2]===phone).at(-1)?.[1];return Boolean(otp);}).toBe(true);await page.getByRole('textbox').fill(otp);await page.getByRole('button',{name:'Verify OTP →',exact:true}).click();}
for(const mode of ['bank-only','bank-salary-utility','bank-with-one-card']){
 test(`thin-file ${mode} produces a primary score without a dossier`,async({page,browser})=>{
  const run=resolve(output,mode);mkdirSync(run,{recursive:true});
  await login(page,'1888'+String(Date.now()).slice(-7));
  if(mode==='bank-only')await page.getByText('Salary Slip Access',{exact:true}).click();
  if(mode!=='bank-only'){await page.getByText('Salary Slip Access',{exact:true}).click();await page.getByText('Utility Bill Access',{exact:true}).click();}
  await page.getByRole('button',{name:'Record Consent & Continue →',exact:true}).click();
  await expect(page.getByRole('button',{name:'Run Assessment →',exact:true})).toBeDisabled();
  if(mode==='bank-only'){await page.screenshot({path:resolve(run,'upload-desktop.png'),fullPage:true});await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await page.screenshot({path:resolve(run,'upload-mobile.png'),fullPage:true});await page.setViewportSize({width:1400,height:1000});}
  const add=async(button,file)=>{const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:button,exact:true}).click();await(await chooser).setFiles(resolve(fixtures,file));};
  if(mode==='bank-only'){
    await add('Add Salary Slip files','Salary_Slip_2026-03.pdf');
    await page.getByRole('button',{name:'← Back to consent',exact:true}).click();
    await page.getByText('Salary Slip Access',{exact:true}).click();
    await page.getByRole('button',{name:'Record Consent & Continue →',exact:true}).click();
    await expect(page.getByRole('button',{name:'Remove Salary_Slip_2026-03.pdf',exact:true})).toHaveCount(0);
    await add('Add bank statement files','Salary_Slip_2026-03.pdf');
    const rejected=page.waitForResponse(response=>response.request().method()==='POST'&&response.url().endsWith('/assess/bank-cashflow'));
    await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
    expect((await rejected).status()).toBe(422);
    await expect(page.getByRole('alert')).toContainText('statement');
    await expect(page.getByRole('heading',{name:'Start with your bank statement'})).toBeVisible();
    await expect(page.getByText(/insufficient[_ ]evidence/i)).toHaveCount(0);
    await page.getByRole('button',{name:'Remove Salary_Slip_2026-03.pdf',exact:true}).first().click();
  }
  const month=mode==='bank-with-one-card'?'08':'03';
  await add('Add bank statement files',`Bank_Statement_2026-${month}.pdf`);
  if(mode==='bank-only'){
    const denied=async route=>route.fulfill({status:403,contentType:'application/json',body:JSON.stringify({detail:'Recorded consent is required for each supporting category'})});
    await page.route('**/assess/bank-cashflow',denied);await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
    await expect(page.getByRole('alert')).toContainText('consent');
    await expect(page.getByRole('heading',{name:'Start with your bank statement'})).toBeVisible();
    await expect(page.getByRole('button',{name:'Remove Bank_Statement_2026-03.pdf',exact:true})).toBeVisible();
    await page.unroute('**/assess/bank-cashflow',denied);
  }
  if(mode==='bank-only'){const preview=page.waitForResponse(response=>response.url().endsWith('/bank-cashflow/preview'));await page.getByRole('button',{name:'Preview extracted transactions',exact:true}).click();expect((await preview).status()).toBe(200);await expect(page.getByRole('heading',{name:'Review extracted statement values'})).toBeVisible();}
  if(mode!=='bank-only'){await add('Add Salary Slip files','Salary_Slip_2026-07.pdf');await add('Add Utility Bill files','Utility_Bill_2026-08.pdf');}
  if(mode==='bank-with-one-card'){await add('Add statement files','Credit_Card_2026-08.pdf');await page.getByRole('checkbox').check();}
  await expect(page.getByRole('button',{name:'Run Assessment →',exact:true})).toBeEnabled();
  await expect(page.getByText('Complete the six-month dossier',{exact:true})).toHaveCount(0);
  await page.screenshot({path:resolve(run,'upload.png'),fullPage:true});
  const bankResponse=page.waitForResponse(response=>response.request().method()==='POST'&&response.url().endsWith('/assess/bank-cashflow'));
  const optional=mode==='bank-with-one-card'?page.waitForResponse(response=>response.request().method()==='POST'&&response.url().endsWith('/assess/credit-card-statements')):null;
  await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();
  const bank=await(await bankResponse).json();expect(bank.model_version).toBe('PRISM_CASHFLOW_SNAPSHOT_V1');expect(bank.status).toBe('SCORED');expect(bank.score).toBeGreaterThanOrEqual(300);expect(bank.score).toBeLessThanOrEqual(900);expect(bank.score).not.toBe(454.64);expect(bank.months_observed).toBe(1);expect(bank.transaction_count).toBe(8);expect(bank.feature_values.income_regularity).toBeNull();expect(bank.coverage.history_depth).toBe('LIMITED');expect(bank.pd).toBeNull();
  if(mode!=='bank-with-one-card')expect(bank.score).toBe(696);
  const credit=optional?await(await optional).json():null;if(credit)expect(credit.score).toBeNull();
  await expect(page.getByTestId('primary-score')).toHaveText(String(bank.score));
  await expect(page.getByText(/insufficient[_ ]evidence/i)).toHaveCount(0);
  await page.screenshot({path:resolve(run,'results.png'),fullPage:true});
  if(mode==='bank-only'){await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);await page.screenshot({path:resolve(run,'results-mobile.png'),fullPage:true});await page.setViewportSize({width:1400,height:1000});}
  await page.reload();await expect(page.getByTestId('primary-score')).toHaveText(String(bank.score));
  await page.getByRole('tab',{name:'Why this score',exact:true}).click();await expect(page.getByRole('heading',{name:'Patterns behind your cash-flow score'})).toBeVisible();
  await page.getByRole('tab',{name:'Fraud flags',exact:true}).click();await expect(page.getByText('P1-v1',{exact:true})).toBeVisible();
  await page.getByText('Explore bank cash flow',{exact:true}).click();await page.getByLabel('Monthly income',{exact:true}).fill('110000');
  const simulated=page.waitForResponse(response=>response.url().endsWith(`/bank-cashflow/${bank.assessment_id}/what-if`));await page.getByRole('button',{name:'Run hypothetical scenario',exact:true}).click();const scenario=await(await simulated).json();expect(scenario.model_version).toBe('PRISM_CASHFLOW_SNAPSHOT_V1');expect(scenario.feature_values.income_regularity).toBeNull();
  const download=page.waitForEvent('download');await page.getByRole('button',{name:'Download report PDF',exact:true}).click();await(await download).saveAs(resolve(run,'score.pdf'));
  await page.reload();await expect(page.getByTestId('primary-score')).toHaveText(String(bank.score));
  const lender=await browser.newPage();await login(lender,'+19990000002',true);const row=lender.locator(`[data-testid="application-${bank.application_id}"]`);const detail=lender.waitForResponse(response=>response.url().endsWith(`/lender/applications/${bank.application_id}`));await row.getByRole('button',{name:'View →',exact:true}).click();const saved=await(await detail).json();expect(saved.bank_cashflow_assessment.assessment_id).toBe(bank.assessment_id);expect(saved.bank_cashflow_assessment.score).toBe(bank.score);
  writeFileSync(resolve(run,'evidence.json'),JSON.stringify({application_id:bank.application_id,bank,credit,scenario,verification:'Fresh normal borrower and lender journey passed'},null,2));
 });
}
