'use client';
import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowLeft, Plus, Search } from 'lucide-react';

const stamp = value => new Date(value).toLocaleString('en-NG', {timeZone:'Africa/Lagos',dateStyle:'medium',timeStyle:'medium'});
const watNow = () => new Date(Date.now()+3600000).toISOString().slice(0,23);
const VITALS = [['temperature','Temperature (°C)',25,45,'0.1'],['pulse','Pulse (beats/min)',20,250,'1'],['respiratory_rate','Respiratory rate (breaths/min)',1,100,'1'],['oxygen_saturation','Oxygen saturation (%)',0,100,'1'],['systolic','Systolic BP (mmHg)',40,300,'1'],['diastolic','Diastolic BP (mmHg)',20,200,'1'],['pain_score','Pain score (0–10)',0,10,'1']];
const LABELS = {observation:'Observations',nursing_note:'Nursing notes',care_plan:'Care plans',ward_round:'Ward rounds',medication:'Medication record'};

export default function NursingWorkspace({api,user,Modal,notify,initialAdmission,consumeInitial}) {
  const apiRef=useRef(api);apiRef.current=api;
  const [admission,setAdmission]=useState(null);
  const [tab,setTab]=useState('observation');
  const [rows,setRows]=useState([]);
  const [count,setCount]=useState(0);
  const [query,setQuery]=useState('');
  const [state,setState]=useState('active');
  const [page,setPage]=useState(1);
  const [refresh,setRefresh]=useState(0);
  const [loading,setLoading]=useState(true);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const [mode,setMode]=useState(null);
  const [record,setRecord]=useState(null);
  const [prescriptions,setPrescriptions]=useState([]);
  const [prescriptionSearch,setPrescriptionSearch]=useState('');
  const [prescriptionId,setPrescriptionId]=useState('');
  const [outcome,setOutcome]=useState('');
  const [requestId,setRequestId]=useState('');
  const [entryTime,setEntryTime]=useState('');
  const canWrite=kind => (kind==='ward_round'?['administrator','doctor']:['administrator','nurse']).includes(user.role);

  useEffect(()=>{
    let cancelled=false;
    setLoading(true);
    const path=admission?`nursing/${admission.id}/${tab==='medication'?'medications/':`records/?kind=${tab}&`}`:`nursing/?q=${encodeURIComponent(query)}&state=${state}&`;
    const endpoint=admission&&tab==='medication'?`${path}?page=${page}`:`${path}page=${page}`;
    const timer=setTimeout(()=>apiRef.current(endpoint).then(data=>{if(!cancelled){setRows(data.results);setCount(data.count);setError('');}}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);}),180);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[admission?.id,tab,query,state,page,refresh]);

  useEffect(()=>{if(initialAdmission){openAdmission(initialAdmission);consumeInitial();}},[initialAdmission]);
  useEffect(()=>{
    if(mode!=='medication')return;
    let cancelled=false;
    const timer=setTimeout(()=>apiRef.current(`nursing/${admission.id}/prescriptions/?q=${encodeURIComponent(prescriptionSearch)}`).then(data=>{if(!cancelled)setPrescriptions(data.results);}).catch(e=>{if(!cancelled)setError(e.message);}),180);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[mode,prescriptionSearch]);

  async function openAdmission(id){
    setBusy(true);setError('');
    try{const data=await api(`nursing/${id}/`);setAdmission(data);setRows([]);setPage(1);setTab('observation');setLoading(true);}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  function changeTab(next){setRows([]);setLoading(true);setPage(1);setTab(next);setError('');}
  function close(){if(!busy){setMode(null);setRecord(null);setError('');}}
  function openNew(){setError('');setRecord(null);setEntryTime(watNow());setOutcome('');setPrescriptionId('');setPrescriptionSearch('');setPrescriptions([]);setRequestId(crypto.randomUUID());setMode(tab);}
  function addendum(row){setRecord(row);setError('');setMode('addendum');}
  async function save(event){
    event.preventDefault();setBusy(true);setError('');
    const data=Object.fromEntries(new FormData(event.currentTarget));
    if(data.review_confirmed)data.review_confirmed=true;
    for(const field of ['occurred_at','scheduled_at'])if(data[field])data[field]+='+01:00';
    let path;
    if(mode==='addendum')path=`nursing/${admission.id}/${tab==='medication'?'medications':'records'}/${record.id}/addenda/`;
    else if(mode==='medication'){path=`nursing/${admission.id}/medications/`;data.request_id=requestId;}
    else{path=`nursing/${admission.id}/records/`;data.kind=mode;}
    try{await api(path,{method:'POST',body:JSON.stringify(data)});setMode(null);setRecord(null);setPage(1);setRefresh(v=>v+1);notify('Signed inpatient record saved.');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const prescription=prescriptions.find(p=>String(p.id)===prescriptionId);
  return <section className="panel records-panel">
    <div className="records-toolbar"><div><h2>{admission?`${admission.patient_name} · ${admission.hospital_number}`:'Inpatient nursing care'}</h2><p>{admission?`${admission.ward} / ${admission.bed} · ${admission.discharged_at?'Discharged':'Admitted'} · ${admission.department}`:`${count} matching admissions`}</p></div><div className="consultation-tools">{admission?<><button className="secondary" onClick={()=>{setAdmission(null);setRows([]);setPage(1);setError('');}}><ArrowLeft size={16}/>Admissions</button>{!admission.discharged_at&&canWrite(tab)&&<button className="primary" disabled={busy} onClick={openNew}><Plus size={16}/>{({observation:'Record observation',nursing_note:'Add nursing note',care_plan:'Create care plan',ward_round:'Record ward round',medication:'Record medication'})[tab]}</button>}</>:<><div className="search-box"><Search size={17}/><input aria-label="Search nursing admissions" value={query} placeholder="Patient, hospital number, ward or bed" onChange={e=>{setQuery(e.target.value);setPage(1);}}/></div><select className="lab-status-filter" aria-label="Nursing admission status" value={state} onChange={e=>{setState(e.target.value);setPage(1);}}><option value="active">Active admissions</option><option value="discharged">Discharged</option><option value="all">All admissions</option></select></>}</div></div>
    {admission&&<><div className="tabs pharmacy-tabs">{Object.entries(LABELS).map(([key,label])=><button key={key} className={tab===key?'selected':''} onClick={()=>changeTab(key)}>{label}</button>)}</div><p className="panel-footnote">Admitted {stamp(admission.admitted_at)} WAT. {admission.discharged_at?'Discharged '+stamp(admission.discharged_at)+' WAT. Original records remain read-only.':'Event times use WAT; signing time and staff identity are recorded separately.'}</p></>}
    {error&&!mode&&<div className="alert error" role="alert">{error}<button onClick={()=>setRefresh(v=>v+1)}>Retry</button></div>}
    {loading?<div className="empty-state">Loading inpatient records…</div>:!rows.length?<div className="empty-state"><Activity size={30}/><h3>No records found</h3><p>{admission?'Recorded observations and signed care entries will appear here.':'Admit a sample patient through Admissions & wards to begin.'}</p></div>:!admission?<div className="table-scroll"><table><thead><tr><th>Patient</th><th>Ward / bed</th><th>Admitted (WAT)</th><th>Status</th><th>Care record</th></tr></thead><tbody>{rows.map(a=><tr key={a.id}><td><strong>{a.patient_name}</strong><small className="cell-sub">{a.hospital_number}</small></td><td>{a.ward} / {a.bed}</td><td>{stamp(a.admitted_at)}</td><td>{a.discharged_at?'Discharged':'Admitted'}</td><td><button className="table-action" disabled={busy} onClick={()=>openAdmission(a.id)}>Open care record</button></td></tr>)}</tbody></table></div>:<>
      {tab==='observation'&&<ObservationChart rows={rows}/>}
      <div className="care-timeline">{rows.map(r=><article className="care-entry" key={r.id}><div className="care-entry-heading"><strong>{tab==='medication'?`${r.medicine} · ${r.strength}`:LABELS[r.kind]}{r.addenda.length>0&&' · Addendum present'}</strong><span>{stamp(r.occurred_at)} WAT</span></div>
        {tab==='observation'?<dl className="vital-grid nursing-vitals">{VITALS.map(([key,label])=><div key={key}><dt>{label}</dt><dd>{r.vitals[key]??'Not recorded'}</dd></div>)}</dl>:tab==='medication'?<><p><strong>{r.outcome.replace('_',' ')}</strong> · Scheduled slot: {stamp(r.scheduled_at)} WAT<br/>Prescription #{r.prescription_id} · Route: {r.route}{r.outcome==='given'&&<><br/>Actual dose: {r.dose_given} · Quantity used: {r.quantity_used} {r.dispensing_unit}<br/>Dispensed batch: {r.batch_number}</>}</p>{r.reason&&<p>Reason / context: {r.reason}</p>}</>:<p>{r.content}</p>}
        {tab==='observation'&&r.content&&<p>{r.content}</p>}{tab==='care_plan'&&<><h3>Goals</h3><p>{r.goals}</p><h3>Interventions</h3><p>{r.interventions}</p><p>Review date: {r.review_date||'Not specified'}</p></>}
        <small>Signed by {r.recorded_by} · {stamp(r.recorded_at)} WAT</small>{r.addenda.map(a=><section className="clinical-addendum" key={a.id}><strong>Addendum · {a.recorded_by} · {stamp(a.recorded_at)} WAT</strong><p>{a.note}</p></section>)}{canWrite(tab)&&<button className="text-button" onClick={()=>addendum(r)}>Add dated correction</button>}</article>)}</div>
    </>}
    {count>20&&<div className="pagination"><span>Page {page} of {Math.ceil(count/20)}</span><button className="secondary" disabled={page===1} onClick={()=>setPage(v=>v-1)}>Previous</button><button className="secondary" disabled={page*20>=count} onClick={()=>setPage(v=>v+1)}>Next</button></div>}
    {mode&&<Modal title={mode==='addendum'?'Add inpatient addendum':mode==='medication'?'Record medication administration':LABELS[mode]} onClose={close}>
      <div className="form-note"><strong>{admission.patient_name} · {admission.hospital_number}<br/>{admission.ward} / {admission.bed}</strong></div>{error&&<div className="alert error" role="alert">{error}</div>}
      <form onSubmit={save}>{mode==='addendum'?<><p className="form-intro">Original records remain unchanged. A medication addendum does not reverse administration or return supplies; contact the clinical/pharmacy team to resolve discrepancies.</p><label>Correction / additional context *<textarea name="note" required maxLength={10000} rows={5}/></label></>:<>
        <label>Actual event time (WAT) *<input name="occurred_at" type="datetime-local" step="0.001" defaultValue={entryTime} required/></label>
        {mode==='observation'?<><p className="form-intro">Record measured values only. At least one value is required. These limits validate entries; they are not clinical reference ranges or an early-warning score.</p><div className="form-grid">{VITALS.map(([key,label,min,max,step])=><label key={key}>{label}<input type="number" name={key} min={min} max={max} step={step}/></label>)}</div><label>Observation context<textarea name="content" rows={2} maxLength={10000}/></label></>:mode==='medication'?<><label>Find prescribed medicine<input value={prescriptionSearch} onChange={e=>{setPrescriptionSearch(e.target.value);setPrescriptionId('');setOutcome('');}}/></label><label>Prescription *<select aria-label="Administration prescription *" name="prescription_id" required value={prescriptionId} onChange={e=>{setPrescriptionId(e.target.value);setOutcome('');}}><option value="" disabled>Select this patient's prescription</option>{prescriptions.map(p=><option key={p.id} value={p.id}>#{p.id} · {p.medicine} · {p.strength}</option>)}</select></label>
          {prescription&&<div className="form-note">Prescribed dose: {prescription.dose}<br/>Route: {prescription.route} · Frequency: {prescription.frequency} · Duration: {prescription.duration}<br/>Instructions: {prescription.instructions}<br/>Allergies at prescribing: {prescription.allergy_status==='known'?prescription.allergies:prescription.allergy_status==='none'?'No known allergies':'Not assessed / unknown'}<br/>Verify current allergies and that this order is appropriate for this admission. No automatic dose schedule or interaction check is performed.</div>}
          <label>Administration slot (WAT) *<input name="scheduled_at" type="datetime-local" step="0.001" defaultValue={entryTime} required/></label><p className="form-intro">Use the agreed dose time for this slot. A later given dose may follow a not-given entry for the same slot; a second given dose for that slot is blocked. Future events cannot be signed.</p><label>Outcome *<select aria-label="Administration outcome *" name="outcome" value={outcome} required onChange={e=>setOutcome(e.target.value)}><option value="" disabled>Select what happened</option><option value="given">Given</option><option value="not_given">Not given</option><option value="refused">Refused</option><option value="withheld">Withheld</option></select></label>
          {outcome==='given'&&<><label>Dispensed supply *<select aria-label="Administration supply *" name="dispense_id" defaultValue="" required><option value="" disabled>Select verified dispensed supply</option>{prescription?.dispenses.map(d=><option key={d.id} value={d.id}>#{d.id} · {d.batch_number} · Expiry {d.expiry_date} · Remaining {d.available} {prescription.dispensing_unit}</option>)}</select></label><label>Actual dose given *<input name="dose_given" required maxLength={200}/></label><label>Quantity used (dispensing units) *<input name="quantity_used" type="number" min="0.001" max="1000000" step="0.001" required/></label><p className="form-note">This uses the patient's dispensed supply. Pharmacy stock is not deducted again. No pack, strength or dose conversion is calculated.</p></>}
          <label>{outcome&&outcome!=='given'?'Reason not given *':'Context / reason'}<textarea name="reason" rows={3} maxLength={2000} required={Boolean(outcome&&outcome!=='given')}/></label>{!prescriptions.length&&<p className="form-note">No eligible prescription found. A doctor must sign a prescription first; given doses also need a matching pharmacy dispensing record. Search for medicines beyond the first 30 prescriptions.</p>}
        </>:<><label>{mode==='care_plan'?'Care plan summary *':mode==='ward_round'?'Ward-round assessment and plan *':'Nursing note *'}<textarea name="content" required maxLength={10000} rows={5}/></label>{mode==='care_plan'&&<><label>Care goals *<textarea name="goals" required rows={3} maxLength={5000}/></label><label>Planned interventions *<textarea name="interventions" required rows={3} maxLength={5000}/></label><label>Review date<input name="review_date" type="date"/></label><p className="form-note">The plan is a signed narrative; review and evaluation can be documented with addenda. This does not create automated tasks or reminders.</p></>}</>}
      </>}
      <label className="clinical-confirm"><input name="review_confirmed" type="checkbox" required/>{mode==='medication'?'I verified patient identity, current allergies, this admission, the current prescription, dose, route, timing, supplied medicine, expiry and actual outcome.':'I reviewed this clinical entry and confirm it is ready to sign.'}</label><div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Close</button><button className="primary" disabled={busy}>{busy?'Saving…':'Sign inpatient record'}</button></div>
      </form>
    </Modal>}
  </section>;
}

function ObservationChart({rows}){
  const [metric,setMetric]=useState('temperature');
  const points=rows.filter(r=>r.vitals[metric]!==null).map(r=>({time:new Date(r.occurred_at).getTime(),value:Number(r.vitals[metric])})).sort((a,b)=>a.time-b.time);
  const descriptor=VITALS.find(v=>v[0]===metric)[1];
  const low=points.length?Math.min(...points.map(p=>p.value))-1:0,high=points.length?Math.max(...points.map(p=>p.value))+1:1;
  const first=points[0]?.time??0,last=points.at(-1)?.time??1;
  const x=p=>40+(last===first?250:(p.time-first)/(last-first)*500),y=p=>120-(p.value-low)/(high-low)*95;
  return <section className="observation-chart"><div><h3>Measured observations</h3><select aria-label="Observation chart measurement" value={metric} onChange={e=>setMetric(e.target.value)}>{VITALS.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></div><p>Original measurements on this page, ordered by event time. Review addenda for corrections. Missing values are not plotted. No clinical thresholds or alerts are calculated.</p>{points.length?<svg viewBox="0 0 580 160" role="img" aria-label={descriptor+' chart'}><line x1="40" y1="125" x2="540" y2="125" stroke="#c8d9c5"/><polyline points={points.map(p=>`${x(p)},${y(p)}`).join(' ')} fill="none" stroke="#23775d" strokeWidth="2"/>{points.map((p,i)=><circle key={i} cx={x(p)} cy={y(p)} r="4" fill="#23775d"><title>{stamp(p.time)} WAT: {p.value}</title></circle>)}<text x="5" y="18">{high.toFixed(1)}</text><text x="5" y="125">{low.toFixed(1)}</text><text x="40" y="150">{stamp(first)}</text><text x="540" y="150" textAnchor="end">{stamp(last)}</text></svg>:<p>No recorded values for this measurement on this page.</p>}</section>;
}
