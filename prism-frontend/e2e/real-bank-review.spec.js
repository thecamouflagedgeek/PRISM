import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
for (const sample of [
 {name:'448392605-Bank-Statement-1.pdf',score:308,count:6},
 {name:'749911810-indian-bank-6-mnths-1.pdf',score:438,count:233}
]) test(`authorized statement ${sample.name} produces a persisted score`,async({page})=>{
 await page.goto('/');await page.getByRole('button',{name:"I'm a Borrower →",exact:true}).first().click();const phone='1887'+String(Date.now()).slice(-7);await page.getByRole('textbox').fill(phone);await page.getByRole('button',{name:'Continue →',exact:true}).click();let otp;await expect.poll(()=>{otp=[...readFileSync('.demo-runtime/backend.log','utf8').matchAll(/Generated OTP: (\d+)\s+Phone: ([^\r\n]+)/g)].filter(m=>m[2]===phone).at(-1)?.[1];return Boolean(otp);}).toBe(true);await page.getByRole('textbox').fill(otp);await page.getByRole('button',{name:'Verify OTP →',exact:true}).click();await page.getByRole('button',{name:'Record Consent & Continue →',exact:true}).click();
 const chooser=page.waitForEvent('filechooser');await page.getByRole('button',{name:'Add bank statement files',exact:true}).click();await(await chooser).setFiles(resolve('../data/testing',sample.name));
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/assess/bank-cashflow'));await page.getByRole('button',{name:'Run Assessment →',exact:true}).click();const scored=await response;expect(scored.status()).toBe(200);const result=await scored.json();expect(result.score).toBe(sample.score);expect(result.transaction_count).toBe(sample.count);expect(result.coverage.balance_verification_scope).toBe('OBSERVED_SUCCESSIVE_RUNNING_BALANCES');await expect(page.getByTestId('primary-score')).toHaveText(String(sample.score));await expect(page.getByRole('alert')).toHaveCount(0);await page.reload();await expect(page.getByTestId('primary-score')).toHaveText(String(sample.score));
});
