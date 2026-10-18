import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

const root = path.resolve(process.cwd(), '..');
const credentials = JSON.parse(fs.readFileSync(path.join(root, '.local/admin-login.json'), 'utf8'));
const lastName = `UIValidation${Date.now()}`;

test.afterAll(() => {
  // Remove only this test's exact synthetic patient and its dependent records.
  execFileSync(path.join(root, '.venv/bin/python'), ['manage.py', 'shell', '-c', `
from hospital.models import Patient, Appointment, Admission, Invoice, Consultation, ConsultationAddendum, LabOrder, LabReport, LabReportAddendum, Medicine, MedicineBatch, Prescription, Dispense, StockMovement
from django.db.models import Q
patients = Patient.objects.filter(first_name='Synthetic', last_name='${lastName}')
StockMovement.objects.filter(Q(prescription__patient__in=patients) | Q(batch__medicine__code='ui-${lastName.toLowerCase()}')).delete()
Dispense.objects.filter(prescription__patient__in=patients).delete()
Prescription.objects.filter(patient__in=patients).delete()
MedicineBatch.objects.filter(medicine__code='ui-${lastName.toLowerCase()}').delete()
Medicine.objects.filter(code='ui-${lastName.toLowerCase()}').delete()
LabReportAddendum.objects.filter(report__order__patient__in=patients).delete()
LabReport.objects.filter(order__patient__in=patients).delete()
LabOrder.objects.filter(patient__in=patients).delete()
ConsultationAddendum.objects.filter(consultation__patient__in=patients).delete()
Consultation.objects.filter(patient__in=patients).delete()
Appointment.objects.filter(patient__in=patients).delete()
Admission.objects.filter(patient__in=patients).delete()
Invoice.objects.filter(patient__in=patients).delete()
patients.delete()
`], { cwd: path.join(root, 'backend'), env: process.env, stdio: 'pipe' });
});

test('registration, appointments, admission, billing and mobile navigation', async ({ page }) => {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto('/');
  await page.getByLabel('Username', { exact: true }).fill(credentials.username);
  await page.getByLabel('Password', { exact: true }).fill(credentials.password);
  await page.getByRole('button', { name: 'Sign in to workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Hospital overview.' })).toBeVisible();
  await page.getByRole('button', { name: 'Register patient', exact: true }).click();
  let dialog = page.getByRole('dialog');
  await dialog.getByLabel('First name *', { exact: true }).fill('Synthetic');
  await dialog.getByLabel('Last name *', { exact: true }).fill(lastName);
  await dialog.getByLabel('Date of birth *').fill('1995-03-14');
  await dialog.getByLabel('Sex *', { exact: true }).selectOption('female');
  await dialog.getByLabel('Nigerian mobile number *').fill('08031234567');
  await dialog.getByRole('button', { name: 'Register patient', exact: true }).click();
  await expect(page.getByText(`Synthetic ${lastName}`, { exact: true })).toBeVisible();
  await page.getByRole('navigation').getByRole('button', { name: 'Appointments', exact: true }).click();
  await page.getByRole('button', { name: 'Book appointment', exact: true }).first().click();
  dialog = page.getByRole('dialog');
  const patientOption = dialog.getByLabel('Patient *', { exact: true }).locator('option').filter({ hasText: lastName });
  const patientId = await patientOption.getAttribute('value');
  await dialog.getByLabel('Patient *', { exact: true }).selectOption(patientId);
  await dialog.getByLabel('Department *', { exact: true }).selectOption({ label: 'Outpatient clinic' });
  const future = new Date(Date.now()+86400000).toISOString().slice(0,10)+'T10:00';
  await dialog.getByLabel('Appointment date & time (WAT) *').fill(future);
  await dialog.getByRole('button', { name: 'Book appointment', exact: true }).click();
  let row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('scheduled');
  await row.getByRole('button', { name: 'Check in', exact: true }).click();
  await expect(row).toContainText('checked in');
  await page.getByRole('navigation').getByRole('button', { name: 'Consultations', exact: true }).click();
  await page.getByRole('button', { name: 'New consultation' }).click();
  dialog = page.getByRole('dialog');
  const visitId = await dialog.getByLabel('Checked-in appointment *', { exact: true }).locator('option').filter({ hasText: lastName }).getAttribute('value');
  await dialog.getByLabel('Checked-in appointment *', { exact: true }).selectOption(visitId);
  await dialog.getByLabel('Temperature (°C)', { exact: true }).fill('36.7');
  await dialog.getByLabel('Systolic BP (mmHg)', { exact: true }).fill('120');
  await dialog.getByLabel('Diastolic BP (mmHg)', { exact: true }).fill('80');
  await dialog.getByLabel('Symptoms & history *', { exact: true }).fill('Synthetic consultation symptoms');
  await dialog.getByLabel('Diagnosis / clinical assessment *', { exact: true }).fill('Synthetic assessment');
  await dialog.getByLabel('Treatment plan *', { exact: true }).fill('Synthetic treatment plan');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Sign & complete consultation', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await row.getByRole('button', { name: 'View record', exact: true }).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Synthetic assessment', { exact: true })).toBeVisible();
  await expect(dialog.getByText('36.7', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Add addendum', exact: true }).click();
  await dialog.getByLabel('Addendum *', { exact: true }).fill('Synthetic correction recorded as an addendum');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Sign addendum', exact: true }).click();
  await expect(dialog.getByText('Synthetic correction recorded as an addendum', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Synthetic assessment', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Request laboratory test', exact: true }).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('Signed consultation *', { exact: true })).not.toHaveValue('');
  await dialog.getByLabel('Laboratory test *', { exact: true }).selectOption({ label: 'Full blood count · Whole blood' });
  await dialog.getByLabel('Clinical indication *', { exact: true }).fill('Synthetic test request for browser validation');
  await dialog.getByRole('button', { name: 'Submit test request', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('Requested');
  await row.getByRole('button', { name: 'View request', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Record collection', exact: true }).click();
  await dialog.getByLabel('Specimen label / identifier *', { exact: true }).fill('SYNTHETIC-UI-SAMPLE');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Confirm collection', exact: true }).click();
  await dialog.getByRole('button', { name: 'Enter results', exact: true }).click();
  await dialog.getByLabel('Results (include values and units) *', { exact: true }).fill('Synthetic result for software testing only');
  await dialog.getByLabel('Laboratory reference information', { exact: true }).fill('Synthetic reference text');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Sign laboratory report', exact: true }).click();
  await expect(dialog.getByText('Synthetic result for software testing only', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Add report addendum', exact: true }).click();
  await dialog.getByLabel('Report addendum *', { exact: true }).fill('Synthetic report correction');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Sign report addendum', exact: true }).click();
  await expect(dialog.getByText('Synthetic report correction', { exact: true })).toBeVisible();
  await expect(dialog.getByText('Synthetic result for software testing only', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(row).toContainText('Reported');
  await page.getByRole('navigation').getByRole('button', { name: 'Consultations', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await row.getByRole('button', { name: 'View record', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'View patient lab requests', exact: true }).click();
  await expect(page.getByLabel('Search laboratory requests', { exact: true })).not.toHaveValue('');
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('Reported');
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await expect.poll(() => page.locator('.sidebar').evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  if (await page.getByRole('button', { name: 'Dismiss notification' }).isVisible()) await page.getByRole('button', { name: 'Dismiss notification' }).click();
  await page.screenshot({ path: path.join(root, '.local/dija-laboratory-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole('navigation').getByRole('button', { name: 'Pharmacy', exact: true }).click();
  await page.getByRole('button', { name: 'Add medicine', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Medicine code *', { exact: true }).fill('ui-'+lastName.toLowerCase());
  await dialog.getByLabel('Medicine name *', { exact: true }).fill('Synthetic training medicine '+lastName);
  await dialog.getByLabel('Strength *', { exact: true }).fill('Dummy strength');
  await dialog.getByLabel('Formulation *', { exact: true }).fill('Dummy formulation');
  await dialog.getByLabel('Dispensing unit *', { exact: true }).fill('units');
  await dialog.getByLabel('Low-stock threshold *', { exact: true }).fill('5');
  await dialog.getByRole('button', { name: 'Save medicine', exact: true }).click();
  await page.getByRole('button', { name: 'Receive stock', exact: true }).click();
  dialog = page.getByRole('dialog');
  let medicineOption = dialog.getByLabel('Prescription or stock medicine *', { exact: true }).locator('option').filter({ hasText: lastName });
  await expect(medicineOption).toHaveCount(1);
  await dialog.getByLabel('Prescription or stock medicine *', { exact: true }).selectOption(await medicineOption.getAttribute('value'));
  await dialog.getByLabel('Batch number *', { exact: true }).fill('SYNTHETIC-UI-BATCH');
  await dialog.getByLabel('Expiry date *', { exact: true }).fill(new Date(Date.now()+365*86400000).toISOString().slice(0,10));
  await dialog.getByLabel('Quantity received *', { exact: true }).fill('20');
  await dialog.getByLabel('Receipt reference *', { exact: true }).fill('UI-'+lastName);
  await dialog.getByRole('button', { name: 'Record stock receipt', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: lastName })).toContainText('20 / 20 units');
  await page.getByRole('navigation').getByRole('button', { name: 'Consultations', exact: true }).click();
  await page.getByRole('row').filter({ hasText: lastName }).getByRole('button', { name: 'View record', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Prescribe medicine', exact: true }).click();
  dialog = page.getByRole('dialog');
  await expect(dialog.getByLabel('Prescription consultation *', { exact: true })).not.toHaveValue('');
  medicineOption = dialog.getByLabel('Prescription or stock medicine *', { exact: true }).locator('option').filter({ hasText: lastName });
  await expect(medicineOption).toHaveCount(1);
  await dialog.getByLabel('Prescription or stock medicine *', { exact: true }).selectOption(await medicineOption.getAttribute('value'));
  for (const label of ['Dose *','Route *','Frequency *','Duration *']) await dialog.getByLabel(label, { exact: true }).fill('Synthetic software test');
  await dialog.getByLabel('Total quantity (dispensing units) *', { exact: true }).fill('10');
  await dialog.getByLabel('Patient instructions *', { exact: true }).fill('Synthetic software test only');
  await dialog.getByRole('checkbox').check();
  await dialog.getByRole('button', { name: 'Sign prescription', exact: true }).click();
  await page.getByRole('row').filter({ hasText: lastName }).getByRole('button', { name: 'View prescription', exact: true }).click();
  dialog = page.getByRole('dialog');
  for (const amount of ['4','6']) {
    await dialog.getByRole('button', { name: 'Dispense medicine', exact: true }).click();
    const batchOption = dialog.getByLabel('Dispensing batch *', { exact: true }).locator('option').filter({ hasText: 'SYNTHETIC-UI-BATCH' });
    await dialog.getByLabel('Dispensing batch *', { exact: true }).selectOption(await batchOption.getAttribute('value'));
    await dialog.getByLabel('Quantity to dispense *', { exact: true }).fill(amount);
    await dialog.getByRole('checkbox').check();
    await dialog.getByRole('button', { name: 'Confirm dispensing', exact: true }).click();
    await expect(dialog.getByRole('heading', { name: 'Dispensing history', exact: true })).toBeVisible();
  }
  await expect(dialog.getByText('Dispensed', { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
  await page.getByRole('button', { name: 'Stock batches', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('10 / 20 units');
  await row.getByRole('button', { name: 'Write off', exact: true }).click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Quantity to remove *', { exact: true }).fill('2');
  await dialog.getByLabel('Write-off reason *', { exact: true }).fill('Synthetic damaged stock');
  await dialog.getByRole('button', { name: 'Confirm write-off', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: lastName })).toContainText('8 / 20 units');
  await page.getByRole('button', { name: 'Stock history', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'write off', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await expect.poll(() => page.locator('.sidebar').evaluate(el => el.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  await page.screenshot({ path: path.join(root, '.local/dija-pharmacy-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByRole('navigation').getByRole('button', { name: 'Appointments', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('completed');

  await page.getByRole('navigation').getByRole('button', { name: 'Admissions & wards' }).click();
  await page.getByRole('button', { name: 'Admit patient', exact: true }).first().click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Patient *', { exact: true }).selectOption(patientId);
  await dialog.getByLabel('Department *', { exact: true }).selectOption({ label: 'Internal medicine' });
  await dialog.getByLabel('Ward *', { exact: true }).fill('Synthetic validation ward');
  await dialog.getByLabel('Bed *', { exact: true }).fill(lastName.slice(-15));
  await dialog.getByRole('button', { name: 'Admit patient', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('Admitted');
  await row.getByRole('button', { name: 'Discharge', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm discharge' }).click();
  await expect(row).toContainText('Discharged');

  await page.getByRole('navigation').getByRole('button', { name: 'Billing & payments' }).click();
  await page.getByRole('button', { name: 'Create invoice', exact: true }).first().click();
  dialog = page.getByRole('dialog');
  await dialog.getByLabel('Patient *', { exact: true }).selectOption(patientId);
  await dialog.getByLabel('Service description *').fill('Synthetic validation consultation');
  await dialog.getByLabel('Amount (NGN) *').fill('5000.25');
  await dialog.getByRole('button', { name: 'Create invoice', exact: true }).click();
  row = page.getByRole('row').filter({ hasText: lastName });
  await expect(row).toContainText('5,000.25');
  await row.getByRole('button', { name: 'Record payment', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Record payment received' }).click();
  await expect(row.locator('.badge')).toHaveText('paid');

  await page.getByRole('navigation').getByRole('button', { name: 'Departments', exact: true }).click();
  await expect(page.locator('.department-card')).toHaveCount(33);
  await page.getByRole('button', { name: 'Diagnostics & treatment', exact: true }).click();
  await expect(page.locator('.department-card')).toHaveCount(4);
  await page.getByRole('button', { name: 'All departments 33', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Open navigation' }).click();
  await page.getByRole('navigation').getByRole('button', { name: 'Overview', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Hospital overview.' })).toBeVisible();
  await expect(page.getByText('Loading appointments…', { exact: true })).toBeHidden();
  if (await page.getByRole('button', { name: 'Dismiss notification' }).isVisible()) {
    await page.getByRole('button', { name: 'Dismiss notification' }).click();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: path.join(root, '.local/dija-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1100 });
  await page.screenshot({ path: path.join(root, '.local/dija-dashboard.png'), fullPage: true });
  await page.locator('.topbar').getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign in to workspace' })).toBeVisible();
  expect(errors).toEqual([]);
});
