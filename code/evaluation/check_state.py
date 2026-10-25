"""Step 3 check: preliminary COMPLETE/INCOMPLETE and finding recall vs sample_output.csv. Run: python code/evaluation/check_state.py"""
import sys,csv,json; sys.path.insert(0,__import__('pathlib').Path(__file__).resolve().parents[1].as_posix())
from collections import Counter
from auditor.config import DATASET
from auditor.data import Data
from auditor.evidence import build_index, system_of
from auditor.identity import resolve
from auditor.linker import build_ownership
from auditor.assign import assign_resources
from auditor.state import resource_state
d=Data(); ix=build_index(d.evidence_files); own=build_ownership(d,ix)
samples=list(csv.DictReader(open(DATASET/'sample_deletion_requests.csv')))
ALL=samples+d.requests
ids={q['case_id']:resolve(d,q['email'],q['audit_at']) for q in ALL}
res=assign_resources(d,own,ALL,ids)
out={r['case_id']:r for r in csv.DictReader(open(DATASET/'sample_output.csv'))}
conf=Counter(); fnd=Counter()
for q in samples:
    cid=q['case_id']
    sts=[resource_state(r,q['audit_at'],ix,d.evidence_files) for r in res[cid][0]]
    pred='INCOMPLETE' if any(not s.compliant for s in sts) else 'COMPLETE'
    exp=out[cid]['deletion_status']; conf[(exp,pred)]+=1
    expf={s['resource_id'] for s in json.loads(out[cid]['steps_json']) if s['phase']=='FINDING'}
    gotf={s.resource_id for s in sts if not s.compliant}
    fnd['tp']+=len(expf&gotf); fnd['fn']+=len(expf-gotf); fnd['fp']+=len(gotf-expf)
    if pred!=exp or expf!=gotf: print(cid,exp,pred,'missing',sorted(expf-gotf),'extra',sorted(gotf-expf))
print(dict(conf)); print(dict(fnd))
