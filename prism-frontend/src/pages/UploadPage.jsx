// src/pages/UploadPage.jsx
import { useRef, useState } from "react";
import { Nav } from "../components/Nav";
import { api } from '../services/api';
import './AssessmentUI.css';

export default function UploadPage({ go, session, consents, files, setFiles, setAssessmentInput, error, setError }) {
  const [statementPassword,setStatementPassword] = useState('');
  const [creditCardConsent, setCreditCardConsent] = useState(false);
  const [cutoffMonth, setCutoffMonth] = useState("");
  const [extractionReview,setExtractionReview]=useState(null);
  const [reviewBusy,setReviewBusy]=useState(false);
  const review=async()=>{setReviewBusy(true);setError('');try{setExtractionReview(await api.previewBankStatements({sessionId:session.session_id,files:bankFiles,statementPassword}));}catch(error){setError(error.message);}finally{setReviewBusy(false);}};
  const [demoBusy, setDemoBusy] = useState(false);
  const [demoMessage, setDemoMessage] = useState('');
  const dossierFolderRef = useRef();
  const [folderMessage, setFolderMessage] = useState('');
  const selectDossierFolder = async (event) => {
    const selected = Array.from(event.target.files || []);
    const next = { salary: [], utility: [], bankStatements: [], creditCards: [] };
    const categories = {Bank_Statement:'bankStatements', Salary_Slip:'salary', Utility_Bill:'utility', Credit_Card:'creditCards'};
    for (const file of selected) {
      const match = file.name.match(/^(Bank_Statement|Salary_Slip|Utility_Bill|Credit_Card)_\d{4}-\d{2}\.pdf$/i);
      if (match) {
        const prefix = Object.keys(categories).find(key => key.toLowerCase() === match[1].toLowerCase());
        next[categories[prefix]].push(file);
      }
    }
    if (!next.bankStatements.length && !next.creditCards.length) {
      setFolderMessage('No dossier statement PDFs found. Select the folder containing Bank_Statement and Credit_Card PDFs.');
      event.target.value = ''; return;
    }
    if ((next.salary.length && !consents.salary) || (next.utility.length && !consents.utility)) {
      setFolderMessage('Enable salary and utility consent on the previous screen, then select the dossier folder again.');
      event.target.value = ''; return;
    }
    for (const list of Object.values(next)) list.sort((a,b) => a.name.localeCompare(b.name));
    const manifestFile = selected.find(file => file.name === 'manifest.json');
    let declaredCutoff = '';
    if (manifestFile) {
      try {
        const manifest = JSON.parse(await manifestFile.text());
        if (/^\d{4}-\d{2}$/.test(manifest.cutoff_month || '')) declaredCutoff = manifest.cutoff_month;
      } catch { /* Statements still use normal validation when folder metadata is absent. */ }
    }
    setFiles({...next, bank: next.bankStatements[0] || null});
    setCutoffMonth(declaredCutoff); setCreditCardConsent(false);
    setFolderMessage(`${Object.values(next).reduce((count,list) => count+list.length,0)} PDFs selected: ${next.bankStatements.length} bank, ${next.creditCards.length} card, ${next.salary.length} salary, ${next.utility.length} utility.${declaredCutoff ? ` Historical cutoff from the selected manifest: ${declaredCutoff}.` : ''} Review the files and confirm card consent.`);
    event.target.value = '';
  };
  const loadDemo = async () => {
    setDemoBusy(true); setDemoMessage('');
    try {
      const selected = await api.demoFixtures(session.session_id);
      setFiles(selected.files); setCutoffMonth(selected.cutoffMonth);
      setCreditCardConsent(false);
      setDemoMessage('24 corrected SYNTHETIC / FICTIONAL files selected, with explicit pages and repaired card dates. Historical exclusive cutoff: September 2026. Review card consent, then Run Assessment.');
    } catch (error) { setDemoMessage(error.message); }
    finally { setDemoBusy(false); }
  };
  const cardFiles = files.creditCards || [];

  const slots = [
    { key: "salary",  label: "Salary Slip",required: false, enabled: consents.salary,
      desc: "PDF, JPG, or PNG. Used for supporting income evidence." },
    { key: "utility", label: "Utility Bill",required: false, enabled: consents.utility,
      desc: "PDF, JPG, or PNG. Electricity, water, or telecom supporting evidence." },
  ];

  const bankFiles = files.bankStatements || (files.bank ? [files.bank] : []);
  const canProceed = Boolean(bankFiles.length) && (!cardFiles.length || creditCardConsent);

  const handleSubmit = () => {
    if (!session?.session_id) { setError("Session not found. Please log in again."); return; }
    if (!canProceed) return;
    setAssessmentInput({ sessionId: session.session_id, files: {...files, salary: consents.salary ? files.salary : [], utility: consents.utility ? files.utility : []}, creditCardConsent, cutoffMonth, statementPassword, bankFirst: true });
    go("processing");
  };

  const count = bankFiles.length + cardFiles.length + ['salary','utility'].reduce((total,key)=>total+(Array.isArray(files[key])?files[key].length:files[key]?1:0),0);
  return <div className="assessment-ui"><Nav currentPage="upload" onLogoClick={()=>go('landing')}/><main className="assessment-shell upload-reference"><div className="upload-layout"><aside className="upload-intro"><div className="assessment-eyebrow">Step 3 of 4 · Documents</div><h1>Start with your <span>bank statement</span></h1><p className="upload-lead">One readable bank statement is enough. Add other documents only if you have them.</p><section className="upload-guide"><div className="assessment-eyebrow">What happens next</div>{[['1','Read your documents','Extract dated transactions and statement balances.'],['2','Check the patterns','Check transaction order and balance consistency.'],['3','Explore your score','See explanations, next steps and hypothetical changes.']].map(([number,title,description])=><div className="upload-step" key={number}><span className="step-marker">{number}</span><div><b>{title}</b><p>{description}</p></div></div>)}</section><p>Your score describes the supplied bank activity. A credit-card account or six-month dossier is optional.</p><button className="btn-outline" onClick={()=>go('consent')}>← Back to consent</button></aside><div className="upload-document-column">
  {error&&<div role="alert" className="assessment-panel" style={{background:'#fffaf0'}}><h3>{/IDENTITY_CHECK_FAILED/i.test(error)?"Documents don’t match":/consent/i.test(error)?"Consent needs updating":/Document Could Not Be Read/i.test(error)?"Document Could Not Be Read":/timed out|Unable to reach|Processing Failed/i.test(error)?"Processing Failed":"Review Required"}</h3><p>{error}</p><p>Your selected files are still here. {/consent/i.test(error)?"Check optional file categories against recorded consent, then try again.":"Replace the affected file and try again."}</p>{/IDENTITY_CHECK_FAILED/i.test(error)&&<p>PRISM checks document names before generating the score. Replace the mismatched or unreadable supporting file.</p>}{/consent/i.test(error)&&<button className="btn-outline" onClick={()=>go('consent')}>Review consent →</button>}</div>}<div style={{display:'grid',gap:16}}><UploadCategory label="Bank statements · required" button="Add bank statement files" files={bankFiles} enabled={consents.bank} hint="Upload one PDF, JPG or PNG with dated debit/credit transactions and opening, running and closing balances. More statements are welcome, but not required." onFiles={next=>{setError("");setExtractionReview(null);setFiles(current=>({...current,bankStatements:next,bank:next[0]||null}));}}/>{slots.map(({key,label,enabled})=><UploadCategory key={key} label={`${label} · optional`} button={`Add ${label} files`} files={Array.isArray(files[key])?files[key]:files[key]?[files[key]]:[]} enabled={enabled} hint={key==='salary'?'A single slip supports the review of income. Your score does not depend on having one.':'A single bill adds supporting payment information. You can leave this empty.'} onFiles={next=>setFiles(current=>({...current,[key]:next}))}/>)}<UploadCategory label="Credit-card statements · optional" button="Add statement files" files={cardFiles} enabled={true} hint="Add a statement if you have a card. New-to-credit users can skip this entirely." onFiles={next=>setFiles(current=>({...current,creditCards:next}))}/></div>
  <section className="assessment-panel" style={{marginTop:18}}><label>Bank PDF password (only if encrypted)<input type="password" autoComplete="off" value={statementPassword} onChange={event=>setStatementPassword(event.target.value)} style={{display:"block",width:"100%",padding:12,border:"1px solid var(--border)",borderRadius:12,marginTop:8}}/></label><p>The password is used only to read this upload and is not saved in the assessment.</p></section>{cardFiles.length>0&&<section className="assessment-panel" style={{marginTop:18}}><h3>Optional card review</h3><p>Your bank cash-flow score is calculated independently of card history.</p>{cardFiles.length>=6&&<details><summary>Additional historical card assessment</summary><label>Historical cutoff (exclusive month)<input type="text" placeholder="YYYY-MM (optional)" pattern="[0-9]{4}-[0-9]{2}" value={cutoffMonth} onChange={e=>setCutoffMonth(e.target.value)}/></label>{cardFiles.every(file=>/Credit_Card_2026-0[3-8]\.pdf$/i.test(file.name))&&cutoffMonth!=='2026-09'&&<button className="btn-outline" onClick={()=>setCutoffMonth('2026-09')}>Use historical cutoff 2026-09</button>}<p>This optional research model uses six consecutive card months. It does not gate your bank score.</p></details>}<label style={{display:'flex',gap:12,alignItems:'flex-start',marginTop:16}}><input type="checkbox" checked={creditCardConsent} onChange={e=>setCreditCardConsent(e.target.checked)}/><span>I consent to processing these optional card statements for review and any eligible experimental card assessment.</span></label></section>}
  <section className="assessment-panel" style={{marginTop:18}}><button className="btn-outline" disabled={!bankFiles.length||reviewBusy} onClick={review}>{reviewBusy?"Reading statements…":"Preview extracted transactions"}</button>{extractionReview&&<><h3 style={{marginTop:18}}>Review extracted statement values</h3><p>{extractionReview.message}</p>{extractionReview.documents.map(document=><div key={document.document_id}><h3>{document.file_name}</h3><p>Detected bank: {document.detected_bank||"Unverified format"} · Account: {document.account_reference_available?"Reference available (masked)":"Reference needs confirmation"} · Period: {document.statement_period?`${document.statement_period.start} to ${document.statement_period.end}`:"Not verified"}</p><p>{document.transaction_count} transactions · {document.currency||"Currency needs confirmation"} · {document.balances_reconciled===true?"Balances reconciled":"Balances require review"}</p><p>Credits: {document.total_credits} · Debits: {document.total_debits} · Opening: {document.opening_balance??"Not verified"} · Closing: {document.closing_balance??"Not verified"}</p><div className="assessment-table-wrap"><table className="assessment-table"><thead><tr><th>Date</th><th>Direction</th><th>Amount</th><th>Balance</th><th>Source page</th></tr></thead><tbody>{document.transactions.map((transaction,index)=><tr key={index}><td>{transaction.date}</td><td>{transaction.direction}</td><td>{transaction.amount}</td><td>{transaction.running_balance}</td><td>{transaction.source_page}</td></tr>)}</tbody></table></div></div>)}</>}</section><div className="upload-selection-summary"><div><strong>{count} documents uploaded</strong><p style={{marginBottom:0}}>{bankFiles.length} bank · {Array.isArray(files.salary)?files.salary.length:0} salary · {Array.isArray(files.utility)?files.utility.length:0} utility · {cardFiles.length} card</p></div><span className={`status-pill ${!canProceed?'review':''}`}>{!bankFiles.length?'Add a bank statement':canProceed?'Ready to assess':'Confirm card consent'}</span></div><button className="btn-primary" onClick={handleSubmit} disabled={!canProceed} style={{width:'100%',justifyContent:'center'}}>Run Assessment →</button><p style={{textAlign:'center',fontSize:12,marginTop:12}}>Short history is shown as limited coverage, without blocking your cash-flow score.</p>
  <details className="technical-details"><summary>Bulk import & fictional demo</summary><p>You can also import multiple monthly PDFs from a folder. This is optional.</p><button className="btn-outline" type="button" onClick={()=>dossierFolderRef.current?.click()}>Select entire dossier folder</button><input ref={dossierFolderRef} type="file" multiple webkitdirectory="" directory="" hidden onChange={selectDossierFolder}/>{folderMessage&&<p role="status">{folderMessage}</p>}{import.meta.env.DEV&&import.meta.env.VITE_PRISM_DEMO_FIXTURES==='true'&&<><p>Development-only fictional files use the same processing pipeline.</p><button className="btn-outline" disabled={demoBusy||!consents.salary||!consents.utility} onClick={loadDemo}>{demoBusy?'Selecting…':'Load Validated Synthetic Dossier'}</button>{demoMessage&&<p role="status">{demoMessage}</p>}</>}</details>
  </div></div></main></div>;
}

function UploadCategory({label,button,files,enabled,hint,onFiles}) {
  const ref=useRef();
  const addFiles=selected=>{const unique=[...files];for(const file of selected.filter(file=>/\.(pdf|jpe?g|png)$/i.test(file.name))){if(!unique.some(existing=>existing.name===file.name&&existing.size===file.size&&existing.lastModified===file.lastModified))unique.push(file);}onFiles(unique);};
  const add=event=>{addFiles(Array.from(event.target.files||[]));event.target.value='';};
  const required=label.includes('required');
  return <section className={`upload-drop-card ${required?'required':''} ${!enabled?'disabled':''}`} onDragOver={event=>event.preventDefault()} onDrop={event=>{event.preventDefault();if(enabled)addFiles(Array.from(event.dataTransfer.files));}}><button className="upload-drop-target" type="button" aria-label={button} disabled={!enabled} onClick={()=>ref.current?.click()}><span className="document-icon" aria-hidden="true"><svg width="28" height="32" viewBox="0 0 28 32" fill="none"><path d="M6 2h10l6 6v22H6V2Z M16 2v7h6 M10 15h8 M10 20h8 M10 25h5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/></svg></span><span className="upload-drop-copy"><span className="upload-drop-title">{label.split(' · ')[0]} <span className={`document-badge ${required?'required':''}`}>{required?'Required':'Optional'}</span></span><span className="upload-drop-hint">{hint}</span><span className="upload-browse">Click to browse or drag &amp; drop · PDF, JPG or PNG</span></span></button><input ref={ref} type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png" onChange={add}/>{files.length>0&&<div className="selected-file-list"><span className="upload-count">{files.length} selected</span>{files.map((file,index)=><div className="upload-file-row" key={`${file.name}-${index}`}><span style={{overflowWrap:'anywhere'}}>{file.name}</span><button type="button" aria-label={`Remove ${file.name}`} onClick={()=>onFiles(files.filter((_,i)=>i!==index))}>Remove</button></div>)}</div>}{!enabled&&<small className="upload-disabled-note">Enable this document category in your consent settings.</small>}</section>;
}
