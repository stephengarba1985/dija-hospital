'use client';

import ConsultationWorkspace from './consultations';
import LaboratoryWorkspace from './laboratory';
import { useEffect, useRef, useState } from 'react';
import { Activity, ArrowDownLeft, ArrowRight, ArrowUpRight, BedDouble, Building2, CalendarDays, Check, ChevronDown, ChevronLeft, ChevronRight, CircleHelp, ClipboardList, CreditCard, Cross, FlaskConical, HeartPulse, LayoutDashboard, LogOut, Menu, Plus, Search, ShieldCheck, Stethoscope, Users, X } from 'lucide-react';

const NAV = [
  ['dashboard', 'Overview', LayoutDashboard], ['patients', 'Patients', Users],
  ['appointments', 'Appointments', CalendarDays], ['consultations', 'Consultations', Stethoscope], ['admissions', 'Admissions & wards', BedDouble],
  ['laboratory', 'Laboratory', FlaskConical], ['departments', 'Departments', Building2], ['invoices', 'Billing & payments', CreditCard],
];
const CATEGORIES = { clinical: 'Clinical care', diagnostics: 'Diagnostics & treatment', operations: 'Hospital operations', administration: 'Administration' };
const money = v => new Intl.NumberFormat('en-NG', { style: 'currency', currency: 'NGN', maximumFractionDigits: 2 }).format(Number(v));
const dateLabel = v => new Date(v).toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Lagos' });
const timeLabel = v => new Date(v).toLocaleTimeString('en-NG', { hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Lagos' });
const initials = v => v.split(' ').filter(Boolean).slice(0, 2).map(s => s[0]).join('').toUpperCase();
const human = s => s?.replaceAll('_', ' ');

export default function HospitalApp() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState('dashboard');
  const [dashboard, setDashboard] = useState(null);
  const [departments, setDepartments] = useState([]);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState(null);
  const [patientOptions, setPatientOptions] = useState([]);
  const [labContext, setLabContext] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [listLoading, setListLoading] = useState(false);
  const requestId = useRef(0);

  async function api(path, options = {}, csrf = session?.csrfToken) {
    const response = await fetch(`/api/${path}`, {
      cache: 'no-store', ...options,
      headers: { 'Content-Type': 'application/json', ...(csrf ? { 'X-CSRFToken': csrf } : {}), ...options.headers },
    });
    const data = await response.json().catch(() => ({ error: 'The service could not process this request.' }));
    if (response.status === 401 && path !== 'login/') setSession(current => ({ ...current, user: null }));
    if (!response.ok) throw new Error(data.error || 'Unable to complete the request.');
    return data;
  }

  useEffect(() => {
    fetch('/api/session/', { cache: 'no-store' }).then(r => {
      if (!r.ok) throw new Error('The hospital service is unavailable. Please try again.');
      return r.json();
    }).then(setSession).catch(e => setError(e.message)).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!session?.user) return;
    api('departments/').then(data => setDepartments(data.results)).catch(e => setError(e.message));
  }, [session?.user?.username]);

  useEffect(() => {
    if (!session?.user) return;
    const id = ++requestId.current;
    setError('');
    setListLoading(true);
    setRows([]);
    const timer = setTimeout(async () => {
      try {
        if (page === 'dashboard') {
          const data = await api('dashboard/');
          if (id === requestId.current) setDashboard(data);
        } else if (!['departments', 'consultations', 'laboratory'].includes(page)) {
          const data = await api(`${page}/?q=${encodeURIComponent(query)}&page=${pageNumber}`);
          if (id === requestId.current) { setRows(data.results); setTotal(data.count ?? data.results.length); }
        }
      } catch (e) { if (id === requestId.current) setError(e.message); }
      finally { if (id === requestId.current) setListLoading(false); }
    }, 180);
    return () => { clearTimeout(timer); requestId.current++; };
  }, [session?.user?.username, page, query, pageNumber, refresh]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  function navigate(next) { setRows([]); setTotal(0); setListLoading(true); setPage(next); setQuery(''); setPageNumber(1); setError(''); setMobileOpen(false); }

  async function signIn(event) {
    event.preventDefault(); setBusy(true); setError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    event.currentTarget.elements.password.value = '';
    try {
      let csrf = session?.csrfToken;
      if (!csrf) { const current = await api('session/'); csrf = current.csrfToken; }
      const result = await api('login/', { method: 'POST', body: JSON.stringify(data) }, csrf);
      setSession(result); setPage('dashboard');
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function signOut() {
    try { await api('logout/', { method: 'POST' }); setSession(await api('session/')); setDashboard(null); setRows([]); }
    catch (e) { setError(e.message); }
  }

  async function openDialog(type) {
    setError('');
    if (type !== 'patients') {
      try { const result = await api('patient-options/'); setPatientOptions(result.results); }
      catch (e) { setError(e.message); return; }
    }
    setDialog(type);
  }

  async function findPatients(value) {
    try { const result = await api(`patient-options/?q=${encodeURIComponent(value)}`); setPatientOptions(result.results); }
    catch (e) { setError(e.message); }
  }

  async function submitRecord(event) {
    event.preventDefault(); setBusy(true); setError('');
    const data = Object.fromEntries(new FormData(event.currentTarget));
    delete data.patient_search;
    // datetime-local represents Nigerian local time, regardless of the operator's device timezone.
    if (data.scheduled_at) data.scheduled_at += ':00+01:00';
    try {
      await api(`${dialog}/`, { method: 'POST', body: JSON.stringify(data) });
      const target = dialog;
      setDialog(null); navigate(target); setRefresh(v => v + 1);
      setNotice({ patients: 'Patient registered successfully.', appointments: 'Appointment booked successfully.', admissions: 'Patient admitted successfully.', invoices: 'Invoice created successfully.' }[target]);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function updateRecord(resource, id, status) {
    setBusy(true); setError('');
    try { await api(`${resource}/${id}/`, { method: 'PATCH', body: JSON.stringify({ status }) }); setRefresh(v => v + 1); setNotice('Record updated successfully.'); return true; }
    catch (e) { setError(e.message); return false; } finally { setBusy(false); }
  }

  if (loading) return <div className="loading-screen"><div className="brand-mark"><Cross size={28} /></div><p>Opening Dija Hospital…</p></div>;

  if (!session?.user) return <main className="login-layout">
    <section className="login-story">
      <div className="brand"><span className="brand-mark"><Cross /></span><div>Dija Hospital<small>HOSPITAL MANAGEMENT</small></div></div>
      <div className="login-message"><span className="eyebrow light">CONNECTED CARE. EVERY DEPARTMENT.</span><h1>More time for<br />what matters.<span>Your patients.</span></h1><p>One connected workspace for the people who make Dija Hospital work.</p>
      <div className="care-orbit"><div className="orbit-line"/><div className="orbit-heart"><HeartPulse size={70} strokeWidth={1.2}/></div><span className="orbit-label one"><Users size={17}/> Patient care</span><span className="orbit-label two"><ShieldCheck size={17}/> Staff access</span><span className="orbit-label three"><Building2 size={17}/> Every department</span></div></div>
      <span className="login-footer">Built for Nigeria. Ready to grow with you.</span>
    </section>
    <section className="login-panel"><div className="login-form"><span className="eyebrow">WELCOME TO DIJA HOSPITAL</span><h2>Good care starts here.</h2><p>Sign in to your hospital workspace.</p>
      {error && <div className="alert error" role="alert">{error}</div>}
      <form onSubmit={signIn}><label>Username<input name="username" autoComplete="username" required placeholder="Your staff username" /></label><label>Password<input name="password" type="password" autoComplete="current-password" required placeholder="Enter your password" /></label><button className="primary full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in to workspace'}<ArrowRight size={18}/></button></form>
      <p className="login-help">Need access? Contact your hospital administrator.</p><div className="privacy-note"><ShieldCheck size={19}/><span>For authorised hospital personnel only.<br/>Patient information requires confidential handling.</span></div>
    </div><small className="login-copyright">Dija Hospital · Nigeria · Africa/Lagos</small></section>
  </main>;

  const user = session.user;
  const can = module => user.modules.includes(module);
  const canRegister = ['administrator', 'receptionist', 'nurse'].includes(user.role);
  const title = NAV.find(n => n[0] === page)?.[1];
  const stats = dashboard?.stats;
  const filteredDepartments = departments.filter(d => (category === 'all' || d.category === category) && `${d.name} ${d.description}`.toLowerCase().includes(query.toLowerCase()));
  const clinical = departments.filter(d => d.category === 'clinical');
  const buttonLabels = { patients: 'Register patient', appointments: 'Book appointment', admissions: 'Admit patient', invoices: 'Create invoice' };
  const showCreate = page in buttonLabels && (page !== 'patients' || canRegister);

  return <div className="app-shell">
    {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)}/>}
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand"><span className="brand-mark"><Cross size={24}/></span><div>Dija Hospital<small>HOSPITAL MANAGEMENT</small></div></div>
      <div className="branch-switch"><span className="branch-icon"><Building2 size={18}/></span><div>{user.branch?.name || 'No branch assigned'}<small>Nigeria <span className="status-dot"/> Active</small></div><span className="branch-tag">01</span></div>
      <span className="nav-label">WORKSPACE</span>
      <nav>{NAV.filter(([key]) => ['dashboard','departments'].includes(key) || can(key)).map(([key, label, Icon]) => <button key={key} className={page === key ? 'nav-item active' : 'nav-item'} onClick={() => navigate(key)}><Icon size={19}/><span>{label}</span>{page === key && <span className="nav-active-dot"/>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="growth-card"><span className="growth-icon"><HeartPulse size={22}/></span><h3>Better care, together.</h3><p>A connected hospital.<br/>A healthier community.</p><span>DIJA HOSPITAL <ArrowUpRight size={14}/></span></div><button className="nav-item" onClick={() => setHelpOpen(true)}><CircleHelp size={19}/>Help & workspace guide</button><button className="user-card" onClick={signOut} title="Sign out" aria-label={`Sign out ${user.name}`}><span className="avatar">{initials(user.name)}</span><span><strong>{user.name}</strong><small>{human(user.role)}</small></span><LogOut size={17}/></button></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileOpen(true)}><Menu size={22}/></button><span>Workspace</span><ChevronRight size={14}/><strong>{title}</strong></div><div className="topbar-right"><span className="secure-label"><span className="status-dot"/> Staff workspace</span><span className="topbar-divider"/><button className="icon-button" aria-label="Open workspace guide" onClick={() => setHelpOpen(true)}><CircleHelp size={20}/></button><span className="avatar small">{initials(user.name)}</span><span className="topbar-username" title={user.name}>{user.name}</span><button className="signout-button" onClick={signOut}><LogOut size={16}/><span>Sign out</span></button></div></header>
    <main className="content"><div className="page-heading"><div><div className="eyebrow">{(user.branch?.name || 'Dija Hospital').toUpperCase()}</div><h1>{page === 'dashboard' ? 'Hospital overview' : title}<span className="heading-dot">.</span></h1><p>{({ dashboard: 'A clear view of your hospital. A better day of care.', patients: 'Every patient, connected to the care they need.', appointments: 'Keep your clinics organised and your patients moving.', laboratory: 'Test requests, specimen collection and signed reports.', consultations: 'Clinical notes, observations and continuity of care.', admissions: 'Coordinate inpatient care, wards and bed assignments.', departments: 'Every department. One connected hospital.', invoices: 'Manage hospital invoices and record payments in naira.' })[page]}</p></div><div className="heading-actions">{page === 'dashboard' ? <><span className="date-pill"><CalendarDays size={16}/>{new Date().toLocaleDateString('en-NG', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Africa/Lagos' })}</span>{canRegister && <button className="primary" onClick={() => openDialog('patients')}><Plus size={18}/>Register patient</button>}</> : showCreate && <button className="primary" onClick={() => openDialog(page)}><Plus size={18}/>{buttonLabels[page]}</button>}</div></div>
    {notice && <div className="toast" role="status"><Check size={18}/>{notice}<button className="icon-button" aria-label="Dismiss notification" onClick={() => setNotice('')}><X size={16}/></button></div>}
    {error && !dialog && <div className="alert error" role="alert">{error}<button onClick={() => setRefresh(v => v+1)}>Retry</button></div>}

    {page === 'dashboard' && <>
      <section className="welcome-banner"><div><span className="banner-tag"><span className="status-dot"/> YOUR DAILY PULSE</span><h2>Good {new Date().toLocaleTimeString('en', { hour: 'numeric', hour12: false, timeZone: 'Africa/Lagos' }).split(':')[0] < 12 ? 'morning' : 'day'}, {user.name.split(' ')[0]}.</h2><p>From the first appointment to the last round,<br className="desktop-break"/> let’s make every patient’s journey a little better.</p><button onClick={() => navigate(can('appointments') ? 'appointments' : 'departments')}>{can('appointments') ? 'View appointments' : 'Explore departments'}<ArrowRight size={16}/></button></div><div className="banner-art" aria-hidden="true"><div className="art-circle outer"/><div className="art-circle inner"/><HeartPulse className="art-heart" size={105} strokeWidth={1.15}/><span className="art-cross a">+</span><span className="art-cross b">+</span><span className="art-badge"><ShieldCheck size={17}/> Connected care</span></div></section>
      <section className="stats-grid" aria-label="Hospital statistics"><Stat label="Registered patients" value={stats?.patients} Icon={Users} detail={`${stats?.new_patients ?? 0} registered today`} tone="green"/><Stat label="Today's appointments" value={stats?.appointments} Icon={CalendarDays} detail={`${stats?.checked_in ?? 0} patients checked in`} tone="blue"/><Stat label="Current inpatients" value={stats?.admitted} Icon={BedDouble} detail="Active ward admissions" tone="amber"/><Stat label="Hospital departments" value={stats?.departments} Icon={Building2} detail="Across the main branch" tone="purple"/></section>
      <div className="dashboard-columns"><section className="panel"><div className="panel-heading"><div><h2>Today’s appointments</h2><p>Patient visits across your clinics</p></div>{can('appointments') && <button className="text-button" onClick={() => navigate('appointments')}>View all<ArrowRight size={15}/></button>}</div>{listLoading ? <div className="empty-state">Loading appointments…</div> : !dashboard?.appointments.length ? <Empty Icon={CalendarDays} title="A new day of care" text={can('appointments') ? 'Book an appointment to start building today’s clinic schedule.' : 'Your role does not include individual appointment records.'} action={can('appointments') ? () => openDialog('appointments') : null} label="Book appointment"/> : <AppointmentTable rows={dashboard.appointments}/>}</section>
      <section className="panel quick-panel"><div className="panel-heading"><div><h2>Quick actions</h2><p>A little less admin. A little more care.</p></div><span className="subtle-icon"><Activity size={19}/></span></div><div className="quick-actions">{canRegister && <Quick Icon={Users} title="Register a patient" subtitle="Create a new hospital record" onClick={() => openDialog('patients')}/>} {can('appointments') && <Quick Icon={CalendarDays} title="Book an appointment" subtitle="Find the right department" onClick={() => openDialog('appointments')}/>} {can('admissions') && <Quick Icon={BedDouble} title="Admit a patient" subtitle="Assign a ward and bed" onClick={() => openDialog('admissions')}/>} {can('invoices') && <Quick Icon={CreditCard} title="Create an invoice" subtitle="Bill for hospital services" onClick={() => openDialog('invoices')}/>}<Quick Icon={Building2} title="Explore departments" subtitle="Your hospital, connected" onClick={() => navigate('departments')}/></div></section></div>
      <div className="dashboard-columns lower"><section className="panel"><div className="panel-heading"><div><h2>Recently registered</h2><p>New faces in the Dija Hospital family</p></div>{can('patients') && <button className="text-button" onClick={() => navigate('patients')}>All patients<ArrowRight size={15}/></button>}</div>{dashboard?.patients.length ? <div className="recent-list">{dashboard.patients.map(p => <div className="recent-patient" key={p.id}><span className="patient-avatar">{initials(p.name)}</span><div><strong>{p.name}</strong><small>{p.hospital_number}</small></div><span className="muted">{dateLabel(p.created_at)}</span></div>)}</div> : <Empty Icon={Users} title="Patient records start here" text={can('patients') ? 'Your most recently registered patients will appear here.' : 'Patient records are available to clinical and registration staff.'}/>}</section><section className="panel activity-panel"><div className="panel-heading"><div><h2>Clinic activity</h2><p>Today’s scheduled visits by department</p></div><Stethoscope size={20} className="muted"/></div><div className="clinic-bars">{(dashboard?.department_activity ?? []).slice(0,5).map(d => <div className="clinic-bar" key={d.name}><div><span>{d.name}</span><strong>{d.count}</strong></div><div className="bar-track"><span style={{ width: `${d.count ? Math.max(6, d.count / Math.max(1, ...dashboard.department_activity.map(x => x.count)) * 100) : 0}%` }}/></div></div>)}{!dashboard && <p className="muted">Loading clinic activity…</p>}</div><div className="panel-footnote"><span className="status-dot"/> Live records · Africa/Lagos (WAT)</div></section></div>
    </>}

    {page === 'departments' && <><div className="department-intro"><Building2 size={26}/><div><strong>{departments.length} departments, one shared purpose.</strong><p>The directory covers clinical, diagnostic, operational and administrative services. Specialist workflows will be added in later phases.</p></div></div><div className="directory-tools"><div className="tabs"><button onClick={() => setCategory('all')} className={category === 'all' ? 'selected' : ''}>All departments <span>{departments.length}</span></button>{Object.entries(CATEGORIES).map(([key, value]) => <button key={key} onClick={() => setCategory(key)} className={category === key ? 'selected' : ''}>{value}</button>)}</div><SearchBox value={query} onChange={setQuery} placeholder="Find a department…"/></div><div className="department-grid">{filteredDepartments.map((d, index) => <article className="department-card" key={d.id}><div className="department-top"><span className={`department-icon tone-${d.category}`}>{d.category === 'clinical' ? <Stethoscope/> : d.category === 'diagnostics' ? <Activity/> : d.category === 'operations' ? <HeartPulse/> : <Building2/>}</span><span className="department-number">{String(index+1).padStart(2,'0')}</span></div><span className="eyebrow">{CATEGORIES[d.category]}</span><h2>{d.name}</h2><p>{d.description}</p><div className="department-footer">{d.category === 'clinical' && can('appointments') ? <button className="text-button" onClick={() => openDialog('appointments')}>Book appointment<ArrowUpRight size={16}/></button> : <span className="directory-label">Department directory</span>}<span className="status-dot"/></div></article>)}</div>{!filteredDepartments.length && <Empty Icon={Search} title="No departments found" text="Try another search or category."/>}</>}

    {page === 'consultations' && <ConsultationWorkspace api={api} user={user} Modal={Modal} notify={setNotice} onOpenLaboratory={(record, openRequest) => {setLabContext({...record, openRequest});navigate('laboratory');}}/>}
    {page === 'laboratory' && <LaboratoryWorkspace api={api} user={user} Modal={Modal} notify={setNotice} initialConsultation={labContext} consumeInitial={() => setLabContext(null)}/>}
    {page !== 'dashboard' && page !== 'departments' && page !== 'consultations' && page !== 'laboratory' && <section className="panel records-panel"><div className="records-toolbar"><div><h2>{title}</h2><p>{page === 'patients' ? `${total} registered patients` : 'Current branch records'}</p></div>{page === 'patients' && <SearchBox value={query} onChange={v => { setQuery(v); setPageNumber(1); }} placeholder="Search name, hospital no. or phone…"/>}</div>{listLoading ? <div className="empty-state">Loading records…</div> : !rows.length ? <Empty Icon={page === 'patients' ? Users : page === 'appointments' ? CalendarDays : page === 'admissions' ? BedDouble : CreditCard} title="No records to show" text={query ? 'Try a different search.' : `Start by adding your first ${page === 'patients' ? 'patient' : page === 'appointments' ? 'appointment' : page === 'admissions' ? 'admission' : 'invoice'}.`} action={showCreate ? () => openDialog(page) : null} label={buttonLabels[page]}/> : <>
      {page === 'patients' && <div className="table-scroll"><table><thead><tr><th>Patient</th><th>Hospital number</th><th>Date of birth</th><th>Sex</th><th>Phone number</th><th>Registered</th></tr></thead><tbody>{rows.map(p => <tr key={p.id}><td><div className="patient-cell"><span className="patient-avatar">{initials(p.name)}</span><strong>{p.name}</strong></div></td><td><code>{p.hospital_number}</code></td><td>{dateLabel(p.date_of_birth+'T12:00:00+01:00')}</td><td className="capitalize">{p.sex}</td><td>{p.phone}</td><td>{dateLabel(p.created_at)}</td></tr>)}</tbody></table></div>}
      {page === 'appointments' && <AppointmentTable rows={rows} onUpdate={(id, status) => updateRecord('appointments', id, status)} busy={busy} clinical={['administrator','doctor','nurse'].includes(user.role)}/>}
      {page === 'admissions' && <div className="table-scroll"><table><thead><tr><th>Patient</th><th>Department</th><th>Ward / bed</th><th>Admitted</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.map(a => <tr key={a.id}><td><strong>{a.patient_name}</strong><small className="cell-sub">{a.hospital_number}</small></td><td>{a.department}</td><td>{a.ward} / {a.bed}</td><td>{dateLabel(a.admitted_at)}</td><td><span className={`badge ${a.discharged_at ? 'completed' : 'checked_in'}`}>{a.discharged_at ? 'Discharged' : 'Admitted'}</span></td><td>{!a.discharged_at && ['administrator','doctor'].includes(user.role) && <button disabled={busy} className="table-action" onClick={() => setDialog({ type: 'confirm', resource: 'admissions', id: a.id, text: `Discharge ${a.patient_name}? This will release the assigned bed.`, label: 'Confirm discharge' })}>Discharge</button>}</td></tr>)}</tbody></table></div>}
      {page === 'invoices' && <div className="table-scroll"><table><thead><tr><th>Invoice</th><th>Patient</th><th>Description</th><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.map(i => <tr key={i.id}><td><code>INV-{String(i.id).padStart(5,'0')}</code><small className="cell-sub">{dateLabel(i.created_at)}</small></td><td><strong>{i.patient_name}</strong></td><td>{i.description}</td><td className="amount">{money(i.amount)}</td><td><span className={`badge ${i.status === 'paid' ? 'completed' : 'scheduled'}`}>{human(i.status)}</span></td><td>{i.status === 'unpaid' && <button disabled={busy} className="table-action" onClick={() => setDialog({ type: 'confirm', resource: 'invoices', id: i.id, text: `Confirm that payment of ${money(i.amount)} has been received for INV-${String(i.id).padStart(5,'0')}? This records a manual payment; it does not charge the patient.`, label: 'Record payment received' })}>Record payment</button>}</td></tr>)}</tbody></table></div>}
      </>}{page === 'patients' && total > 20 && <div className="pagination"><span>Page {pageNumber} of {Math.ceil(total/20)}</span><button className="secondary" disabled={pageNumber === 1} onClick={() => setPageNumber(v=>v-1)}><ChevronLeft size={16}/>Previous</button><button className="secondary" disabled={pageNumber*20 >= total} onClick={() => setPageNumber(v=>v+1)}>Next<ChevronRight size={16}/></button></div>}{page !== 'patients' && rows.length >= 100 && <p className="panel-footnote">Showing the latest 100 records.</p>}</section>}
    <footer className="workspace-footer"><span><Cross size={13}/>Dija Hospital <span className="footer-dot">·</span> Care, connected.</span><span>Nigeria <span className="footer-dot">·</span> WAT (UTC+1)</span></footer>
    </main></div>

    {dialog && <Modal title={typeof dialog === 'object' ? 'Confirm action' : buttonLabels[dialog]} onClose={() => { if(!busy) {setDialog(null);setError('');} }}>
      {error && <div className="alert error" role="alert">{error}</div>}
      {typeof dialog === 'object' ? <><p className="confirm-copy">{dialog.text}</p><div className="form-actions"><button className="secondary" disabled={busy} onClick={() => setDialog(null)}>Cancel</button><button className="primary" disabled={busy} onClick={async () => { if (await updateRecord(dialog.resource, dialog.id)) setDialog(null); }}>{busy ? 'Saving…' : dialog.label}</button></div></> : <form onSubmit={submitRecord}>
      <p className="form-intro">{dialog === 'patients' ? 'Create a patient record for Dija Hospital. Fields marked * are required.' : 'Add a record for the current branch. All appointment times use West Africa Time.'}</p>
      {dialog === 'patients' ? <><div className="form-grid"><Field label="First name *" name="first_name" maxLength={80}/><Field label="Last name *" name="last_name" maxLength={80}/><Field label="Date of birth *" name="date_of_birth" type="date" min="1900-01-01" max={new Date().toLocaleDateString('en-CA', { timeZone: 'Africa/Lagos' })}/><label>Sex *<select aria-label="Sex *" name="sex" required defaultValue=""><option value="" disabled>Select</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></select></label><Field label="Nigerian mobile number *" name="phone" type="tel" placeholder="08031234567" maxLength={20}/><Field label="Next of kin name" name="next_of_kin_name" required={false} maxLength={160}/><Field label="Next of kin mobile" name="next_of_kin_phone" type="tel" required={false} placeholder="08031234567" maxLength={20}/></div><label>Home address<textarea name="address" rows={2} maxLength={500}/></label><div className="form-note"><ShieldCheck size={16}/>A unique hospital number will be generated on registration.</div></> : <><label>Find patient<input name="patient_search" placeholder="Search by name or hospital number" onChange={e => findPatients(e.target.value)}/></label><label>Patient *<select aria-label="Patient *" name="patient_id" defaultValue="" required><option value="" disabled>Select a patient</option>{patientOptions.map(p => <option key={p.id} value={p.id}>{p.name} · {p.hospital_number}</option>)}</select></label>{!patientOptions.length && <p className="form-note">No matching patients. Ask registration to create a patient record first.</p>}
      {dialog !== 'invoices' && <label>Department *<select aria-label="Department *" name="department_id" defaultValue="" required><option value="" disabled>Select a clinical department</option>{clinical.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>}
      {dialog === 'appointments' && <Field label="Appointment date & time (WAT) *" name="scheduled_at" type="datetime-local"/>}
      {dialog === 'admissions' && <div className="form-grid"><Field label="Ward *" name="ward" placeholder="e.g. Medical ward" maxLength={80}/><Field label="Bed *" name="bed" placeholder="e.g. M-01" maxLength={20}/></div>}
      {dialog === 'invoices' && <><Field label="Service description *" name="description" placeholder="e.g. Outpatient consultation" maxLength={200}/><Field label="Amount (NGN) *" name="amount" type="number" min="0.01" max="9999999999.99" step="0.01"/><div className="form-note">New invoices are unpaid. Record receipt only after payment is confirmed.</div></>}
      </>}
      <div className="form-actions"><button type="button" className="secondary" disabled={busy} onClick={() => {setDialog(null);setError('');}}>Cancel</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : buttonLabels[dialog]}{!busy && <ArrowRight size={16}/>}</button></div>
      </form>}
    </Modal>}
    {helpOpen && <Modal title="Your Dija Hospital workspace" onClose={() => setHelpOpen(false)}><div className="help-content"><p>Start with patient registration, then book a clinic appointment, admit a patient to a ward, or create an invoice.</p><h3>What works today</h3><p>Patient registration and search, signed consultations with vital signs and clinical addenda, laboratory requests and signed results, appointments with check-in and completion, admissions with bed conflict checks, discharge, naira invoices and manual payment recording.</p><h3>Departments & future phases</h3><p>The directory includes 33 departments. Prescribing, pharmacy dispensing, imaging, theatre, NHIA/HMO claims, HR and stock workflows are planned; listing a department does not activate its specialist functions.</p><h3>Staff access</h3><p>Your administrator assigns roles and branches through Django administration. New branches can be configured there. Each staff account works within its assigned branch; cross-branch transfer is a future workflow.</p><h3>Development version</h3><p>Use synthetic records only until security review, backups, clinical governance and Nigeria Data Protection Act requirements have been addressed for your hospital.</p><button className="primary" onClick={() => setHelpOpen(false)}>Got it<Check size={16}/></button></div></Modal>}
  </div>;
}

function Field({ label, required = true, ...props }) { return <label>{label}<input {...props} required={required}/></label>; }
function SearchBox({ value, onChange, placeholder }) { return <div className="search-box"><Search size={17}/><input aria-label={placeholder} placeholder={placeholder} value={value} onChange={e => onChange(e.target.value)}/>{value && <button aria-label="Clear search" onClick={() => onChange('')}><X size={15}/></button>}</div>; }
function Stat({ label, value, Icon, detail, tone }) { return <article className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon ${tone}`}><Icon size={20}/></span></div><strong className="stat-value">{value ?? '—'}</strong><span className="stat-detail"><span className={`mini-dot ${tone}`}/>{detail}</span></article>; }
function Quick({ Icon, title, subtitle, onClick }) { return <button onClick={onClick} className="quick-action"><span className="quick-icon"><Icon size={20}/></span><span><strong>{title}</strong><small>{subtitle}</small></span><ChevronRight size={16}/></button>; }
function Empty({ Icon, title, text, action, label }) { return <div className="empty-state"><span className="empty-icon"><Icon size={26} strokeWidth={1.4}/></span><h3>{title}</h3><p>{text}</p>{action && <button className="text-button" onClick={action}><Plus size={15}/>{label}</button>}</div>; }
function AppointmentTable({ rows, onUpdate, busy, clinical }) { return <div className="table-scroll"><table><thead><tr><th>Patient</th><th>Department</th><th>{onUpdate ? 'Date & time' : 'Time'}</th><th>Status</th>{onUpdate && <th>Action</th>}</tr></thead><tbody>{rows.map(a => <tr key={a.id}><td><div className="patient-cell"><span className="patient-avatar">{initials(a.patient_name)}</span><div><strong>{a.patient_name}</strong><small className="cell-sub">{a.hospital_number}</small></div></div></td><td>{a.department}</td><td>{onUpdate && <small className="cell-sub">{dateLabel(a.scheduled_at)}</small>}{timeLabel(a.scheduled_at)}</td><td><span className={`badge ${a.status}`}>{human(a.status)}</span></td>{onUpdate && <td><div className="table-actions">{a.status === 'scheduled' && <button disabled={busy} className="table-action" onClick={() => onUpdate(a.id, 'checked_in')}>Check in</button>}{a.status === 'checked_in' && clinical && <button disabled={busy} className="table-action" onClick={() => onUpdate(a.id, 'completed')}>Complete</button>}{['scheduled','checked_in'].includes(a.status) && <button disabled={busy} className="table-action danger" onClick={() => onUpdate(a.id, 'cancelled')}>Cancel</button>}</div></td>}</tr>)}</tbody></table></div>; }
function Modal({ title, onClose, children }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    ref.current?.focus();
    function key(e) {
      if (e.key === 'Escape') closeRef.current();
      if (e.key === 'Tab') {
        const nodes = [...ref.current.querySelectorAll('button:not(:disabled), input, select, textarea, [tabindex="0"]')];
        const first = nodes[0], last = nodes[nodes.length-1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) { e.preventDefault(); last?.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }
    document.addEventListener('keydown', key);
    return () => { document.body.style.overflow = overflow; document.removeEventListener('keydown', key); previous?.focus(); };
  }, []);
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" tabIndex={-1} ref={ref}><div className="modal-header"><div><span className="eyebrow">DIJA HOSPITAL</span><h2 id="modal-title">{title}</h2></div><button className="icon-button" aria-label="Close dialog" onClick={onClose}><X size={21}/></button></div>{children}</section></div>;
}
