# Dija Hospital

A new hospital management project for a general hospital in Nigeria, separate from the existing grains-store project. Built with Next.js 16, React 19, Django 5.2 and PostgreSQL 17. It starts with one branch and uses branch-owned records throughout so more branches can be added later.

## Working first release

- Staff sign-in with Django sessions, CSRF protection, a one-hour session lifetime and role-based API access.
- Dashboard with actual database counts, today's appointments, recent patients and clinic activity.
- Patient registration, generated hospital numbers, Nigerian mobile-number validation, next-of-kin capture and paginated search.
- Appointments by department, check-in, cancellation and clinical completion.
- Signed consultations linked to checked-in appointments, optional measured vital signs, explicit allergy status, symptoms/history, examination, diagnosis, treatment and follow-up. Signing completes the appointment atomically; dated addenda preserve original records.
- Admissions with occupied-bed and duplicate-admission protection; doctor-authorised discharge.
- Naira invoices and explicit confirmation of manual payment receipts. No payment gateway or insurance processing is connected.
- Laboratory requests from signed consultations, specimen labels and collection, signed free-text reports and append-only report addenda.
- Signed prescriptions, medicine catalogue, batch receipts, expiry blocking, partial dispensing and an append-only stock ledger.
- Admission-linked observation charts, signed nursing notes, narrative care plans, ward rounds and medication administration records with dated addenda.
- A searchable directory of 33 clinical, diagnostic, operational and administrative departments.
- Branch scoping and audit events for API reads, changes, sign-in and sign-out. The audit log records identifiers and actions, not copied patient names or clinical content.
- A superuser-only Django administration console for configuring branches, departments and staff roles.

No real patient data is included. Browser validation creates synthetic records and removes them afterwards.

## Start in this cloud workspace

```bash
bash /workspace/hospital-management/scripts/setup.sh
bash /workspace/hospital-management/scripts/start.sh
```

Setup is repeatable: it preserves the database, generates local secrets only if absent, installs locked dependencies and applies migrations. The cloud image is Debian trixie with Python 3.12 and Node 24. PostgreSQL runs as the workspace user, listening only on loopback. Its trust authentication is strictly for this isolated development machine. The database `dija_hospital` is separate from `elohim_grains`.

Your name and a labelled **Sign out** button appear in the top-right header and stay reachable while scrolling. The sidebar also scrolls on short screens, with account controls at its bottom.

The frontend uses port 3100 and proxies `/api/` to Django on port 8000. The service processes need to restart after cloud restoration. Logs and PID files are in `.local/`; secrets and generated credentials there are ignored by Git. Use existing checkout directories; cloud tasks already provide isolation, so do not create a Git worktree unless requested.

The generated local administrator username is `dija-admin`. Its random password is saved in `.local/admin-login.json` with owner-only permissions. Retrieve it privately in your workspace; do not commit, share or paste that file into chat. It is a development account. To set a password of your choice:

```bash
cd /workspace/hospital-management/backend
source ../scripts/runtime.sh
../.venv/bin/python manage.py changepassword dija-admin
```

Django administration is served on the backend under `/admin/`. Create users there and assign each a **Staff profile** with a role and branch. Ordinary staff should not be superusers. The administration console is intentionally restricted to trusted superusers; staff work through the branch-scoped application. Available roles: administrator, receptionist, doctor, nurse, accountant, laboratory scientist and pharmacist. Laboratory scientists can process requests and sign laboratory reports, but cannot read consultation notes or register patients. Pharmacists can maintain the medicine catalogue, receive batches, dispense prescriptions and record stock write-offs. They see the patient identifier and allergy snapshot needed for dispensing, without access to broader consultation or demographic records. Registration is restricted to administrators, receptionists and nurses; doctors can read patient records. Accounts staff can see billing and a minimal patient selector without access to demographic records or admissions.

Branch staff cannot override their assigned branch through API parameters. A trusted superuser can select an active branch through the API's `branch` query parameter; a branch-switching interface and cross-branch patient transfers are future work. Add another branch and its departments through administration when required.

## Validation

```bash
cd /workspace/hospital-management/backend
source ../scripts/runtime.sh
../.venv/bin/python manage.py check
../.venv/bin/python manage.py makemigrations --check --dry-run
../.venv/bin/python manage.py test hospital --noinput

cd ../frontend
npm run build
# Start services first; keep runtime variables from above for test cleanup.
npx playwright test
```

The 58 backend tests cover login/CSRF, staff access, registration, branch boundaries, appointments, admissions, billing and audit events. Browser tests exercise registration → appointment → check-in → signed consultation → clinical addendum → laboratory request → specimen collection → signed result → report addendum, medicine creation → batch receipt → prescription → partial/full dispensing → stock write-off, admission → observation chart → nursing note → care plan → ward round → given/refused medication records → discharge, invoice → payment, the department directory, mobile layout and sign-out. Chromium is used from `/usr/bin/chromium`; set `CHROMIUM_PATH` if different. Browser tests read only the private local development credentials. Do not run them against real patient databases.

## Department roadmap

The department directory is broader than the working transaction modules. A department appearing in the directory does **not** mean its specialist functions are complete.

| Area | Departments | Planned specialist workflows |
| --- | --- | --- |
| Clinical care | Outpatient, emergency, internal medicine, surgery, obstetrics/gynaecology, paediatrics, ICU, orthopaedics, eye, dental, ENT, mental health, nursing, physiotherapy, community health | Triage workflow, coded diagnoses, care-plan task management, referrals, maternity records and discharge summaries |
| Diagnostics & treatment | Laboratory, radiology, pharmacy, blood bank | Structured laboratory analytes, analyser integration and critical-result escalation; imaging/PACS integration; automated prescription decision support, controlled-drug workflows, stock transfers and transfusion controls |
| Operations | Theatre, medical records, ambulance, mortuary, nutrition, infection prevention, sterilisation, facilities | Procedure scheduling, transport, release approvals, dietary orders, surveillance, instrument tracking, equipment and housekeeping |
| Administration | Accounts, NHIA/HMO, HR, procurement/stores, hospital administration, ICT | Receipt/reconciliation, partial payments/refunds, tariffs, authorisations/claims, rosters/payroll, stock/procurement, reporting and integrations |

The current release is a development foundation, not a complete clinical electronic medical record or a production-certified hospital system. Directly completing an appointment does not create a consultation note; use Consultations to sign one. Treatment-plan text does not issue prescriptions or order tests; recording a payment does not move money.

## Before using real hospital records

Arrange hospital-specific clinical and access review, Nigeria Data Protection Act obligations, retention/consent policies and operational sign-off. Add HTTPS deployment, managed PostgreSQL with verified TLS, backups with restore testing, shared-cache login limits, stronger account controls/MFA, access monitoring, audit-log retention, incident handling and disaster recovery. Configure `DJANGO_DEBUG=false`, a deployment secret, allowed hosts, trusted HTTPS origins and `DB_SSLMODE=verify-full` with the database provider's CA. Development launch scripts are not production deployment scripts.

The frontend and Django should share an HTTPS origin through a trusted reverse proxy. Keep Django administration separately restricted. No payment, messaging or external health-service credentials are currently required or configured.

## Update an existing WSL installation

Stop Django and Next.js with Ctrl+C in their terminals. From the project root:

```bash
git pull --ff-only
source .venv/bin/activate
cd backend
source ../.local/wsl-env.sh
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

In another terminal, from the project root: `cd frontend` then `npm run dev`. Sign out and back in to refresh staff module access. No existing patients or accounts are replaced by this migration.

Doctors and administrators can open **Consultations → New consultation** after a patient is checked in. Nurses can read consultation records but cannot sign or append clinical notes. Reception, billing and other roles cannot read consultation content. Use **View record → Add addendum** for corrections. Signed notes have no edit/delete API, and administration treats them as read-only. Allergy status and vitals are recorded per consultation, not as a longitudinal allergy register. Empty vital signs mean not recorded; entry bounds are data validation, not clinical reference ranges. Follow-up dates do not automatically book appointments. Only synthetic records have been validated.

## Laboratory workflow

The laboratory module is available after applying migrations with `python manage.py migrate` using the existing WSL instructions above. The migration adds a starter catalogue to existing branches without modifying existing patient data. A subsequent sign-out/sign-in refreshes the staff navigation.

1. Register a synthetic patient, book an appointment, check in, and sign the consultation.
2. As a doctor or administrator, open **Consultations → View record → Request laboratory test**, or **Laboratory → Request test** and search for a signed consultation. Select a test, priority and clinical indication. Each request contains one test; repeat requests are allowed.
3. As a laboratory scientist or administrator, open **Laboratory → View request → Record collection**. Confirm patient/specimen identity and enter the specimen label. The collection timestamp records the time this action is saved; backdating is not implemented.
4. Select **Enter results**. Enter verified results with units and any laboratory-specific reference information, review the identity/specimen/results confirmation, and sign. The request becomes Reported; the original report cannot be edited or deleted through the application or administration console.
5. Doctors and nurses can view signed reports. **View patient lab requests** in a consultation filters laboratory requests by that patient's hospital number across visits. Laboratory staff can append a dated **report addendum** for corrections without replacing the original report.
6. Doctors/administrators can cancel a request only before collection and must give a reason. Collected, reported or cancelled requests cannot be processed as new requests.

The hospital owner can configure **Lab tests** through Django administration. Five starter entries are included: full blood count, malaria parasite test, urinalysis, random blood glucose, and urea/electrolytes/creatinine. Verify the approved catalogue and specimen requirements for your hospital. Future branches can receive missing starter entries through `python manage.py seed_lab_tests`; repeated runs preserve existing names, specimen settings and inactive entries. Historical request names and specimen types are snapshots, so catalogue edits do not rewrite past records.

Laboratory scientists cannot create test requests or view broader patient/consultation records. Doctors cannot collect specimens or sign laboratory reports; nurses have read access. Administrators can exercise the full workflow for development and testing. Staff are assigned to their own branches through Staff profiles. Read access and workflow actions are audited without copying result text into audit events.

This module records manually entered reports. It does not generate test values, reference ranges or diagnoses, interface with laboratory instruments, issue invoices, send external orders, deliver critical-result alerts, track clinician acknowledgement, or automatically amend a treatment plan. These capabilities and laboratory-specific clinical validation remain separate work. Continue with synthetic data only.

## Prescriptions and pharmacy

Update existing WSL installations using `git pull --ff-only` and `python manage.py migrate` as above; no dependencies or existing patient accounts are replaced. Restart both servers and sign out/sign in to load the Pharmacy menu. No medicine names, doses, stock quantities or prices are seeded.

### First sample workflow

1. As administrator or pharmacist, open **Pharmacy → Add medicine**. Enter a separate code, name, strength, formulation and smallest dispensing unit for each approved product. For software testing use a clearly synthetic medicine, dummy strength/formulation and `units`. Do not use a real regimen as sample data.
2. Select **Receive stock**, choose the medicine and enter its batch label, exact expiry date, quantity in dispensing units and a unique receipt reference for this entry. Subsequent deliveries can top up the same batch using a new receipt reference, provided the expiry date matches. Reusing a receipt reference cannot add stock again.
3. As a doctor or administrator, open **Consultations → View record → Prescribe medicine**, or **Pharmacy → New prescription** and search for a signed consultation. Enter one medicine, dose, route, frequency, duration, total whole-number quantity in dispensing units, and patient instructions. Review the patient and allergy information before signing. No dosing or quantity calculation is performed.
4. As pharmacist or administrator, open **Pharmacy → View prescription → Dispense medicine**. Verify the current patient, allergies, prescription and medicine; choose a batch and enter the quantity actually dispensed. The eligible batch list is ordered by earliest expiry, and excludes expired/expiring-today or inactive products. Each submission deducts stock and appends history atomically.
5. Dispense part of the quantity now and the remainder later, or split across batches with separate entries. The system blocks quantities above the unfilled prescription or available batch balance, including when two requests compete for the same stock. Repeated submissions with the same dispensing-action identifier do not deduct stock twice.
6. Review **Medicines**, **Stock batches** and **Stock history**. Medicines show available unexpired stock and configured low-stock flags. Expired stock is retained for traceability but cannot be dispensed. A reasoned **Write off** action removes damaged/unusable stock and preserves the signed stock movement; retries of the same action cannot remove stock twice.

### Roles, corrections and limits

Doctors/administrators can sign prescriptions and cancel an active prescription's unfilled quantity with a reason. Pharmacists/administrators can receive, dispense and write off stock. Nurses have prescription read access. Reception, accounts and laboratory roles cannot read prescriptions. All records are scoped to staff branches.

Prescribed product identity and the consultation allergy record are snapshots. Signed prescriptions, dispensing and stock movements have no edit/delete API and are read-only in administration. Correct a prescription by cancelling its unfilled quantity and issuing a new one. Prior dispensing remains in history and cancellation does not put medicine back into stock. The system prevents changing a medicine's identity in administration after stock or prescribing; create a new entry and deactivate the old product instead. Active status and low-stock threshold can still be updated there.

The allergy snapshot may not reflect a later clinical addendum or newly discovered allergy. Both prescriber and dispenser must verify current information with the patient and clinical team; there is no automated allergy/interaction check. The confirmation records a staff workflow, not an independently verified clinical assessment.

Only whole-number stock quantities are supported, in the declared dispensing unit. No pack conversion, substitution, dose recommendation, renal/weight calculation, automated prescription expiry, controlled-drug register, barcode integration, supplier purchasing, quarantine workflow, return/refund, cross-branch transfer or automatic invoice generation is implemented. Test with synthetic data; hospital-specific pharmacy validation and deployment controls remain required before live use.

## Nursing and inpatient care

Apply `python manage.py migrate` after pulling the update, restart the two servers, and sign out/sign in to refresh the **Nursing & inpatient care** menu. Existing admissions and clinical records are preserved. Nothing is seeded as a bedside observation, care plan or medication dose.

### Bedside sample workflow

1. Admit a synthetic patient through **Admissions & wards**. Open **Open care record** on the admission row, or choose an admission from **Nursing & inpatient care**. Search by patient, hospital number, ward or bed; use the admission status filter to retrieve discharged history.
2. As nurse or administrator, choose **Observations → Record observation**. Enter actual event time in WAT and at least one measured value. Missing measurements remain unrecorded; zero pain scores remain zero. Blood pressure requires both values. Event times before admission or in the future are rejected. The chart plots original observations on the current page only; review displayed addenda for corrections. Data-entry limits are not normal ranges, an early-warning score or a clinical alert system.
3. Record **Nursing notes** or **Care plans**. Plans require a summary, goals and interventions and may include a review date. Plans are narrative records; reviews/evaluations can be dated addenda. Task assignment, completion tracking and reminder scheduling are not implemented.
4. Doctors/administrators record **Ward rounds** with assessment and plan. Doctors can read nursing records but cannot sign nursing observations, notes, plans or medication administration as a nurse. Nurses can read ward rounds but cannot sign or amend them. Administrators can test both roles.
5. New bedside records are allowed only while the admission is active. After discharge the original records remain readable, and authorised staff can append dated corrections. Admissions are read-only in Django administration; create and discharge them through the application to preserve their clinical identity. Signed entries cannot be overwritten or deleted through API or administration. The original event time and the actual recording/signing time are kept separately, together with staff identity.

### Medication administration record

As nurse/administrator, open **Medication record → Record medication**. Select a current prescription for this patient, verify it is appropriate for this admission and check current allergies with the patient/clinical team. Specify the agreed administration slot and actual event time in WAT. No schedule or medication doses are generated automatically.

- For **Given**, choose the matching pharmacy dispensing entry, manually enter the actual dose and quantity used in dispensing units, and confirm checks. Fractional usage up to three decimal places is supported; no strength/pack/dose conversion is calculated. Supply must already have been dispensed, must not have expired at the event date and cannot be consumed beyond its dispensed quantity. Inactive medicines and cancelled prescriptions are blocked.
- For **Not given**, **Refused** or **Withheld**, record a reason and leave dose, quantity and dispensed supply blank. These events do not consume supplies. A later given event may follow a not-given entry for the exact same prescription and administration slot, preserving both events. A second given event for that slot is blocked, including concurrent submissions.
- Retrying the same administration-action identifier does not record a second dose. Consumed quantities are checked under database locks. Administration uses the patient's dispensed supply and does not subtract pharmacy inventory again.
- Use **Add dated correction** to append context. Corrections do not erase a historical given dose, reverse its counted usage or automatically return medicine to stock. Discrepancies need clinical/pharmacy review; automated reversal/reconciliation is not implemented.

This is a manual documentation workflow, not an automated medication scheduler or validated prescribing decision system. It does not calculate or verify clinical dosing, allergy interactions, suitable administration windows, duplicate doses entered under different slot times, infusion rates, fluid balances, early-warning scores, clinical escalation or controlled-drug double checks. There is no administration record for medicines without a matching system prescription/dispensing entry. Continue testing with synthetic data until hospital-specific nursing, pharmacy and clinical governance reviews and deployment controls are complete.
