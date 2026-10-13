"""Convert the completed Phase 2 pytest JUnit file into required JSON results."""
import json, xml.etree.ElementTree as ET
from pathlib import Path
BACKEND=Path(__file__).resolve().parents[2]
OUT=BACKEND/'phase2'/'outputs'/'phase2c'
root=ET.parse(OUT/'pytest_results.xml').getroot()
suite=root.find('testsuite') if root.tag=='testsuites' else root
cases=[]
for t in suite.findall('testcase'):
    status='passed'; detail=None
    if t.find('failure') is not None: status='failed'; detail=t.find('failure').get('message')
    elif t.find('error') is not None: status='error'; detail=t.find('error').get('message')
    elif t.find('skipped') is not None: status='skipped'; detail=t.find('skipped').get('message')
    cases.append({'class':t.get('classname'),'name':t.get('name'),'status':status,'detail':detail})
phase2c=[x for x in cases if (x.get('class') or '').endswith('test_phase2c')]
counts={k:sum(x['status']==k for x in cases) for k in ('passed','failed','error','skipped')}
phase2c_counts={k:sum(x['status']==k for x in phase2c) for k in ('passed','failed','error','skipped')}
result={'interpreter':'Python 3.14.5','command':'py -3.14 -m pytest backend/phase2/tests -q','suite_counts':counts,'total_tests':len(cases),'phase2c_counts':phase2c_counts,'phase2c_test_count':len(phase2c),'cases':cases,'phase1_environment':'Python 3.12 runtime is not available to the launcher; Phase 1 suite not rerun in this audit.'}
(OUT/'equivalence_test_results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
summary=json.loads((OUT/'phase2c_summary.json').read_text(encoding='utf-8'))
summary['tests']=result
(OUT/'phase2c_summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
report=(OUT/'phase2c_report.md').read_text(encoding='utf-8')
verification='\n\n## Verification\n\nPhase 2 suite: **{passed} passed, {failed} failed, {error} errors, {skipped} skipped** ({total} tests total); Phase 2C checks: **{cpassed} passed, {cfailed} failed, {cerror} errors, {cskipped} skipped** ({ctotal} tests). Python 3.12 is unavailable to the launcher, so the Phase 1 suite was not rerun in this audit. The Phase 2B.6 output hashes and production artifact hashes matched the pre-audit snapshot.\n'.format(passed=counts['passed'],failed=counts['failed'],error=counts['error'],skipped=counts['skipped'],total=len(cases),cpassed=phase2c_counts['passed'],cfailed=phase2c_counts['failed'],cerror=phase2c_counts['error'],cskipped=phase2c_counts['skipped'],ctotal=len(phase2c))
marker='\n### Architecture decision\n'
if marker in report:
    arch_index=report.index(marker)
    source_index=report.index('\n## Source references\n',arch_index)
    verify_index=report.find('\n## Verification\n',source_index)
    if verify_index<0: verify_index=len(report)
    architecture=report[arch_index:source_index]
    sources=report[source_index:verify_index]
    report=report[:arch_index]+sources+verification+'\n'+architecture
else:
    report+=verification
(OUT/'phase2c_report.md').write_text(report,encoding='utf-8')
(OUT/'semantic_mapping_report.md').write_text(report,encoding='utf-8')
