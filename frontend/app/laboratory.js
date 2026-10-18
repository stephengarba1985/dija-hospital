'use client';
import { useEffect, useRef, useState } from 'react';
import { FlaskConical, Plus, Search } from 'lucide-react';

const dateTime = v => v ? new Date(v).toLocaleString('en-NG', { timeZone: 'Africa/Lagos', dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';
const label = status => ({ requested: 'Requested', collected: 'Specimen collected', reported: 'Reported', cancelled: 'Cancelled' })[status];
const badge = status => ({ requested: 'scheduled', collected: 'checked_in', reported: 'completed', cancelled: 'cancelled' })[status];

export default function LaboratoryWorkspace({ api, user, Modal, notify, initialConsultation, consumeInitial }) {
  const apiRef = useRef(api); apiRef.current = api;
  const [records, setRecords] = useState([]);
  const [count, setCount] = useState(0);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState(null);
  const [record, setRecord] = useState(null);
  const [tests, setTests] = useState([]);
  const [consultations, setConsultations] = useState([]);
  const [lookup, setLookup] = useState('');
  const [fixedConsultation, setFixedConsultation] = useState(null);
  const [selectedConsultation, setSelectedConsultation] = useState('');
  const canOrder = ['administrator', 'doctor'].includes(user.role);
  const canReport = ['administrator', 'laboratory'].includes(user.role);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      apiRef.current(`laboratory/?q=${encodeURIComponent(query)}&status=${status}&page=${page}`).then(data => {
        if (!cancelled) { setRecords(data.results); setCount(data.count); setError(''); }
      }).catch(e => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setLoading(false); });
    }, 180);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [query, status, page, refresh]);

  useEffect(() => {
    if (mode !== 'new' || fixedConsultation) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      apiRef.current(`consultations/?q=${encodeURIComponent(lookup)}`).then(data => {
        if (!cancelled) setConsultations(data.results);
      }).catch(e => { if (!cancelled) setError(e.message); });
    }, 180);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [lookup, mode, fixedConsultation]);

  useEffect(() => {
    if (initialConsultation) {
      if (initialConsultation.openRequest && canOrder) openNew(initialConsultation);
      else { setQuery(initialConsultation.hospital_number); setStatus(''); setPage(1); }
      consumeInitial();
    }
  }, [initialConsultation]);

  async function openNew(consultation = null) {
    setBusy(true); setError('');
    try {
      const result = await api('laboratory/tests/');
      setTests(result.results); setLookup(''); setFixedConsultation(consultation);
      setConsultations(consultation ? [consultation] : []);
      setSelectedConsultation(consultation ? String(consultation.id) : ''); setMode('new');
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function view(id) {
    setBusy(true); setError('');
    try { setRecord(await api(`laboratory/${id}/`)); setMode('view'); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  function changeMode(next) { setError(''); setMode(next); }
  function close() { if (!busy) { setMode(null); setRecord(null); setError(''); } }
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    if (data.identity_verified) data.identity_verified = true;
    if (data.review_confirmed) data.review_confirmed = true;
    try {
      const endpoint = mode === 'new' ? 'laboratory/' : `laboratory/${record.id}/${mode === 'addendum' ? 'addenda' : mode}/`;
      await api(endpoint, { method: 'POST', body: JSON.stringify(data) });
      if (mode === 'new') { setMode(null); setPage(1); setStatus(''); setQuery(''); }
      else { setRecord(await api(`laboratory/${record.id}/`)); setMode('view'); }
      setRefresh(v=>v+1);
      notify(({ new: 'Laboratory test requested.', collect: 'Specimen collection recorded.', report: 'Laboratory report signed.', cancel: 'Laboratory request cancelled.', addendum: 'Report addendum signed. Original results preserved.' })[mode]);
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  const title = ({ new: 'Request laboratory test', view: 'Laboratory request & report', collect: 'Record specimen collection', report: 'Sign laboratory report', cancel: 'Cancel laboratory request', addendum: 'Add report addendum' })[mode];
  return <section className="panel records-panel">
    <div className="records-toolbar"><div><h2>Laboratory requests</h2><p>{count} matching requests · WAT</p></div><div className="consultation-tools"><div className="search-box"><Search size={17}/><input aria-label="Search laboratory requests" placeholder="Patient, hospital number or test" value={query} onChange={e=>{setQuery(e.target.value);setPage(1);}}/></div><select className="lab-status-filter" aria-label="Filter laboratory status" value={status} onChange={e=>{setStatus(e.target.value);setPage(1);}}><option value="">All statuses</option>{['requested','collected','reported','cancelled'].map(s=><option key={s} value={s}>{label(s)}</option>)}</select>{canOrder && <button className="primary" disabled={busy} onClick={()=>openNew()}><Plus size={16}/>Request test</button>}</div></div>
    {error && !mode && <div className="alert error" role="alert">{error}<button onClick={()=>setRefresh(v=>v+1)}>Retry</button></div>}
    {loading ? <div className="empty-state">Loading laboratory requests…</div> : !records.length ? <div className="empty-state"><FlaskConical size={30}/><h3>No laboratory requests found</h3><p>{canOrder ? 'Request a test from a signed consultation to begin.' : 'Requests from clinical staff will appear here.'}</p></div> : <div className="table-scroll"><table><thead><tr><th>Patient</th><th>Test</th><th>Priority</th><th>Status</th><th>Requested (WAT)</th><th>Request</th></tr></thead><tbody>{records.map(o=><tr key={o.id}><td><strong>{o.patient_name}</strong><small className="cell-sub">{o.hospital_number}</small></td><td>{o.test_name}<small className="cell-sub">LAB-{o.id} · {o.specimen_type}</small></td><td><span className={`lab-priority ${o.priority}`}>{o.priority}</span></td><td><span className={`badge ${badge(o.status)}`}>{label(o.status)}</span></td><td>{dateTime(o.created_at)}</td><td><button className="table-action" disabled={busy} onClick={()=>view(o.id)}>View request</button></td></tr>)}</tbody></table></div>}
    {count>20 && <div className="pagination"><span>Page {page} of {Math.ceil(count/20)}</span><button className="secondary" disabled={page===1} onClick={()=>setPage(v=>v-1)}>Previous</button><button className="secondary" disabled={page*20>=count} onClick={()=>setPage(v=>v+1)}>Next</button></div>}
    {mode && <Modal title={title} onClose={close}>
      {error && <div className="alert error" role="alert">{error}</div>}
      {record && <div className="form-note"><strong>{record.patient_name} · {record.hospital_number}<br/>{record.test_name} · LAB-{record.id}</strong></div>}
      {mode === 'view' ? <div className="clinical-record">
        <p><strong>{label(record.status)} · {record.priority}</strong><br/>Requested by {record.requested_by} · {dateTime(record.created_at)} WAT<br/>Consultation #{record.consultation_id}</p><h3>Clinical indication</h3><p>{record.indication}</p><h3>Specimen</h3><p>Required: {record.specimen_type}<br/>Label: {record.specimen_id || 'Not collected'}{record.collected_at && <><br/>Collection recorded by {record.collected_by} · {dateTime(record.collected_at)} WAT</>}</p>
        {record.status==='cancelled' && <><h3>Cancellation</h3><p>{record.cancellation_reason}<br/>By {record.cancelled_by} · {dateTime(record.cancelled_at)} WAT</p></>}
        {record.report ? <><h3>Signed results</h3><p>{record.report.result_text}</p><h3>Laboratory reference information</h3><p>{record.report.reference_info || 'Not supplied'}</p><h3>Report comments</h3><p>{record.report.comments || 'None'}</p><p>Signed by {record.report.signed_by} · {dateTime(record.report.signed_at)} WAT</p><h3>Report addenda</h3>{!record.report.addenda.length && <p>No addenda.</p>}{record.report.addenda.map(a=><section className="clinical-addendum" key={a.id}><strong>{a.signed_by} · {dateTime(a.signed_at)} WAT</strong><p>{a.note}</p></section>)}</> : record.status!=='cancelled' && <p>No signed result is available yet.</p>}
        <div className="form-actions lab-actions"><button className="secondary" onClick={close}>Close</button>{canOrder && record.status==='requested' && <button className="secondary" onClick={()=>changeMode('cancel')}>Cancel request</button>}{canReport && record.status==='requested' && <button className="primary" onClick={()=>changeMode('collect')}>Record collection</button>}{canReport && record.status==='collected' && <button className="primary" onClick={()=>changeMode('report')}>Enter results</button>}{canReport && record.status==='reported' && <button className="primary" onClick={()=>changeMode('addendum')}>Add report addendum</button>}</div>
      </div> : <form onSubmit={save}>
        {mode==='new' && <><p className="form-intro">One test per request. Requests are linked to signed consultations; they do not automatically generate invoices or send specimens to external laboratories.</p>{!fixedConsultation && <label>Find consultation patient<input aria-label="Find consultation patient" value={lookup} onChange={e=>{setLookup(e.target.value);setSelectedConsultation('');}} placeholder="Search name or hospital number"/></label>}<label>Signed consultation *<select aria-label="Signed consultation *" name="consultation_id" required value={selectedConsultation} onChange={e=>setSelectedConsultation(e.target.value)}><option value="" disabled>Select a signed consultation</option>{consultations.map(c=><option key={c.id} value={c.id}>{c.patient_name} · {c.hospital_number} · Consultation #{c.id} · {dateTime(c.created_at)}</option>)}</select></label>{!consultations.length && <p className="form-note">No matching consultations. Complete and sign a consultation first. Search to find older patients.</p>}<label>Laboratory test *<select aria-label="Laboratory test *" name="lab_test_id" required defaultValue=""><option value="" disabled>Select an active test</option>{tests.map(t=><option key={t.id} value={t.id}>{t.name} · {t.specimen_type}</option>)}</select></label>{!tests.length && <p className="form-note">No active tests. An administrator can configure the branch’s laboratory test catalogue.</p>}<label>Priority<select aria-label="Priority" name="priority" defaultValue="routine"><option value="routine">Routine</option><option value="urgent">Urgent</option></select></label><label>Clinical indication *<textarea name="indication" required rows={3} maxLength={2000}/></label></>}
        {mode==='collect' && <><p className="form-intro">Confirm the patient and specimen label before recording collection. This records collection now, not a backdated collection time.</p><label>Specimen label / identifier *<input name="specimen_id" required maxLength={100}/></label><label className="clinical-confirm"><input name="identity_verified" type="checkbox" required/>I have verified the patient identity, required specimen and specimen label.</label></>}
        {mode==='report' && <><p className="form-intro">Enter verified laboratory observations only. No results, reference ranges or diagnoses are generated automatically. Signed reports cannot be overwritten; use a dated addendum for corrections.</p><label>Results (include values and units) *<textarea name="result_text" required rows={6} maxLength={10000}/></label><label>Laboratory reference information<textarea name="reference_info" rows={3} maxLength={3000}/></label><label>Report comments<textarea name="comments" rows={3} maxLength={5000}/></label></>}
        {mode==='cancel' && <><p className="form-intro">Cancel this uncollected request? The request and reason remain in the record.</p><label>Cancellation reason *<textarea name="cancellation_reason" required rows={3} maxLength={2000}/></label></>}
        {mode==='addendum' && <><p className="form-intro">Record a correction or additional context. The original signed report remains unchanged.</p><label>Report addendum *<textarea name="note" required rows={5} maxLength={10000}/></label></>}
        {['report','addendum'].includes(mode) && <label className="clinical-confirm"><input type="checkbox" name="review_confirmed" required/>I have reviewed the patient, specimen and results and confirm this entry is ready to sign.</label>}
        <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Close</button><button className="primary" disabled={busy || (mode==='new' && !tests.length)}>{busy ? 'Saving…' : ({new:'Submit test request',collect:'Confirm collection',report:'Sign laboratory report',cancel:'Confirm cancellation',addendum:'Sign report addendum'})[mode]}</button></div>
      </form>}
    </Modal>}
  </section>;
}
