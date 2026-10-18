'use client';
import { useEffect, useRef, useState } from 'react';
import { Pill, Plus, Search } from 'lucide-react';

const dateTime = value => value ? new Date(value).toLocaleString('en-NG', { timeZone: 'Africa/Lagos', dateStyle: 'medium', timeStyle: 'short' }) : 'Not recorded';
const statusLabel = value => ({ active:'Active', completed:'Dispensed', cancelled:'Cancelled' })[value];
const medicineLabel = m => `${m.name} · ${m.strength} · ${m.form} · ${m.dispensing_unit}`;
const tomorrow = () => {
  const day = new Date(Date.now()+86400000);
  return day.toLocaleDateString('en-CA', { timeZone:'Africa/Lagos' });
};

export default function PharmacyWorkspace({ api, user, Modal, notify, initialConsultation, consumeInitial }) {
  const apiRef = useRef(api); apiRef.current = api;
  const [tab, setTab] = useState('prescriptions');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [count, setCount] = useState(0);
  const [rows, setRows] = useState([]);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState(null);
  const [record, setRecord] = useState(null);
  const [medicines, setMedicines] = useState([]);
  const [batches, setBatches] = useState([]);
  const [consultations, setConsultations] = useState([]);
  const [consultationSearch, setConsultationSearch] = useState('');
  const [medicineSearch, setMedicineSearch] = useState('');
  const [consultationId, setConsultationId] = useState('');
  const [consultationInfo, setConsultationInfo] = useState(null);
  const [fixedConsultation, setFixedConsultation] = useState(null);
  const [requestId, setRequestId] = useState('');
  const canPrescribe = ['administrator','doctor'].includes(user.role);
  const canDispense = ['administrator','pharmacist'].includes(user.role);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const path = ({ prescriptions:'pharmacy/', medicines:'pharmacy/medicines/', batches:'pharmacy/batches/', movements:'pharmacy/movements/' })[tab];
    const timer = setTimeout(() => {
      apiRef.current(`${path}?q=${encodeURIComponent(query)}&page=${page}`).then(data => {
        if (!cancelled) { setRows(data.results);setCount(data.count);setError(''); }
      }).catch(e=>{ if(!cancelled)setError(e.message); }).finally(()=>{if(!cancelled)setLoading(false);});
    }, 180);
    return ()=>{cancelled=true;clearTimeout(timer);};
  }, [tab,query,page,refresh]);

  useEffect(()=>{
    if(mode!=='new' || fixedConsultation)return;
    let cancelled=false;
    const timer=setTimeout(()=>{
      apiRef.current(`consultations/?q=${encodeURIComponent(consultationSearch)}`).then(data=>{if(!cancelled)setConsultations(data.results);}).catch(e=>{if(!cancelled)setError(e.message);});
    },180);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[mode,consultationSearch,fixedConsultation]);

  useEffect(()=>{
    if(!['new','receive'].includes(mode))return;
    let cancelled=false;
    const timer=setTimeout(()=>{
      apiRef.current(`pharmacy/medicines/?active=1&q=${encodeURIComponent(medicineSearch)}`).then(data=>{if(!cancelled)setMedicines(data.results);}).catch(e=>{if(!cancelled)setError(e.message);});
    },180);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[mode,medicineSearch]);

  useEffect(()=>{
    if(mode!=='new' || !consultationId)return;
    let cancelled=false;
    setConsultationInfo(null);
    apiRef.current(`consultations/${consultationId}/`).then(data=>{if(!cancelled)setConsultationInfo(data);}).catch(e=>{if(!cancelled)setError(e.message);});
    return ()=>{cancelled=true;};
  },[consultationId,mode]);

  useEffect(()=>{
    if(initialConsultation){
      if(initialConsultation.openRequest && canPrescribe)openNew(initialConsultation);
      else{setQuery(initialConsultation.hospital_number);setPage(1);setTab('prescriptions');}
      consumeInitial();
    }
  },[initialConsultation]);

  function changeTab(next){setRows([]);setLoading(true);setTab(next);setPage(1);setQuery('');setError('');}
  function close(){if(!busy){setMode(null);setRecord(null);setConsultationInfo(null);setError('');}}
  function openNew(consultation=null){
    setRecord(null);setError('');setConsultationSearch('');setMedicineSearch('');setMedicines([]);
    setFixedConsultation(consultation);setConsultations(consultation?[consultation]:[]);
    setConsultationInfo(null);setConsultationId(consultation?String(consultation.id):'');setMode('new');
  }
  function openSimple(next,row=null){setRecord(row);setError('');setMedicineSearch('');setMedicines([]);setRequestId(crypto.randomUUID());setMode(next);}
  async function view(id){
    setBusy(true);setError('');
    try{setRecord(await api(`pharmacy/${id}/`));setMode('view');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function openDispense(){
    setBusy(true);setError('');
    try{const result=await api(`pharmacy/batches/?medicine=${record.medicine_id}&available=1`);setBatches(result.results);setRequestId(crypto.randomUUID());setMode('dispense');}
    catch(e){setError(e.message);}finally{setBusy(false);}
  }
  async function save(event){
    event.preventDefault();setBusy(true);setError('');
    const data=Object.fromEntries(new FormData(event.currentTarget));
    if(data.review_confirmed)data.review_confirmed=true;
    if(['dispense','write_off'].includes(mode))data.request_id=requestId;
    const path=({new:'pharmacy/',medicine:'pharmacy/medicines/',receive:'pharmacy/receive/',
      dispense:`pharmacy/${record?.id}/dispense/`,cancel:`pharmacy/${record?.id}/cancel/`,
      write_off:`pharmacy/batches/${record?.id}/write-off/`})[mode];
    try{
      await api(path,{method:'POST',body:JSON.stringify(data)});
      if(['dispense','cancel'].includes(mode)){setRecord(await api(`pharmacy/${record.id}/`));setMode('view');}
      else{setMode(null);setRecord(null);setPage(1);setQuery('');setTab(mode==='new'?'prescriptions':mode==='medicine'?'medicines':'batches');}
      setRefresh(v=>v+1);
      notify(({new:'Prescription signed.',medicine:'Medicine added to catalogue.',receive:'Stock receipt recorded.',dispense:'Dispensing recorded and stock updated.',cancel:'Unfilled prescription quantity cancelled.',write_off:'Stock write-off recorded.'})[mode]);
    }catch(e){setError(e.message);}finally{setBusy(false);}
  }
  const tabs=[['prescriptions','Prescriptions'],['medicines','Medicines'],...(canDispense?[['batches','Stock batches'],['movements','Stock history']]:[])];
  const pageSize=tab==='prescriptions'?20:30;
  const allergy=record?.allergy_status==='known'?record.allergies:record?.allergy_status==='none'?'No known allergies':'Not assessed / unknown';
  return <section className="panel records-panel">
    <div className="records-toolbar"><div><h2>Prescriptions & pharmacy</h2><p>{count} matching records · WAT</p></div><div className="consultation-tools">{['prescriptions','medicines'].includes(tab)&&<div className="search-box"><Search size={17}/><input aria-label="Search pharmacy records" value={query} placeholder={tab==='medicines'?'Medicine name, code or strength':'Patient, hospital number or medicine'} onChange={e=>{setQuery(e.target.value);setPage(1);}}/></div>}{canPrescribe&&<button className="primary" disabled={busy} onClick={()=>openNew()}><Plus size={16}/>New prescription</button>}{canDispense&&<><button className="secondary" disabled={busy} onClick={()=>openSimple('medicine')}>Add medicine</button><button className="secondary" disabled={busy} onClick={()=>openSimple('receive')}>Receive stock</button></>}</div></div>
    <div className="tabs pharmacy-tabs">{tabs.map(([key,name])=><button key={key} className={tab===key?'selected':''} onClick={()=>changeTab(key)}>{name}</button>)}</div>
    {error&&!mode&&<div className="alert error" role="alert">{error}<button onClick={()=>setRefresh(v=>v+1)}>Retry</button></div>}
    {loading?<div className="empty-state">Loading pharmacy records…</div>:!rows.length?<div className="empty-state"><Pill size={30}/><h3>No records found</h3><p>{tab==='prescriptions'?'Prescribe a medicine from a signed consultation.':'Pharmacy staff can add medicines and receive stock. No medicines or quantities are seeded automatically.'}</p></div>:<div className="table-scroll"><table>
      {tab==='prescriptions'&&<><thead><tr><th>Patient</th><th>Medicine</th><th>Quantity</th><th>Status</th><th>Prescribed (WAT)</th><th>Record</th></tr></thead><tbody>{rows.map(r=><tr key={r.id}><td><strong>{r.patient_name}</strong><small className="cell-sub">{r.hospital_number}</small></td><td>{r.medicine_name}<small className="cell-sub">{r.strength} · {r.form}</small></td><td>{r.dispensed_quantity} / {r.quantity} {r.dispensing_unit}<small className="cell-sub">Dispensed / prescribed</small></td><td><span className={`badge ${r.status==='active'?'scheduled':r.status}`}>{statusLabel(r.status)}</span></td><td>{dateTime(r.created_at)}</td><td><button className="table-action" disabled={busy} onClick={()=>view(r.id)}>View prescription</button></td></tr>)}</tbody></>}
      {tab==='medicines'&&<><thead><tr><th>Medicine</th><th>Code</th><th>Form / unit</th><th>Available stock</th><th>Status</th></tr></thead><tbody>{rows.map(m=><tr key={m.id}><td><strong>{m.name}</strong><small className="cell-sub">{m.strength}</small></td><td>{m.code}</td><td>{m.form} / {m.dispensing_unit}</td><td>{m.available} {m.dispensing_unit}{m.low_stock&&<small className="cell-sub stock-warning">Low stock</small>}</td><td>{m.active?'Active':'Inactive'}</td></tr>)}</tbody></>}
      {tab==='batches'&&<><thead><tr><th>Medicine</th><th>Batch</th><th>Expiry date</th><th>Balance / received</th><th>Action</th></tr></thead><tbody>{rows.map(b=><tr key={b.id}><td>{b.medicine_name}<small className="cell-sub">{b.strength}</small></td><td>{b.batch_number}</td><td>{b.expiry_date}{b.expired&&<small className="cell-sub stock-warning">Blocked: expires today or earlier</small>}</td><td>{b.quantity_remaining} / {b.quantity_received} {b.dispensing_unit}</td><td>{b.quantity_remaining>0&&<button className="table-action danger" disabled={busy} onClick={()=>openSimple('write_off',b)}>Write off</button>}</td></tr>)}</tbody></>}
      {tab==='movements'&&<><thead><tr><th>Medicine / batch</th><th>Movement</th><th>Change</th><th>Batch balance after</th><th>Reference / reason</th><th>Staff / WAT</th></tr></thead><tbody>{rows.map(m=><tr key={m.id}><td>{m.medicine_name}<small className="cell-sub">{m.batch_number}</small></td><td>{m.kind.replace('_',' ')}</td><td>{m.quantity>0?'+':''}{m.quantity}</td><td>{m.balance_after}</td><td>{m.reference||m.note||`Prescription #${m.prescription_id}`}</td><td>{m.actor}<small className="cell-sub">{dateTime(m.created_at)}</small></td></tr>)}</tbody></>}
    </table></div>}
    {count>pageSize&&<div className="pagination"><span>Page {page} of {Math.ceil(count/pageSize)}</span><button className="secondary" disabled={page===1} onClick={()=>setPage(v=>v-1)}>Previous</button><button className="secondary" disabled={page*pageSize>=count} onClick={()=>setPage(v=>v+1)}>Next</button></div>}
    {mode&&<Modal title={({new:'New prescription',view:'Prescription record',medicine:'Add medicine',receive:'Receive stock',dispense:'Dispense medicine',cancel:'Cancel unfilled quantity',write_off:'Write off stock'})[mode]} onClose={close}>
      {error&&<div className="alert error" role="alert">{error}</div>}
      {['view','dispense','cancel'].includes(mode)&&<div className="form-note"><strong>{record.patient_name} · {record.hospital_number}<br/>{record.medicine_name} · {record.strength} · {record.form}</strong></div>}
      {mode==='view'?<div className="clinical-record"><p>Prescription #{record.id} · Consultation #{record.consultation_id}<br/>Signed by {record.prescribed_by} · {dateTime(record.created_at)} WAT<br/><span className={`badge ${record.status==='active'?'scheduled':record.status}`}>{statusLabel(record.status)}</span></p><h3>Instructions</h3><dl className="vital-grid">{[['Dose',record.dose],['Route',record.route],['Frequency',record.frequency],['Duration',record.duration],['Total prescribed',`${record.quantity} ${record.dispensing_unit}`],['Unfilled quantity',`${record.unfilled_quantity} ${record.dispensing_unit}`]].map(([key,value])=><div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}</dl><p>{record.instructions}</p><h3>Allergy record at prescribing</h3><p className={record.allergy_status!=='none'?'stock-warning':''}>{allergy}</p><p>Verify current allergy information with the patient and clinical team before dispensing. No automated allergy or interaction check is performed.</p><h3>Dispensing history</h3>{!record.dispenses.length&&<p>Not dispensed.</p>}{record.dispenses.map(d=><section className="clinical-addendum" key={d.id}><strong>{d.quantity} {record.dispensing_unit} · Batch {d.batch_number} · Expiry {d.expiry_date}</strong><p>{d.pharmacist} · {dateTime(d.created_at)} WAT</p></section>)}{record.status==='cancelled'&&<><h3>Cancellation</h3><p>{record.cancellation_reason}<br/>{record.cancelled_by} · {dateTime(record.cancelled_at)} WAT</p><p>Earlier dispensing remains recorded; cancellation does not return medicine to stock.</p></>}<div className="form-actions lab-actions"><button className="secondary" onClick={close}>Close</button>{record.status==='active'&&canPrescribe&&<button className="secondary" onClick={()=>{setError('');setMode('cancel');}}>Cancel unfilled quantity</button>}{record.status==='active'&&canDispense&&<button className="primary" disabled={busy} onClick={openDispense}>Dispense medicine</button>}</div></div>:<form onSubmit={save}>
        {mode==='new'&&<><p className="form-intro">One medicine per prescription. Enter the prescribed dose, route, schedule and total quantity yourself. No dose, interaction or treatment recommendation is generated.</p>{!fixedConsultation&&<label>Find consultation patient<input value={consultationSearch} onChange={e=>{setConsultationSearch(e.target.value);setConsultationId('');setConsultationInfo(null);}}/></label>}<label>Signed consultation *<select aria-label="Prescription consultation *" name="consultation_id" required value={consultationId} onChange={e=>setConsultationId(e.target.value)}><option value="" disabled>Select a signed consultation</option>{consultations.map(c=><option key={c.id} value={c.id}>{c.patient_name} · {c.hospital_number} · Consultation #{c.id}</option>)}</select></label>{consultationInfo&&<div className="form-note">Allergies at this consultation: {consultationInfo.allergy_status==='known'?consultationInfo.allergies:consultationInfo.allergy_status==='none'?'No known allergies':'Not assessed / unknown'}. Verify current allergies before prescribing.</div>}{medicineSelector()}<div className="form-grid">{[['dose','Dose *'],['route','Route *'],['frequency','Frequency *'],['duration','Duration *']].map(([key,label])=><label key={key}>{label}<input name={key} required maxLength={key==='route'?100:200}/></label>)}<label>Total quantity (dispensing units) *<input name="quantity" type="number" min="1" max="1000000" step="1" required/></label></div><label>Patient instructions *<textarea name="instructions" required maxLength={5000} rows={3}/></label><label className="clinical-confirm"><input name="review_confirmed" type="checkbox" required/>I have reviewed the patient, current allergies, medicine, dose, route, frequency, duration and quantity and confirm this prescription is ready to sign.</label></>}
        {mode==='medicine'&&<><p className="form-intro">Use a separate catalogue entry for each medicine, strength and formulation. Stock is recorded in the smallest dispensing unit. No opening stock is created automatically.</p><div className="form-grid">{[['code','Medicine code *',40],['name','Medicine name *',160],['strength','Strength *',80],['form','Formulation *',80],['dispensing_unit','Dispensing unit *',30]].map(([key,label,max])=><label key={key}>{label}<input name={key} required maxLength={max} pattern={key==='code'?'[A-Za-z0-9_-]+':undefined}/></label>)}<label>Low-stock threshold *<input name="low_stock_threshold" type="number" min="0" max="1000000" step="1" required defaultValue="0"/></label></div></>}
        {mode==='receive'&&<><p className="form-intro">Use the exact batch label and expiry date. For month-only expiry labels, follow your approved pharmacy procedure to determine the date. Each receipt reference must be unique for this stock entry.</p>{medicineSelector()}<div className="form-grid"><label>Batch number *<input name="batch_number" required maxLength={100}/></label><label>Expiry date *<input name="expiry_date" type="date" min={tomorrow()} required/></label><label>Quantity received *<input name="quantity" type="number" min="1" max="1000000" step="1" required/></label><label>Receipt reference *<input name="reference" required maxLength={100}/></label></div><label>Receipt note<textarea name="note" maxLength={500} rows={2}/></label></>}
        {mode==='dispense'&&<><div className="form-note">Dose: {record.dose} · Route: {record.route}<br/>Frequency: {record.frequency} · Duration: {record.duration}<br/>Allergies at prescribing: {allergy}<br/>Unfilled: {record.unfilled_quantity} {record.dispensing_unit}</div><p className="form-intro">Verify current allergies and the prescription. Expired or expiring-today batches are blocked. Batches are listed earliest expiry first. For split batches, record each dispensing separately.</p><label>Stock batch *<select aria-label="Dispensing batch *" name="batch_id" required defaultValue=""><option value="" disabled>Select an available batch</option>{batches.map(b=><option key={b.id} value={b.id}>{b.batch_number} · Expiry {b.expiry_date} · {b.quantity_remaining} {b.dispensing_unit}</option>)}</select></label>{!batches.length&&<p className="form-note">No eligible batches. Receive verified stock first. Only the earliest 30 eligible batches are shown.</p>}<label>Quantity to dispense *<input name="quantity" type="number" min="1" max={record.unfilled_quantity} step="1" required/></label><label className="clinical-confirm"><input type="checkbox" name="review_confirmed" required/>I have checked patient identity, current allergies, prescription, medicine, strength, batch label, expiry and instructions before dispensing.</label></>}
        {mode==='cancel'&&<><p className="form-intro">This stops further dispensing of the unfilled quantity. Previous prescriptions and dispensing events remain unchanged. To correct a prescription, cancel its unfilled quantity and issue a new prescription.</p><label>Cancellation reason *<textarea name="reason" required maxLength={2000} rows={3}/></label></>}
        {mode==='write_off'&&<><p className="form-intro">Remove unusable stock from {record.medicine_name}, batch {record.batch_number}. This records a permanent stock movement. Available balance: {record.quantity_remaining} {record.dispensing_unit}.</p><label>Quantity to remove *<input name="quantity" type="number" min="1" max={record.quantity_remaining} step="1" required/></label><label>Write-off reason *<textarea name="reason" required maxLength={500} rows={3}/></label></>}
        <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>Close</button><button className="primary" disabled={busy||(mode==='new'&&!consultationInfo)||(mode==='dispense'&&!batches.length)}>{busy?'Saving…':({new:'Sign prescription',medicine:'Save medicine',receive:'Record stock receipt',dispense:'Confirm dispensing',cancel:'Confirm cancellation',write_off:'Confirm write-off'})[mode]}</button></div>
      </form>}
    </Modal>}
  </section>;

  function medicineSelector(){return <><label>Find medicine<input aria-label="Find medicine" value={medicineSearch} onChange={e=>setMedicineSearch(e.target.value)} placeholder="Search name, code or strength"/></label><label>Medicine *<select aria-label="Prescription or stock medicine *" name="medicine_id" required defaultValue=""><option value="" disabled>Select an active medicine</option>{medicines.map(m=><option key={m.id} value={m.id}>{medicineLabel(m)}</option>)}</select></label>{!medicines.length&&<p className="form-note">No active medicines found. Pharmacy staff must add the approved medicine catalogue first. Search to find entries beyond the first 30.</p>}</>;}
}
