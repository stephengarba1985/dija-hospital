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
from hospital.models import Patient, Appointment, Admission, Invoice, Consultation, ConsultationAddendum
patients = Patient.objects.filter(first_name='Synthetic', last_name='${lastName}')
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
  await dialog.getByRole('button', { name: 'Close', exact: true }).click();
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
  await page.getByRole('button', { name: 'Dija Administrator administrator' }).click();
  await expect(page.getByRole('button', { name: 'Sign in to workspace' })).toBeVisible();
  expect(errors).toEqual([]);
});
