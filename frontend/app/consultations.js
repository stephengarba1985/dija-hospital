'use client';
import { useEffect, useRef, useState } from 'react';
import { Plus, Search, Stethoscope } from 'lucide-react';

const VITALS = [
  ['temperature', 'Temperature (°C)', 25, 45, '0.1'], ['pulse', 'Pulse (beats/min)', 20, 250, '1'],
  ['respiratory_rate', 'Respiratory rate (breaths/min)', 1, 100, '1'], ['oxygen_saturation', 'Oxygen saturation (%)', 0, 100, '1'],
  ['systolic', 'Systolic BP (mmHg)', 40, 300, '1'], ['diastolic', 'Diastolic BP (mmHg)', 20, 200, '1'],
  ['weight', 'Weight (kg)', 0.1, 500, '0.01'],
];
const TEXTS = [['symptoms', 'Symptoms & history', true], ['examination', 'Examination findings', false],
  ['diagnosis', 'Diagnosis / clinical assessment', true], ['treatment_plan', 'Treatment plan', true],
  ['follow_up_instructions', 'Follow-up instructions', false]];
const dateTime = v => new Date(v).toLocaleString('en-NG', { timeZone: 'Africa/Lagos', dateStyle: 'medium', timeStyle: 'short' });

export default function ConsultationWorkspace({ api, user, Modal, notify, onOpenLaboratory, onOpenPharmacy }) {
  const apiRef = useRef(api); apiRef.current = api;
  const [records, setRecords] = useState([]);
  const [count, setCount] = useState(0);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState(null);
  const [record, setRecord] = useState(null);
  const [appointments, setAppointments] = useState([]);
  const [allergyStatus, setAllergyStatus] = useState('unknown');
  const canSign = ['administrator', 'doctor'].includes(user.role);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      apiRef.current(`consultations/?q=${encodeURIComponent(search)}&page=${page}`).then(data => {
        if (!cancelled) { setRecords(data.results); setCount(data.count); setError(''); }
      }).catch(e => { if (!cancelled) setError(e.message); }).finally(() => { if (!cancelled) setLoading(false); });
    }, 180);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [search, page, revision]);

  async function openNew() {
    setBusy(true); setError('');
    try {
      const result = await api('appointments/?for_consultation=1');
      setAppointments(result.results); setAllergyStatus('unknown'); setMode('new');
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function view(id) {
    setBusy(true); setError('');
    try { setRecord(await api(`consultations/${id}/`)); setMode('view'); }
    catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    delete data.confirm;
    try {
      if (mode === 'new') {
        await api('consultations/', { method: 'POST', body: JSON.stringify(data) });
        setMode(null); setPage(1); setRevision(v=>v+1);
        notify('Consultation signed and appointment completed.');
      } else {
        await api(`consultations/${record.id}/addenda/`, { method: 'POST', body: JSON.stringify(data) });
        setRecord(await api(`consultations/${record.id}/`));
        setMode('view'); notify('Clinical addendum saved. Original notes preserved.');
      }
    } catch(e) { setError(e.message); } finally { setBusy(false); }
  }
  const close = () => { if (!busy) { setMode(null); setRecord(null); setError(''); } };
  return <section className="panel records-panel">
    <div className="records-toolbar"><div><h2>Consultation records</h2><p>{count} signed consultations · WAT</p></div><div className="consultation-tools"><div className="search-box"><Search size={17}/><input aria-label="Search consultation patients" placeholder="Patient name or hospital number" value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}}/></div>{canSign && <button className="primary" disabled={busy} onClick={openNew}><Plus size={16}/>New consultation</button>}</div></div>
    {error && !mode && <div className="alert error" role="alert">{error}<button onClick={()=>setRevision(v=>v+1)}>Retry</button></div>}
    {loading ? <div className="empty-state">Loading consultations…</div> : !records.length ? <div className="empty-state"><Stethoscope size={30}/><h3>No consultations found</h3><p>Check a patient in under Appointments, then record their consultation here.</p></div> : <div className="table-scroll"><table><thead><tr><th>Patient</th><th>Department</th><th>Clinician</th><th>Signed (WAT)</th><th>Record</th></tr></thead><tbody>{records.map(c=><tr key={c.id}><td><strong>{c.patient_name}</strong><small className="cell-sub">{c.hospital_number}</small></td><td>{c.department}</td><td>{c.clinician}</td><td>{dateTime(c.created_at)}</td><td><button className="table-action" disabled={busy} onClick={()=>view(c.id)}>View record</button></td></tr>)}</tbody></table></div>}
    {count>20 && <div className="pagination"><span>Page {page} of {Math.ceil(count/20)}</span><button className="secondary" disabled={page===1} onClick={()=>setPage(v=>v-1)}>Previous</button><button className="secondary" disabled={page*20>=count} onClick={()=>setPage(v=>v+1)}>Next</button></div>}
    {mode && <Modal title={mode==='new' ? 'New consultation' : mode==='addendum' ? 'Add clinical addendum' : 'Consultation record'} onClose={close}>
      {error && <div className="alert error" role="alert">{error}</div>}
      {mode==='view' ? <div className="clinical-record"><div className="form-note"><strong>{record.patient_name} · {record.hospital_number}</strong></div><p>{record.department}<br/>Signed by {record.clinician} · {dateTime(record.created_at)} WAT</p>
        <h3>Vital signs</h3><dl className="vital-grid">{VITALS.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{record.vitals[key] ?? 'Not recorded'}</dd></div>)}</dl>
        <h3>Allergies</h3><p>{record.allergy_status==='known' ? record.allergies : record.allergy_status==='none' ? 'No known allergies' : 'Not assessed / unknown'}</p>
        {TEXTS.map(([key,label])=><section key={key}><h3>{label}</h3><p>{record[key] || 'Not recorded'}</p></section>)}
        <h3>Follow-up date</h3><p>{record.follow_up_date || 'Not scheduled'} · This does not book an appointment.</p>
        <h3>Clinical addenda</h3>{!record.addenda.length && <p>No addenda.</p>}{record.addenda.map(a=><section className="clinical-addendum" key={a.id}><strong>{a.clinician} · {dateTime(a.created_at)} WAT</strong><p>{a.note}</p></section>)}
        <div className="form-actions lab-actions"><button className="secondary" onClick={close}>Close</button><button className="secondary" onClick={()=>onOpenLaboratory(record, false)}>View patient lab requests</button><button className="secondary" onClick={()=>onOpenPharmacy(record, false)}>View patient prescriptions</button>{canSign && <button className="primary" onClick={()=>onOpenPharmacy(record, true)}>Prescribe medicine</button>}{canSign && <button className="primary" onClick={()=>onOpenLaboratory(record, true)}>Request laboratory test</button>}{canSign && <button className="primary" onClick={()=>{setError('');setMode('addendum');}}>Add addendum</button>}</div>
      </div> : <form onSubmit={save}>
        {mode==='new' ? <><p className="form-intro">Sign a record for a checked-in appointment. Saving completes that appointment. These notes cannot be overwritten; use an addendum for corrections.</p>
          <label>Checked-in appointment *<select aria-label="Checked-in appointment *" name="appointment_id" defaultValue="" required><option value="" disabled>Select a checked-in patient</option>{appointments.map(a=><option value={a.id} key={a.id}>{a.patient_name} · {a.hospital_number} · {a.department} · {dateTime(a.scheduled_at)}</option>)}</select></label>
          {!appointments.length && <div className="form-note">No eligible appointments. Book an appointment and check the patient in first. The latest 100 eligible appointments are shown.</div>}
          <h3 className="clinical-section-title">Vital signs (optional)</h3><p className="form-intro">Enter measured observations only. Blank values mean not recorded. Validation limits check data entry; they are not clinical reference ranges.</p><div className="form-grid">{VITALS.map(([key,label,min,max,step])=><label key={key}>{label}<input name={key} type="number" min={min} max={max} step={step}/></label>)}</div>
          <label>Allergy status *<select aria-label="Allergy status *" name="allergy_status" value={allergyStatus} onChange={e=>setAllergyStatus(e.target.value)}><option value="unknown">Not assessed / unknown</option><option value="none">No known allergies</option><option value="known">Known allergies</option></select></label>
          {allergyStatus==='known' && <label>Allergies and reactions *<textarea name="allergies" required maxLength={2000} rows={3}/></label>}
          {TEXTS.map(([name,label,required])=><label key={name}>{label}{required ? ' *' : ''}<textarea name={name} required={required} maxLength={name==='diagnosis'||name==='follow_up_instructions'?5000:10000} rows={3}/></label>)}
          <label>Follow-up date<input name="follow_up_date" type="date" min={new Date().toLocaleDateString('en-CA',{timeZone:'Africa/Lagos'})}/></label><p className="form-note">Follow-up instructions do not automatically create an appointment. Treatment plans do not issue prescriptions or order tests.</p>
        </> : <><p className="form-intro">Add a correction or update for {record.patient_name}. The original signed record and earlier addenda remain unchanged.</p><label>Addendum *<textarea name="note" required maxLength={10000} rows={6}/></label></>}
        <label className="clinical-confirm"><input type="checkbox" name="confirm" required/>I have reviewed this entry and confirm it is ready to sign.</label>
        <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Cancel</button><button className="primary" disabled={busy || (mode==='new' && !appointments.length)}>{busy ? 'Saving…' : mode==='new' ? 'Sign & complete consultation' : 'Sign addendum'}</button></div>
      </form>}
    </Modal>}
  </section>;
}
